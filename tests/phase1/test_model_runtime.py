import asyncio
import sys
from pathlib import Path

import httpx
import pytest

from app.routing.model_router import ModelRouter
from app.routing.service import RoutingService
from app.task.analyzer import TaskAnalyzer


def configured(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEED_GEMMA_MODEL", str(tmp_path / "gemma.gguf"))
    monkeypatch.setenv("SPEED_LAYA_MODEL", str(tmp_path / "laya"))
    monkeypatch.delenv("SPEED_MODELS_CONFIG", raising=False)
    monkeypatch.delenv("SPEED_GEMMA_ENDPOINT", raising=False)
    return ModelRouter()


def test_configured_models_and_missing_laya(tmp_path, monkeypatch):
    router = configured(tmp_path, monkeypatch)
    assert set(router.models) == {"gemma-reasoning", "laya"}
    laya = router.get("laya")
    assert laya.kind == "in_process" and laya.endpoint is None
    status = asyncio.run(router.health(laya))
    assert status["availability"] == "missing_artifact"
    assert status["artifact_exists"] is False
    Path(laya.model).mkdir()
    monkeypatch.setattr(TaskAnalyzer, "status", "not_loaded")
    assert asyncio.run(router.health(laya))["availability"] == "not_loaded"
    monkeypatch.setattr(TaskAnalyzer, "status", "healthy")
    assert asyncio.run(router.health(laya))["availability"] == "healthy"


@pytest.mark.parametrize("availability", ["healthy", "unavailable", "model_mismatch"])
def test_endpoint_health_controls_selection(tmp_path, monkeypatch, availability):
    router = configured(tmp_path, monkeypatch)
    model = router.get("gemma-reasoning")
    def handler(request):
        if availability == "unavailable":
            return httpx.Response(503)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={"data": [{"id": model.model_id if availability == "healthy" else "other-model"}]})
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(router.health(model))["availability"] == availability
    assert asyncio.run(router.route("general")) == (model if availability == "healthy" else None)
    assert asyncio.run(router.route("routing")) is None


def test_laya_missing_uses_disclosed_fallback(tmp_path, monkeypatch, caplog):
    router = configured(tmp_path, monkeypatch)
    service = RoutingService()
    service.model_router = router
    analysis = service.analyze("Private input never logged")
    assert analysis.mode == "deterministic_fallback"
    assert analysis.task_type.value == "general"
    assert "fallback=deterministic_general" in caplog.text
    assert "Private input" not in caplog.text


def test_endpoint_credentials_and_placeholder_port_rejected(tmp_path, monkeypatch):
    configured(tmp_path, monkeypatch)
    for endpoint in ["http://127.0.0.1:0", "https://user:secret@localhost:8080", "https://example.com"]:
        monkeypatch.setenv("SPEED_GEMMA_ENDPOINT", endpoint)
        with pytest.raises(ValueError):
            ModelRouter()


def test_startup_validation_does_not_launch_and_discloses_missing_laya(tmp_path, monkeypatch, capsys):
    from app import model_startup
    router = configured(tmp_path, monkeypatch)
    Path(router.get("gemma-reasoning").model).write_bytes(b"test artifact placeholder")
    monkeypatch.setattr(model_startup, "ModelRouter", lambda: router)
    monkeypatch.setattr("sys.argv", ["model_startup", "--validate-only"])
    def forbidden(*args):
        raise AssertionError("Validation must not start a process")
    monkeypatch.setattr(model_startup.os, "execv", forbidden)
    model_startup.main()
    output = capsys.readouterr().out
    assert "runtime not verified" in output
    assert "laya: unavailable: model artifact not found" in output
    assert "no port" in output


def test_laya_load_failure_is_reported_without_repeated_loading(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    router = configured(tmp_path, monkeypatch)
    Path(router.get("laya").model).mkdir()
    monkeypatch.setattr(TaskAnalyzer, "status", "not_loaded")
    load = Mock(side_effect=RuntimeError("synthetic load failure"))
    monkeypatch.setitem(sys.modules, "laya", SimpleNamespace(load=load))
    service = RoutingService()
    service.model_router = router
    assert service.analyze("one").mode == "deterministic_fallback"
    assert service.analyze("two").mode == "deterministic_fallback"
    assert load.call_count == 1
    assert asyncio.run(router.health(router.get("laya")))["availability"] == "failed"
