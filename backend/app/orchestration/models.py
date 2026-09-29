from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


Status = Literal["pending", "ready", "running", "waiting", "completed", "failed", "blocked"]
Kind = Literal["llm", "native_tool", "sandbox", "mcp", "artifact"]


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    kind: Kind
    dependencies: list[str] = Field(default_factory=list, max_length=32)
    tool_name: str | None = None
    inputs: dict = Field(default_factory=dict)
    expected_output: str = Field(default="", max_length=300)
    status: Status = "pending"


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    objective: str = Field(max_length=8000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    planner_mode: Literal["local_model", "deterministic_fallback"]
    steps: list[PlanStep] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_graph(self):
        ids = {step.id for step in self.steps}
        if len(ids) != len(self.steps):
            raise ValueError("Duplicate step IDs")
        for step in self.steps:
            if step.id in step.dependencies or not set(step.dependencies) <= ids:
                raise ValueError("Invalid dependency")
            if len(set(step.dependencies)) != len(step.dependencies):
                raise ValueError("Duplicate dependency")
        done = set()
        while len(done) < len(ids):
            ready = {s.id for s in self.steps if s.id not in done and set(s.dependencies) <= done}
            if not ready:
                raise ValueError("Cycle in plan")
            done.update(ready)
        return self


class TaskGraph:
    def __init__(self, plan: ExecutionPlan):
        self.plan = plan
        self.nodes = {s.id: s for s in plan.steps}

    def topological_order(self) -> list[str]:
        order = []
        while len(order) < len(self.nodes):
            ready = [s.id for s in self.plan.steps
                     if s.id not in order and set(s.dependencies) <= set(order)]
            if not ready:
                raise ValueError("Graph changed after validation")
            order.extend(ready)
        return order

    def ready(self) -> list[PlanStep]:
        return [s for s in self.plan.steps if s.status == "pending" and all(
            self.nodes[d].status == "completed" for d in s.dependencies)]

    def blocked(self) -> list[PlanStep]:
        return [s for s in self.plan.steps if s.status == "pending" and any(
            self.nodes[d].status in {"failed", "blocked"} for d in s.dependencies)]


class ExecutionEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    sequence: int
    task_id: str
    step_id: str | None = None
    parent_event_id: str | None = None
    agent_id: str = "speed"
    lane_id: int = 0
    event_type: str
    status: str
    title: str
    summary: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int | None = None
    metadata: dict = Field(default_factory=dict)
    is_mock: bool = False


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str = Field(min_length=1, max_length=8000)
    # Accept old clients' false value, but never select simulation through the API.
    demo_mode: Literal[False] = False
    flow: Literal["document", "mcp", "coding"] = "document"
    input_path: str = Field(default="fixtures/inspection-report.txt", max_length=500)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "changes_requested", "rejected"]
    comment: str = Field(default="", max_length=2000)


class ResultReview(BaseModel):
    status: Literal["pending", "approved", "changes_requested", "rejected"] = "pending"
    comment: str = ""
    reviewed_by: str | None = None
    reviewer_name: str | None = None
    reviewed_at: datetime | None = None
