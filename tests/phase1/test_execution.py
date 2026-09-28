import asyncio
from types import SimpleNamespace

import pytest
from docx import Document

from app.orchestration.events import EventBus, Trace, current_trace
from app.orchestration.executor import Executor
from app.orchestration.models import ExecutionPlan, PlanStep, StartRequest
from app.orchestration.service import AgentService
from app.security.gateway import security_gateway
from app.security.models import Permission
from app.security.policy import ResourceScope
from app.task.models import TaskAnalysis
from app.task.service import task_service
from app.tools.models import ToolRequest, ToolStatus
from app.tools.runtime import tool_runtime
from app.tools.builtin.filesystem import list_files, read_file, write_file
from app.tools.builtin.filesystem_scope import filesystem_scope


def test_event_sequences_privacy_replay_and_isolation():
    bus = EventBus()
    async def scenario():
        queue, replay = bus.subscribe("t")
        assert replay == []
        trace = Trace(bus, "t", "step", 1)
        trace.emit("file.read", "Read report", metadata={"path": "report.txt", "content": "PRIVATE", "token": "SECRET"})
        trace.emit("model.fallback", "Mock analysis", is_mock=True)
        assert (await queue.get()).sequence == 1
        assert (await queue.get()).sequence == 2
        bus.unsubscribe("t", queue)
    asyncio.run(scenario())
    assert [e.sequence for e in bus.replay("t")] == [1, 2]
    assert bus.replay("other") == []
    assert bus.replay("t", 1)[0].is_mock
    assert "PRIVATE" not in str(bus.replay("t")) and "SECRET" not in str(bus.replay("t"))
    assert bus.replay("t")[0].step_id == "step"


def test_bounded_history_and_slow_subscriber():
    bus = EventBus(history_limit=3)
    async def scenario():
        queue, _ = bus.subscribe("t")
        for _ in range(260):
            bus.emit("t", "step.ready", "Ready")
        assert await queue.get() is None
        assert queue not in bus.subscribers["t"]
    asyncio.run(scenario())
    assert [e.sequence for e in bus.replay("t")] == [258, 259, 260]


def test_native_files_and_runtime_telemetry(user, workspace):
    task = task_service.create_task(user.id, "files")
    bus = EventBus()
    token = current_trace.set(Trace(bus, task.id, "write", 1))
    try:
        for content in ("one\n", "one\ntwo\n"):
            result = tool_runtime.execute(user=user, request=ToolRequest(
                task_id=task.id, tool_name="file.write", arguments={"path": "draft.txt", "content": content}))
            assert result.status == ToolStatus.SUCCESS
    finally:
        current_trace.reset(token)
    assert read_file("draft.txt")["content"] == "one\ntwo\n"
    assert any(e["name"] == "draft.txt" for e in list_files()["entries"])
    events = bus.replay(task.id)
    assert {"file.created", "file.updated"} <= {e.event_type for e in events}
    edit = next(e for e in events if e.event_type == "file.updated")
    assert edit.metadata["path"] == "draft.txt" and edit.metadata["lines_added"] == 1
    assert "content" not in edit.metadata


@pytest.mark.parametrize("path", ["../escape", "/tmp/escape", "a/../../escape"])
def test_workspace_traversal_rejected(path):
    with pytest.raises(PermissionError):
        write_file(path, "no")


def test_symlink_escape_rejected(workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        write_file("link/escape", "no")


def test_gateway_without_task_and_foreign_owner(user):
    args = dict(user=user, permission=Permission.FILE_READ, scope=ResourceScope.WORKSPACE,
                resource="report.txt", reason="test")
    assert not security_gateway.authorize(**args).allowed
    task = task_service.create_task("someone-else", "test")
    assert not security_gateway.authorize(**args, task_id=task.id).allowed


def test_analysis_confidence_and_missing_route(tmp_path):
    from app.routing.model_router import ModelRouter
    assert TaskAnalysis(task_type="coding", confidence=0.8).confidence == 0.8
    config = tmp_path / "models.yaml"
    config.write_text("models: {}", encoding="utf-8")
    assert ModelRouter(str(config)).route("reasoning") is None


@pytest.mark.parametrize("fail", [False, True])
def test_executor_parallel_merge_failure_and_bound(user, fail):
    async def scenario():
        barrier = asyncio.Event()
        active = 0
        peak = 0
        finished = set()
        class Runtime:
            async def execute(self, step, *args):
                nonlocal active, peak
                active += 1
                peak = max(active, peak)
                try:
                    if step.id in {"a", "b"}:
                        if active == 2:
                            barrier.set()
                        await asyncio.wait_for(barrier.wait(), 1)
                    if step.id == "merge":
                        assert {"a", "b"} <= finished
                    if fail and step.id == "a":
                        raise ValueError("private exception")
                    finished.add(step.id)
                    return step.id
                finally:
                    active -= 1
        steps = [PlanStep(id=id, title=id, kind="llm", dependencies=deps) for id, deps in
                 [("read", []), ("a", ["read"]), ("b", ["read"]), ("merge", ["a", "b"]), ("last", ["merge"])]]
        record = SimpleNamespace(plan=ExecutionPlan(task_id="t", objective="test", planner_mode="local_model", steps=steps),
                                 task=SimpleNamespace(id="t"), request=StartRequest(objective="test"), artifacts=[], has_mock=False)
        bus = EventBus()
        result = await Executor(Runtime(), concurrency=2).run(record, user, bus)
        assert result is not fail
        assert peak == 2
        if fail:
            assert steps[-1].status == "blocked" and steps[-2].status == "blocked"
        else:
            lifecycle = [e.event_type for e in bus.replay("t") if e.step_id == "read"]
            assert lifecycle == ["step.ready", "step.started", "step.completed"]
            assert "branch.merged" in [e.event_type for e in bus.replay("t")]
        assert "private exception" not in str(bus.replay("t"))
    asyncio.run(scenario())


def test_deterministic_document_end_to_end(user, workspace):
    async def scenario():
        service = AgentService()
        record = service.create(user, StartRequest(objective="Review the inspection and prepare a note", demo_mode=True))
        await asyncio.gather(*service.jobs)
        assert record.task.status.value == "completed"
        assert record.has_mock
        artifact = record.artifacts[0]
        path = workspace / artifact["path"]
        assert path.is_file() and path.stat().st_size > 0
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Approval note" in text and "worn seal" in text and "DEMONSTRATION" in text
        types = [e.event_type for e in service.bus.replay(record.task.id)]
        for kind in ["plan.fallback", "file.read", "branch.started", "branch.merged", "file.created", "artifact.created", "task.completed"]:
            assert kind in types
        assert types.index("file.read") < types.index("artifact.created") < types.index("task.completed")
        assert "worn seal" not in str(service.bus.replay(record.task.id))
        await service.close()
    asyncio.run(scenario())


def test_task_failure_blocks_artifact(user):
    async def scenario():
        service = AgentService()
        record = service.create(user, StartRequest(objective="Missing report", input_path="missing.txt", demo_mode=True))
        await asyncio.gather(*service.jobs)
        assert record.task.status.value == "failed"
        assert not record.artifacts
        assert any(s.status == "blocked" for s in record.plan.steps)
    asyncio.run(scenario())


def test_approved_consent_expiry(user):
    import time
    from app.security.consent import create_consent_request, approve_consent, get_consent_request
    from app.security.policy import RiskLevel
    consent = create_consent_request(user, Permission.MCP_USE, ResourceScope.WORKSPACE,
                                     "mcp:local-demo/calculator", "test", RiskLevel.MEDIUM, "t")
    approve_consent(consent.id, user)
    consent.expires_at = time.time() - 1
    assert get_consent_request(consent.id).status.value == "expired"


def test_shutdown_cancels_background_task(user):
    class SlowPlanner:
        async def plan(self, *args):
            await asyncio.Event().wait()
    async def scenario():
        service = AgentService(planner=SlowPlanner())
        record = service.create(user, StartRequest(objective="wait"))
        await asyncio.sleep(0)
        await service.close()
        assert record.task.status.value == "failed"
        assert all(job.done() for job in service.jobs)
    asyncio.run(scenario())
