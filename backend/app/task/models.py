from enum import Enum

from pydantic import BaseModel


class TaskType(str, Enum):
    CODING = "coding"
    GENERAL = "general"
    REASONING = "reasoning"


class TaskAnalysis(BaseModel):
    task_type: TaskType