from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    CODING = "coding"
    GENERAL = "general"
    REASONING = "reasoning"


class TaskAnalysis(BaseModel):
    mode: Literal["laya", "deterministic_fallback"] = "laya"
    task_type: TaskType
    confidence: float | None = Field(default=None, ge=0, le=1)
