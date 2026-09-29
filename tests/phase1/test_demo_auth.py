from functools import partial
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings, settings
from app.main import create_app
from app.orchestration.models import StartRequest
from app.orchestration.service import AgentRecord
from app.security.dependencies import DEMO_PRINCIPAL_ID
from app.security.models import User, Permission
from app.security.policy import ResourceScope, RiskLevel
from app.security.consent import create_consent_request
from app.security.gateway import security_gateway
from app.task.service import task_service

HEADERS = {"X-Speed-Demo-User": DEMO_PRINCIPAL_ID}
DEMO = User(id=DEMO_PRINCIPAL_ID, username="admin", roles=["admin"], password_hash="unused")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "speed_demo_auth", True)
    with TestClient(create_app()) as client:
        yield client


def idle(client, owner):
    task = task_service.create_task(owner, "Demo ownership")
    client.app.state.agent.records[task.id] = AgentRecord(task, StartRequest(objective="Demo ownership"))
    return task.id


def test_demo_defaults_off_and_marker_cannot_bypass_jwt(monkeypatch):
    assert Settings.model_fields["speed_demo_auth"].default is False
    monkeypatch.setattr(settings, "speed_demo_auth", False)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/auth/config").json() == {"demo_auth": False}
        for headers in [HEADERS, {}, {"X-Speed-Demo-User": "anything"}]:
            assert client.get("/api/v1/models/health", headers=headers).status_code == 401
        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-password"})
        assert login.status_code == 200
        real = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + login.json()["access_token"]})
        assert real.status_code == 200
        assert real.json()["id"] == "user-admin"


def test_demo_agent_and_health_without_login(client, monkeypatch):
    from app.api.routes import models, chat
    from app.task.models import TaskAnalysis
    monkeypatch.setattr(models.model_router, "health", AsyncMock(return_value={"availability": "unavailable"}))
    monkeypatch.setattr(chat.routing_service, "route", AsyncMock(return_value=(TaskAnalysis(task_type="general"), object())))
    monkeypatch.setattr(chat.inference_service, "chat", AsyncMock(return_value={"choices": []}))
    config = client.get("/api/v1/auth/config")
    assert config.json() == {"demo_auth": True}
    assert config.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/auth/me", headers=HEADERS).json() == {
        "id": DEMO_PRINCIPAL_ID, "username": "admin", "roles": ["admin"]}
    started = client.post("/api/v1/agent/tasks", headers=HEADERS,
                          json={"objective": "Review", "demo_mode": True})
    assert started.status_code == 202
    task_id = started.json()["task_id"]
    assert client.app.state.agent.records[task_id].task.user_id == DEMO_PRINCIPAL_ID
    assert client.get(f"/api/v1/agent/tasks/{task_id}", headers=HEADERS).status_code == 200
    assert client.get("/api/v1/models/health", headers=HEADERS).status_code == 200
    assert client.post("/v1/chat/completions", headers=HEADERS,
                       json={"messages": [{"role": "user", "content": "Hello"}]}).status_code == 200
    for headers in [{}, {"X-Speed-Demo-User": "admin"}, {"X-Speed-Demo-User": "anything"},
                    {"Authorization": "Bearer speed-demo-admin"}]:
        assert client.get("/api/v1/models/health", headers=headers).status_code == 401


def test_demo_tickets_remain_single_use_task_bound_and_owner_checked(client):
    own, foreign = idle(client, DEMO_PRINCIPAL_ID), idle(client, "another-owner")
    ticket_path = f"/api/v1/agent/tasks/{own}/ticket"
    assert client.post(f"/api/v1/agent/tasks/{foreign}/ticket", headers=HEADERS).status_code == 404
    ticket = client.post(ticket_path, headers=HEADERS).json()["ticket"]
    assert client.app.state.ws_tickets[ticket][1] == DEMO_PRINCIPAL_ID
    with client.websocket_connect(f"/api/v1/agent/tasks/{own}/events") as ws:
        ws.send_json({"ticket": ticket})
        assert ws.receive_json()["snapshot"]["task_id"] == own
    for target, value in [(own, ticket), (foreign, client.post(ticket_path, headers=HEADERS).json()["ticket"])]:
        with client.websocket_connect(f"/api/v1/agent/tasks/{target}/events") as ws:
            ws.send_json({"ticket": value})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


def test_demo_artifacts_still_require_registered_id_and_owner(client, workspace):
    from app.orchestration.artifacts import ArtifactRuntime
    from app.orchestration.events import Trace
    own, foreign = idle(client, DEMO_PRINCIPAL_ID), idle(client, "another-owner")
    service = client.app.state.agent
    for task_id in [own, foreign]:
        artifact = client.portal.call(partial(ArtifactRuntime().create_word, task_id,
                                             {"content": "Demo"}, Trace(service.bus, task_id)))
        service.records[task_id].artifacts.append(artifact)
        result = client.get(f"/api/v1/agent/tasks/{task_id}/artifacts/{artifact['id']}", headers=HEADERS)
        assert result.status_code == (200 if task_id == own else 404)
    assert client.get(f"/api/v1/agent/tasks/{own}/artifacts/unknown", headers=HEADERS).status_code == 404


def test_demo_does_not_auto_approve_consent(client):
    own = idle(client, DEMO_PRINCIPAL_ID)
    args = dict(user=DEMO, task_id=own, permission=Permission.SANDBOX_EXECUTE,
                scope=ResourceScope.WORKSPACE, resource="python", reason="Demo test")
    decision = security_gateway.authorize(**args)
    assert decision.requires_consent
    consent = create_consent_request(**args, risk=RiskLevel.HIGH)
    assert consent.user_id == DEMO_PRINCIPAL_ID
    assert not security_gateway.authorize(**args, consent_id=consent.id).allowed
    assert client.post(f"/api/v1/permissions/{consent.id}/approve", headers=HEADERS).status_code == 200
    assert security_gateway.authorize(**args, consent_id=consent.id).allowed
    other = DEMO.model_copy(update={"id": "another-owner"})
    foreign = create_consent_request(**{**args, "user": other}, risk=RiskLevel.HIGH)
    assert client.post(f"/api/v1/permissions/{foreign.id}/approve", headers=HEADERS).status_code == 404
