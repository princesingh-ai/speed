from enum import Enum

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    CODING = "coding"
    GENERAL = "general"
    REASONING = "reasoning"


class TaskAnalysis(BaseModel):
    task_type: TaskType
    confidence: float | None = Field(default=None, ge=0, le=1)
