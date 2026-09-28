from enum import Enum

from pydantic import BaseModel, Field

from app.security.models import Permission
from app.security.policy import ResourceScope


class ToolStatus(str, Enum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


class ToolRequest(BaseModel):
    tool_name: str
    task_id: str
    arguments: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    status: ToolStatus
    tool_name: str
    task_id: str
    result: dict | None = None
    error: str | None = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    permission: Permission
    scope: ResourceScope