from pydantic import BaseModel, Field


class ExecuteToolRequest(BaseModel):
    tool_name: str
    task_id: str
    arguments: dict = Field(default_factory=dict)
    consent_id: str | None = None