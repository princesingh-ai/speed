from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas.tasks import CreateTaskRequest, TaskResponse
from app.security.dependencies import get_current_user
from app.security.models import User
from app.task.service import task_service


router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["tasks"],
)


@router.post("", response_model=TaskResponse)
async def create_task(
    request: CreateTaskRequest,
    user: User = Depends(get_current_user),
):
    task = task_service.create_task(
        user_id=user.id,
        prompt=request.prompt,
    )

    return task


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    user: User = Depends(get_current_user),
):
    task = task_service.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found.",
        )

    if task.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Task belongs to another user.",
        )

    return task