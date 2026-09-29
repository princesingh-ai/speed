import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.main import create_app
from app.orchestration.events import EventBus, Trace
from app.orchestration.models import ResultReview, StartRequest
from app.orchestration.planner import Planner, fallback_plan
from app.orchestration.runtimes import RuntimeRouter
from app.orchestration.service import AgentRecord, AgentService
from app.security.consent import create_consent_request
from app.security.dependencies import DEMO_PRINCIPAL_ID, get_current_user
from app.security.jwt import create_access_token
from app.security.models import Permission, User
from app.security.policy import ResourceScope, RiskLevel
from app.security.store import get_user
from app.task.service import task_service


@pytest.fixture(params=["demo", "jwt"])
def session(request, monkeypatch):
    demo = request.param == "demo"
    monkeypatch.setattr(settings, "speed_demo_auth", demo)
    user = (User(id=DEMO_PRINCIPAL_ID, username="admin", roles=["admin"], password_hash="unused")
            if demo else get_user("admin"))
    headers = ({"X-Speed-Demo-User": DEMO_PRINCIPAL_ID} if demo else
               {"Authorization": "Bearer " + create_access_token(user)})
    with TestClient(create_app()) as client:
        yield client, user, headers


def finished(client, user):
    task = task_service.create_task(user.id, "Review the inspection")
    task_service.complete_task(task.id)
    record = AgentRecord(task, StartRequest(objective=task.prompt), review=ResultReview())
    record.final_response = "Recommendation: conditional approval. Review required."
    client.app.state.agent.records[task.id] = record
    return record, f"/api/v1/agent/tasks/{task.id}"


@pytest.mark.parametrize("decision", ["approved", "changes_requested", "rejected"])
def test_owned_review_persists_and_emits_without_changing_consent(session, decision, workspace):
    client, user, headers = session
    record, path = finished(client, user)
    relative = f"outputs/tasks/{record.task.id}/artifact/note.docx"
    artifact = workspace / relative
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"test artifact")
    record.artifacts.append({"id": "artifact", "name": "note.docx", "path": relative, "size": 13, "is_mock": False})
    consent = create_consent_request(user, Permission.SANDBOX_EXECUTE, ResourceScope.WORKSPACE,
                                    "sandbox:python", "Run tool", RiskLevel.MEDIUM, record.task.id)
    ticket = client.post(path + "/ticket", headers=headers).json()["ticket"]
    with client.websocket_connect(path + "/events") as ws:
        ws.send_json({"ticket": ticket, "after_sequence": 0})
        assert ws.receive_json()["snapshot"]["review"]["status"] == "pending"
        response = client.post(path + "/review", headers=headers,
                               json={"decision": decision, "comment": " Check the seal. "})
        assert response.status_code == 200
        review = response.json()["review"]
        assert review == {"status": decision, "comment": "Check the seal.",
                          "reviewed_by": user.id, "reviewer_name": "admin",
                          "reviewed_at": review["reviewed_at"]}
        assert review["reviewed_at"]
        event = ws.receive_json()["event"]
        assert event["event_type"] == "review.submitted" and event["status"] == decision
        assert "Check the seal" not in str(event)
    assert client.get(path, headers=headers).json()["review"] == review
    assert client.get(path + "/events", headers=headers).json()["snapshot"]["review"] == review
    assert record.task.status.value == "completed"
    assert record.final_response.startswith("Recommendation")
    assert client.get(path + "/artifacts/artifact", headers=headers).content == b"test artifact"
    assert consent.status.value == "pending"
    assert client.post(path + "/review", headers=headers, json={"decision": "approved"}).status_code == 409


def test_review_ownership_auth_readiness_and_validation(session):
    client, user, headers = session
    record, path = finished(client, user)
    assert client.post(path + "/review", json={"decision": "approved"}).status_code == 401
    for body in [{"decision": "approve"}, {"decision": "approved", "comment": "x" * 2001},
                 {"decision": "approved", "reviewed_by": "another"}]:
        assert client.post(path + "/review", headers=headers, json=body).status_code == 422
    record.task.user_id = "another-owner"
    assert client.post(path + "/review", headers=headers, json={"decision": "approved"}).status_code == 404
    record.task.user_id = user.id
    task_service.start_task(record.task.id)
    assert client.post(path + "/review", headers=headers, json={"decision": "approved"}).status_code == 409
    assert record.review.status == "pending"
    client.app.dependency_overrides[get_current_user] = lambda: user.model_copy(update={"roles": []})
    assert client.post(path + "/review", headers=headers, json={"decision": "approved"}).status_code == 403


def test_normal_api_rejects_execution_simulation(session):
    client, _, headers = session
    for flag in ["demo_mode", "test_mode"]:
        assert client.post("/api/v1/agent/tasks", headers=headers,
                           json={"objective": "Review", flag: True}).status_code == 422
    with pytest.raises(ValidationError):
        Settings(speed_jwt_secret="test-only", speed_sandbox_mode="mock", _env_file=None)


def test_model_failure_does_not_complete_with_canned_analysis(user):
    async def unavailable(_):
        raise RuntimeError("offline")

    async def scenario():
        service = AgentService(planner=Planner(unavailable), runtimes=RuntimeRouter(unavailable))
        record = service.create(user, StartRequest(objective="Review"))
        await asyncio.gather(*service.jobs)
        assert record.task.status.value == "failed"
        assert record.artifacts == [] and record.final_response == "" and record.review is None
        assert not record.has_mock
        assert not any(e.is_mock for e in service.bus.replay(record.task.id))
        assert any(e.event_type == "model.failed" for e in service.bus.replay(record.task.id))

    asyncio.run(scenario())


def test_normal_document_uses_inference_real_tools_and_review(user, workspace):
    calls = []

    async def complete(prompt):
        calls.append(prompt)
        return "Recommendation: replace the worn seal.\n[ ] Approved\nHuman review required."

    async def planned(task_id, request, trace):
        # A valid structured model response, with the real planner validation path.
        async def response(_):
            return fallback_plan(task_id, request).model_dump_json()
        return await Planner(response).plan(task_id, request, trace)

    async def scenario():
        planner = Planner()
        planner.plan = planned
        service = AgentService(planner=planner, runtimes=RuntimeRouter(complete))
        record = service.create(user, StartRequest(objective="Review"))
        await asyncio.gather(*service.jobs)
        snapshot = service.snapshot(record.task.id)
        assert snapshot["status"] == "completed" and snapshot["review"]["status"] == "pending"
        assert snapshot["planner_mode"] == "local_model" and not snapshot["has_mock"]
        assert calls and "[ ] Approved" not in snapshot["final_response"]
        from docx import Document
        text = "\n".join(p.text for p in Document(workspace / record.artifacts[0]["path"]).paragraphs)
        assert "worn seal" in text and "[ ] Approved" not in text
        assert "mock" not in text.lower() and "DEMONSTRATION" not in text
        assert not any(e.is_mock for e in service.bus.replay(record.task.id))
        assert "review.required" in [e.event_type for e in service.bus.replay(record.task.id)]

    asyncio.run(scenario())


def test_coding_model_failure_never_substitutes_example_program():
    async def unavailable(_):
        raise RuntimeError("offline")
    with pytest.raises(RuntimeError):
        asyncio.run(Planner(unavailable).plan("t", StartRequest(objective="Custom code", flow="coding"),
                                            Trace(EventBus(), "t")))


def test_normal_verification_rejects_simulated_source():
    with pytest.raises(ValueError, match="actual execution"):
        asyncio.run(RuntimeRouter().analyze({"purpose": "verification", "source": {"is_mock": True}},
                                            Trace(EventBus(), "t"), False))
