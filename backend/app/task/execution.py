from enum import Enum

from pydantic import BaseModel


class ExecutionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionTask(BaseModel):
    id: str
    user_id: str
    prompt: str

    status: ExecutionStatus = ExecutionStatus.CREATED

    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    failed_at: float | None = None

    error: str | None = None