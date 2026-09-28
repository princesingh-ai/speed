from fastapi import APIRouter, Depends

from app.security.dependencies import get_current_user
from app.security.models import User
from app.tools.registry import tool_registry
from app.api.schemas.tools import ExecuteToolRequest
from app.tools.models import ToolRequest
from app.tools.runtime import tool_runtime

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


@router.get("")
async def list_tools(
    user: User = Depends(get_current_user),
):
    return {
        "tools": tool_registry.list_tools(),
    }

@router.post("/execute")
async def execute_tool(
    request: ExecuteToolRequest,
    user: User = Depends(get_current_user),
):
    tool_request = ToolRequest(
        tool_name=request.tool_name,
        task_id=request.task_id,
        arguments=request.arguments,
    )

    return tool_runtime.execute(
        user=user,
        request=tool_request,
        consent_id=request.consent_id,
    )