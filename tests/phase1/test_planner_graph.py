import asyncio

import pytest
from pydantic import ValidationError

from app.orchestration.events import EventBus, Trace
from app.orchestration.models import ExecutionPlan, PlanStep, StartRequest, TaskGraph
from app.orchestration.planner import Planner, fallback_plan, validate_tools


def plan(steps):
    return ExecutionPlan(task_id="t", objective="Review", planner_mode="local_model", steps=steps)


def node(id, dependencies=()):
    return PlanStep(id=id, title=id, kind="llm", dependencies=list(dependencies))


def test_valid_structured_plan_and_fan_in():
    graph = TaskGraph(plan([node("read"), node("a", ["read"]), node("b", ["read"]), node("merge", ["a", "b"])]))
    assert [s.id for s in graph.ready()] == ["read"]
    graph.nodes["read"].status = "completed"
    assert {s.id for s in graph.ready()} == {"a", "b"}
    graph.nodes["a"].status = "completed"
    assert "merge" not in [s.id for s in graph.ready()]
    graph.nodes["b"].status = "completed"
    assert [s.id for s in graph.ready()] == ["merge"]
    assert graph.topological_order() == ["read", "a", "b", "merge"]


@pytest.mark.parametrize("steps", [
    [node("a"), node("a")],
    [node("a", ["missing"])],
    [node("a", ["a"])],
    [node("a", ["b"]), node("b", ["a"])],
])
def test_invalid_dependencies_rejected(steps):
    with pytest.raises(ValidationError):
        plan(steps)


def test_unknown_kind_tool_and_reference_rejected():
    with pytest.raises(ValidationError):
        PlanStep(id="a", title="A", kind="unknown")
    with pytest.raises(ValueError):
        validate_tools(plan([PlanStep(id="a", title="A", kind="native_tool", tool_name="shell.exec")]))
    with pytest.raises(ValueError):
        validate_tools(plan([PlanStep(id="a", title="A", kind="llm", inputs={"source": {"from_step": "b"}})]))


def test_failed_dependency_blocks_descendants():
    graph = TaskGraph(plan([node("a"), node("b", ["a"]), node("c", ["b"])]))
    graph.nodes["a"].status = "failed"
    assert [s.id for s in graph.blocked()] == ["b"]
    graph.nodes["b"].status = "blocked"
    assert [s.id for s in graph.blocked()] == ["c"]


@pytest.mark.parametrize("response", ["invalid JSON", '{"steps": []}'])
def test_malformed_planner_falls_back(response):
    async def complete(_):
        return response
    bus = EventBus()
    result = asyncio.run(Planner(complete).plan("t", StartRequest(objective="Review any report"), Trace(bus, "t")))
    assert result.planner_mode == "deterministic_fallback"
    assert "model.failed" in [e.event_type for e in bus.replay("t")]
    assert next(e for e in bus.replay("t") if e.event_type == "plan.fallback").is_mock


def test_real_structured_planner_and_explicit_demo():
    request = StartRequest(objective="Review")
    valid = fallback_plan("t", request)
    valid.planner_mode = "local_model"
    calls = []
    async def complete(prompt):
        calls.append(prompt)
        return valid.model_dump_json()
    assert asyncio.run(Planner(complete).plan("t", request, Trace(EventBus(), "t"))).planner_mode == "local_model"
    request.demo_mode = True
    assert asyncio.run(Planner(complete).plan("t", request, Trace(EventBus(), "t"))).planner_mode == "deterministic_fallback"
    assert len(calls) == 1


def test_model_unavailable_falls_back():
    async def unavailable(_):
        raise RuntimeError("offline")
    result = asyncio.run(Planner(unavailable).plan("t", StartRequest(objective="Review"), Trace(EventBus(), "t")))
    assert result.planner_mode == "deterministic_fallback"


def test_planner_timeout_is_disclosed(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "speed_model_timeout", .01)
    async def never(_):
        await asyncio.Event().wait()
    bus = EventBus()
    result = asyncio.run(Planner(never).plan("t", StartRequest(objective="Review"), Trace(bus, "t")))
    assert result.planner_mode == "deterministic_fallback"
    assert "model.failed" in [e.event_type for e in bus.replay("t")]


def test_phase1_rejects_public_inference_endpoint(monkeypatch):
    from types import SimpleNamespace
    from app.orchestration import planner
    class Router:
        def route(self, capability):
            return SimpleNamespace(endpoint="https://example.com", model="unapproved")
    monkeypatch.setattr(planner, "ModelRouter", Router)
    with pytest.raises(PermissionError):
        asyncio.run(planner.local_completion("private prompt"))
