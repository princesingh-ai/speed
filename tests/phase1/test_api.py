from functools import partial

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.orchestration.models import StartRequest
from app.orchestration.service import AgentRecord
from app.security.dependencies import get_current_user
from app.task.service import task_service


@pytest.fixture
def client(user):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client


def idle_task(client, user):
    task = task_service.create_task(user.id, "An idle task")
    service = client.app.state.agent
    service.records[task.id] = AgentRecord(task, StartRequest(objective="An idle task"))
    client.portal.call(partial(service.bus.emit, task.id, "task.created", "Task created"))
    return task.id


def ticket(client, task_id):
    response = client.post(f"/api/v1/agent/tasks/{task_id}/ticket")
    assert response.status_code == 200
    return response.json()["ticket"]


def test_websocket_replay_live_disconnect_resume(client, user):
    task_id = idle_task(client, user)
    route = f"/api/v1/agent/tasks/{task_id}/events"
    auth = ticket(client, task_id)
    with client.websocket_connect(route) as ws:
        ws.send_json({"ticket": auth, "after_sequence": 0})
        initial = ws.receive_json()
        assert initial["type"] == "snapshot" and initial["events"][0]["sequence"] == 1
        for index in [2, 3]:
            client.portal.call(partial(client.app.state.agent.bus.emit, task_id, "step.ready", "Ready"))
            assert ws.receive_json()["event"]["sequence"] == index
    with client.websocket_connect(route) as ws:
        ws.send_json({"ticket": ticket(client, task_id), "after_sequence": 2})
        assert [e["sequence"] for e in ws.receive_json()["events"]] == [3]
    with client.websocket_connect(route) as ws:
        ws.send_json({"ticket": auth})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert client.get(route + "?after_sequence=1").json()["events"][0]["sequence"] == 2


def test_ownership_unknown_task_and_ticket_isolation(client, user):
    own = idle_task(client, user)
    other = user.model_copy(update={"id": "another-user"})
    foreign = idle_task(client, other)
    for suffix in ["", "/events", "/artifacts/unknown"]:
        assert client.get(f"/api/v1/agent/tasks/{foreign}{suffix}").status_code == 404
    assert client.get("/api/v1/agent/tasks/unknown").status_code == 404
    assert client.post(f"/api/v1/agent/tasks/{foreign}/ticket").status_code == 404
    for target in [foreign, "unknown"]:
        with client.websocket_connect(f"/api/v1/agent/tasks/{target}/events") as ws:
            ws.send_json({"ticket": ticket(client, own)})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


def test_artifact_download_registered_only(client, user, workspace):
    task_id = idle_task(client, user)
    from app.orchestration.artifacts import ArtifactRuntime
    from app.orchestration.events import Trace
    service = client.app.state.agent
    artifact = client.portal.call(partial(ArtifactRuntime().create_word, task_id,
                                         {"content": "Approved for review"}, Trace(service.bus, task_id)))
    service.records[task_id].artifacts.append(artifact)
    response = client.get(f"/api/v1/agent/tasks/{task_id}/artifacts/{artifact['id']}")
    assert response.status_code == 200 and response.content.startswith(b"PK")
    assert client.get(f"/api/v1/agent/tasks/{task_id}/artifacts/unknown").status_code == 404


def test_auth_required_and_dashboard_static():
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/agent/tasks", json={"objective": "Review"}).status_code in {401, 403}
        response = client.get("/phase1/")
        assert response.status_code == 200 and 'id="lanes"' in response.text
        assert client.get("/phase1/app.js").status_code == 200


def test_development_login_supplies_real_agent_session(caplog, monkeypatch):
    from unittest.mock import AsyncMock
    from app.orchestration.service import AgentService
    monkeypatch.setattr(AgentService, "run", AsyncMock())
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
        response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-password"})
        assert response.status_code == 200
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        assert "admin-password" not in caplog.text
        assert response.json()["access_token"] not in caplog.text
        user = client.get("/api/v1/auth/me", headers=headers).json()
        assert user == {"id": "user-admin", "username": "admin", "roles": ["admin"]}
        started = client.post("/api/v1/agent/tasks", headers=headers,
                              json={"objective": "Review"})
        assert started.status_code == 202
        path = "/api/v1/agent/tasks/" + started.json()["task_id"]
        assert client.get(path, headers=headers).status_code == 200
        assert client.post(path + "/ticket", headers=headers).status_code == 200
        assert client.get(path).status_code in {401, 403}
        other = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "test-password"})
        assert client.get(path, headers={"Authorization": "Bearer " + other.json()["access_token"]}).status_code == 404
        assert client.get("/api/v1/models/health").status_code in {401, 403}
        assert client.post("/v1/chat/completions", json={"messages": []}).status_code in {401, 403}


def test_same_login_authorizes_normal_chat_and_health(monkeypatch):
    from unittest.mock import AsyncMock
    from app.api.routes import chat, models
    from app.task.models import TaskAnalysis
    route = AsyncMock(return_value=(TaskAnalysis(task_type="general", mode="deterministic_fallback"), object()))
    monkeypatch.setattr(chat.routing_service, "route", route)
    monkeypatch.setattr(chat.inference_service, "chat", AsyncMock(return_value={"choices": []}))
    monkeypatch.setattr(models.model_router, "health", AsyncMock(return_value={"availability": "unavailable"}))
    with TestClient(create_app()) as client:
        token = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-password"}).json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        response = client.post("/v1/chat/completions", headers=headers,
                               json={"messages": [{"role": "user", "content": "Hello"}]})
        assert response.status_code == 200
        assert response.headers["X-SPEED-Task-Analysis"] == "deterministic_fallback"
        assert client.get("/api/v1/models/health", headers=headers).status_code == 200
        assert all("laya" not in model["id"] for model in client.get("/v1/models").json()["data"])


def test_gateway_configuration_preserves_inference():
    from pathlib import Path
    conf = Path("infrastructure/nginx/conf/nginx.conf").read_text()
    assert "location /api/v1/" in conf and "proxy_set_header Upgrade $http_upgrade" in conf
    assert "location = /v1/stream" in conf and "location = /v1/streams/lookup" in conf
    assert "proxy_pass http://llama_backend" in conf
    login = conf.split("location = /login {", 1)[1].split("}", 1)[0]
    assert 'return 302 "/#/login";' in login
    assert "proxy_pass" not in login
    root = conf.split("location / {", 1)[1].split("}", 1)[0]
    assert "proxy_pass http://llama_backend;" in root
    api = conf.split("location /api/v1/ {", 1)[1].split("}", 1)[0]
    assert "proxy_pass http://speed_backend;" in api
    assert "proxy_set_header Connection $connection_upgrade;" in api
    inference = conf.split("location /v1/ {", 1)[1].split("}", 1)[0]
    assert "proxy_pass http://speed_backend;" in inference
    for path in ("/v1/stream", "/v1/streams/lookup"):
        block = conf.split(f"location = {path} {{", 1)[1].split("}", 1)[0]
        assert "proxy_pass http://llama_backend;" in block


def test_start_returns_task_handle_and_snapshot(client, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(client.app.state.agent, "run", AsyncMock())
    response = client.post("/api/v1/agent/tasks", json={"objective": "Review"})
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    snapshot = client.get(f"/api/v1/agent/tasks/{task_id}")
    assert snapshot.status_code == 200
    assert snapshot.json()["objective"] == "Review"
    assert "inputs" not in str(snapshot.json()["steps"])


def test_invalid_websocket_cursor(client, user):
    task_id = idle_task(client, user)
    with client.websocket_connect(f"/api/v1/agent/tasks/{task_id}/events") as ws:
        ws.send_json({"ticket": ticket(client, task_id), "after_sequence": -1})
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4400


def test_final_response_is_owner_only_and_not_in_events(client, user):
    task_id = idle_task(client, user)
    service = client.app.state.agent
    service.records[task_id].final_response = "Confidential review result"
    assert client.get(f"/api/v1/agent/tasks/{task_id}").json()["final_response"] == "Confidential review result"
    assert "Confidential review result" not in str(service.bus.replay(task_id))
    client.app.dependency_overrides[get_current_user] = lambda: user.model_copy(update={"id": "different-owner"})
    assert client.get(f"/api/v1/agent/tasks/{task_id}").status_code == 404
    assert client.get(f"/api/v1/agent/tasks/{task_id}/events").status_code == 404
