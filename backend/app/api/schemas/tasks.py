from pydantic import BaseModel

from app.task.execution import ExecutionStatus


class CreateTaskRequest(BaseModel):
    prompt: str


class TaskResponse(BaseModel):
    id: str
    user_id: str
    prompt: str
    status: ExecutionStatus

    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    failed_at: float | None = None
    error: str | None = None