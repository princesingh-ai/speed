import asyncio
from time import perf_counter

from app.orchestration.events import Trace, current_trace
from app.orchestration.models import TaskGraph


def resolve_inputs(value, results):
    if isinstance(value, dict):
        if set(value) == {"from_step"}:
            return results[value["from_step"]]
        return {k: resolve_inputs(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_inputs(item, results) for item in value]
    return value


class Executor:
    def __init__(self, runtimes, concurrency=3, semaphore=None):
        self.runtimes = runtimes
        self.concurrency = concurrency
        self.semaphore = semaphore or asyncio.Semaphore(concurrency)

    async def run(self, record, user, bus):
        graph = TaskGraph(record.plan)
        results = {}
        mock_steps = set()
        lanes = {id: index + 1 for index, id in enumerate(graph.topological_order())}
        completed_events = {}
        active = {}

        async def execute(step):
            async with self.semaphore:
                started = perf_counter()
                inherited_mock = any(d in mock_steps for d in step.dependencies)
                parents = [lanes[d] for d in step.dependencies] or [0]
                trace = Trace(bus, record.task.id, step.id, lanes[step.id],
                              next((completed_events[d] for d in step.dependencies if d in completed_events), None),
                              inherited_mock)
                token = current_trace.set(trace)
                try:
                    step.status = "running"
                    event = trace.emit("step.started", step.title, "running",
                                       metadata={"dependencies": step.dependencies, "source_lanes": parents})
                    trace.parent_event_id = event.event_id
                    if len(step.dependencies) > 1:
                        trace.emit("branch.merged", "Dependency results joined", metadata={"source_lanes": parents})
                    inputs = resolve_inputs(step.inputs, results)
                    # Give the stream a chance to publish started states before synchronous tools.
                    await asyncio.sleep(0)
                    results[step.id] = await self.runtimes.execute(
                        step, user, record.task.id, inputs, trace, record.request.demo_mode)
                    if isinstance(results[step.id], dict) and results[step.id].get("is_mock"):
                        trace.is_mock = True
                    if trace.is_mock:
                        mock_steps.add(step.id)
                        record.has_mock = True
                    if step.kind == "artifact":
                        record.artifacts.append(results[step.id])
                    step.status = "completed"
                    event = trace.emit("step.completed", step.title,
                                       duration_ms=int((perf_counter() - started) * 1000))
                    completed_events[step.id] = event.event_id
                except asyncio.CancelledError:
                    step.status = "failed"
                    trace.emit("step.failed", "Step cancelled", "failed")
                    raise
                except Exception as exc:
                    step.status = "failed"
                    trace.emit("step.failed", "Step failed", "failed",
                               metadata={"error_code": type(exc).__name__},
                               duration_ms=int((perf_counter() - started) * 1000))
                finally:
                    current_trace.reset(token)

        try:
            while True:
                blocked = graph.blocked()
                while blocked:
                    for step in blocked:
                        step.status = "blocked"
                        Trace(bus, record.task.id, step.id, lanes[step.id]).emit(
                            "step.blocked", "Dependency failed", "blocked")
                    blocked = graph.blocked()
                ready = graph.ready()
                if len(ready) > 1:
                    bus.emit(record.task.id, "branch.started", f"{len(ready)} independent steps ready",
                             metadata={"dependencies": [s.id for s in ready]})
                for step in ready:
                    step.status = "ready"
                    Trace(bus, record.task.id, step.id, lanes[step.id]).emit("step.ready", step.title, "ready")
                    active[step.id] = asyncio.create_task(execute(step))
                if not active:
                    break
                done, _ = await asyncio.wait(active.values(), return_when=asyncio.FIRST_COMPLETED)
                for future in done:
                    await future
                active = {id: future for id, future in active.items() if future not in done}
        finally:
            for future in active.values():
                future.cancel()
            await asyncio.gather(*active.values(), return_exceptions=True)
        ok = all(s.status == "completed" for s in record.plan.steps)
        if ok:
            # Keep actual model/verification output in the ownership-protected snapshot,
            # never in operational event metadata. Plan order is deterministic.
            responses = [results[id] for id in graph.topological_order()
                         if graph.nodes[id].kind == "llm" and isinstance(results.get(id), str)]
            record.final_response = responses[-1] if responses else "Workflow completed."
        return ok
