import time
import uuid

from app.task.execution import ExecutionStatus, ExecutionTask


class TaskService:

    def __init__(self):
        self.tasks: dict[str, ExecutionTask] = {}

    def create_task(
        self,
        user_id: str,
        prompt: str,
    ) -> ExecutionTask:
        now = time.time()

        task = ExecutionTask(
            id=f"task_{uuid.uuid4().hex}",
            user_id=user_id,
            prompt=prompt,
            status=ExecutionStatus.CREATED,
            created_at=now,
        )

        self.tasks[task.id] = task

        return task

    def get_task(
        self,
        task_id: str,
    ) -> ExecutionTask | None:
        return self.tasks.get(task_id)

    def start_task(
        self,
        task_id: str,
    ) -> ExecutionTask | None:
        task = self.tasks.get(task_id)

        if task is None:
            return None

        task.status = ExecutionStatus.RUNNING
        task.started_at = time.time()

        return task

    def complete_task(
        self,
        task_id: str,
    ) -> ExecutionTask | None:
        task = self.tasks.get(task_id)

        if task is None:
            return None

        task.status = ExecutionStatus.COMPLETED
        task.completed_at = time.time()

        return task

    def fail_task(
        self,
        task_id: str,
        error: str,
    ) -> ExecutionTask | None:
        task = self.tasks.get(task_id)

        if task is None:
            return None

        task.status = ExecutionStatus.FAILED
        task.failed_at = time.time()
        task.error = error

        return task


task_service = TaskService()