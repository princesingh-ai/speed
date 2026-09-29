import asyncio
import json
import logging
from urllib.parse import urlsplit

from app.core.config import settings
from app.inference.service import InferenceService
from app.routing.model_router import ModelRouter
from app.orchestration.models import ExecutionPlan, PlanStep
from app.tools.registry import tool_registry


async def local_completion(prompt: str) -> str:
    model = await ModelRouter().route("reasoning")
    if model is None:
        raise RuntimeError("No reasoning model configured")
    logging.getLogger("speed.models").info("planner inference selected model=%s", model.name)
    # Phase 1 never sends confidential prompts to a public endpoint.
    url = urlsplit(model.endpoint)
    if url.scheme not in {"http", "https"} or url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise PermissionError("Phase 1 inference must use a loopback endpoint")
    async with asyncio.timeout(settings.speed_model_timeout):
        response = await InferenceService().chat(
            messages=[{"role": "user", "content": prompt}], model=model)
    return response["choices"][0]["message"]["content"][:100_000]


def validate_tools(plan):
    fixed = {"sandbox": {"python"}, "mcp": {"search_internal_docs", "calculator"},
             "artifact": {"document.create_word"}, "llm": {None}}
    for step in plan.steps:
        if step.status != "pending":
            raise ValueError("Planner cannot set execution state")
        if step.kind == "native_tool":
            if tool_registry.get_definition(step.tool_name) is None:
                raise ValueError("Unknown native tool")
        elif step.tool_name not in fixed[step.kind]:
            raise ValueError("Unknown tool for execution kind")
        def check(value):
            if isinstance(value, dict):
                if "from_step" in value:
                    if set(value) != {"from_step"} or value["from_step"] not in step.dependencies:
                        raise ValueError("Input references must name direct dependencies")
                else:
                    for item in value.values():
                        check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
        check(step.inputs)
    return plan


def fallback_plan(task_id, request):
    def step(id, kind, deps=(), tool=None, **inputs):
        return PlanStep(id=id, title=id.replace("-", " ").capitalize(), kind=kind,
                        dependencies=list(deps), tool_name=tool, inputs=inputs)
    ref = lambda id: {"from_step": id}
    if request.flow == "coding":
        # A disclosed example program, never an inferred implementation of arbitrary objectives.
        code = "principal, rate, years = 1000, 0.05, 3\nresult = principal * (1 + rate) ** years\nassert round(result, 2) == 1157.63\nprint(round(result, 2))\n"
        steps = [
            step("prepare-code", "native_tool", tool="file.write",
                 path=f"outputs/tasks/{task_id}/calculation.py", content=code),
            step("run-python", "sandbox", ["prepare-code"], "python", code=code),
            step("verify-result", "llm", ["run-python"], purpose="verification", source=ref("run-python")),
        ]
    else:
        steps = [
            step("read-report", "native_tool", tool="file.read", path=request.input_path),
            step("analyze-findings", "llm", ["read-report"], purpose="findings", source=ref("read-report")),
            step("risk-review", "llm", ["read-report"], purpose="risk review", source=ref("read-report")),
        ]
        deps = ["analyze-findings", "risk-review"]
        if request.flow == "mcp":
            steps.append(step("search-policy", "mcp", ["read-report"], "search_internal_docs", query="inspection approval"))
            deps.append("search-policy")
        steps.extend([
            step("draft-note", "llm", deps, purpose="approval note", sources=[ref(d) for d in deps]),
            step("save-draft", "native_tool", ["draft-note"], "file.write",
                 path=f"outputs/tasks/{task_id}/approval-note.txt", content=ref("draft-note")),
            step("create-word", "artifact", ["draft-note", "save-draft"], "document.create_word",
                 title="Approval note", content=ref("draft-note")),
        ])
    return validate_tools(ExecutionPlan(task_id=task_id, objective=request.objective,
                          planner_mode="deterministic_fallback", steps=steps))


class Planner:
    def __init__(self, complete=local_completion):
        self.complete = complete

    async def plan(self, task_id, request, trace):
        trace.emit("plan.started", "Planner started", "running")
        if not request.demo_mode:
            trace.emit("model.started", "Local planner model", "running")
            try:
                example = fallback_plan(task_id, request).model_dump(mode="json")
                prompt = (
                    "Return only an ExecutionPlan JSON object. Use pending status, at most 32 steps, "
                    "unique IDs and acyclic dependencies. Input references are {\"from_step\": \"direct-dependency-id\"}. "
                    "Allowed kinds/tools and input contracts are illustrated by this plan. "
                    "Keep file paths relative to workspace. No external endpoints. "
                    "Use planner_mode local_model. Adapt the plan to the objective.\n"
                    + json.dumps(example) + "\nSchema:\n" + json.dumps(ExecutionPlan.model_json_schema())
                )
                async with asyncio.timeout(settings.speed_model_timeout):
                    raw = await self.complete(prompt)
                plan = ExecutionPlan.model_validate_json(raw)
                if plan.task_id != task_id or plan.objective != request.objective:
                    raise ValueError("Planner changed task identity")
                plan.planner_mode = "local_model"
                validate_tools(plan)
                trace.emit("model.completed", "Planner response validated")
                trace.emit("plan.created", f"Planner created {len(plan.steps)} steps")
                return plan
            except Exception:
                trace.emit("model.failed", "Local planner unavailable or invalid", "failed")
        plan = fallback_plan(task_id, request)
        trace.emit("plan.fallback", "Deterministic example plan", is_mock=True,
                   summary="Template workflow; not AI-generated.",
                   metadata={"planner_mode": plan.planner_mode})
        trace.emit("plan.created", f"Planner created {len(plan.steps)} steps", is_mock=True)
        return plan
