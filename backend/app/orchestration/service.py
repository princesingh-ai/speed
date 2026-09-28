import asyncio
from dataclasses import dataclass, field

from app.core.config import settings
from app.orchestration.events import EventBus, Trace
from app.orchestration.executor import Executor
from app.orchestration.models import ExecutionPlan, StartRequest
from app.orchestration.planner import Planner
from app.orchestration.runtimes import RuntimeRouter
from app.security.gateway import security_gateway
from app.security.models import Permission
from app.security.policy import ResourceScope
from app.task.execution import ExecutionTask
from app.task.service import task_service


@dataclass
class AgentRecord:
    task: ExecutionTask
    request: StartRequest
    plan: ExecutionPlan | None = None
    artifacts: list = field(default_factory=list)
    has_mock: bool = False
    final_response: str = ""


class AgentService:
    def __init__(self, planner=None, runtimes=None):
        self.records = {}
        self.jobs = set()
        self.bus = EventBus()
        self.planner = planner or Planner()
        self.runtimes = runtimes or RuntimeRouter()
        self.semaphore = asyncio.Semaphore(settings.speed_step_concurrency)

    def create(self, user, request):
        if len(self.records) >= 100 or len(self.jobs) >= 8:
            raise ValueError("Phase 1 capacity reached; restart after active work completes")
        task = task_service.create_task(user_id=user.id, prompt=request.objective)
        decision = security_gateway.authorize(user=user, task_id=task.id,
            permission=Permission.AGENT_EXECUTE, scope=ResourceScope.WORKSPACE,
            resource="agent:phase1", reason="Start Phase 1 workflow")
        if not decision.allowed or decision.requires_consent:
            task_service.tasks.pop(task.id, None)
            raise PermissionError("Agent execution denied")
        record = AgentRecord(task, request)
        self.records[task.id] = record
        self.bus.emit(task.id, "task.created", "Task created", "pending")
        job = asyncio.create_task(self.run(record, user))
        self.jobs.add(job)
        job.add_done_callback(self.jobs.discard)
        return record

    async def run(self, record, user):
        trace = Trace(self.bus, record.task.id)
        try:
            task_service.start_task(record.task.id)
            trace.emit("task.started", "Task started", "running")
            record.plan = await self.planner.plan(record.task.id, record.request, trace)
            ok = await Executor(self.runtimes, semaphore=self.semaphore).run(record, user, self.bus)
            if ok:
                task_service.complete_task(record.task.id)
                trace.emit("task.completed", "Task completed", is_mock=record.has_mock,
                           summary="Includes demonstration content; human review required." if record.has_mock else "Workflow completed.")
            else:
                task_service.fail_task(record.task.id, "One or more steps failed. See execution history.")
                trace.emit("task.failed", "Task failed", "failed")
        except asyncio.CancelledError:
            task_service.fail_task(record.task.id, "Server stopped")
            trace.emit("task.failed", "Task interrupted by shutdown", "failed")
            raise
        except Exception as exc:
            task_service.fail_task(record.task.id, "Planning or execution failed")
            trace.emit("task.failed", "Task failed", "failed", metadata={"error_code": type(exc).__name__})

    def snapshot(self, task_id):
        record = self.records[task_id]
        steps = record.plan.steps if record.plan else []
        return {
            "task_id": task_id, "objective": record.task.prompt, "status": record.task.status.value,
            "planner_mode": record.plan.planner_mode if record.plan else None,
            "steps": [s.model_dump(exclude={"inputs", "description"}) for s in steps],
            "running_steps": [s.id for s in steps if s.status in {"running", "waiting"}],
            "artifacts": [{**a, "download_url": f"/api/v1/agent/tasks/{task_id}/artifacts/{a['id']}"} for a in record.artifacts],
            "last_sequence": self.bus.sequences[task_id], "has_mock": record.has_mock,
            "summary": record.task.error or ("Human review required." if record.has_mock else ""),
            "final_response": record.final_response,
        }

    async def close(self):
        jobs = list(self.jobs)
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
