import asyncio
import logging
import threading

from app.routing.model_router import ModelRouter
from app.task.models import TaskAnalysis, TaskType

logger = logging.getLogger("speed.models")


class RoutingService:
    def __init__(self):
        self.task_analyzer = None
        self.model_router = ModelRouter()
        self.lock = threading.Lock()

    def analyze(self, message):
        from app.task.analyzer import TaskAnalyzer
        with self.lock:
            try:
                if self.task_analyzer is None:
                    config = self.model_router.get("laya")
                    if config is None or TaskAnalyzer.status == "failed":
                        raise RuntimeError("Laya unavailable")
                    self.task_analyzer = TaskAnalyzer(config)
                return self.task_analyzer.analyze(message)
            except Exception:
                if self.task_analyzer is not None:
                    TaskAnalyzer.status = "failed"
                    self.task_analyzer = None
                logger.warning("task analysis fallback=deterministic_general; Laya unavailable or failed")
                return TaskAnalysis(task_type=TaskType.GENERAL, mode="deterministic_fallback")

    async def route(self, message: str):
        analysis = await asyncio.to_thread(self.analyze, message)
        return analysis, await self.model_router.route(analysis.task_type.value)
