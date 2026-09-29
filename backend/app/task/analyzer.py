import logging
from pathlib import Path

from app.task.models import TaskAnalysis, TaskType


class TaskAnalyzer:
    status = "not_loaded"

    def __init__(self, config):
        if not Path(config.model).is_dir():
            TaskAnalyzer.status = "missing_artifact"
            raise FileNotFoundError("Laya configured but model artifact not found")
        TaskAnalyzer.status = "loading"
        logger = logging.getLogger("speed.models")
        logger.info("Laya analyzer loading device=%s", config.device)
        try:
            import laya
            self.model = laya.load(config.model, device=config.device)
        except Exception:
            TaskAnalyzer.status = "failed"
            logger.warning("Laya analyzer load failed")
            raise
        TaskAnalyzer.status = "healthy"
        logger.info("Laya analyzer ready in backend process")

    def analyze(self, message: str) -> TaskAnalysis:
        questions = {
            "task": {
                "type": "choice",
                "instructions": "What is the primary task type?",
                "criteria": {
                    "coding": "Writing, debugging, explaining, or modifying computer code.",
                    "reasoning": "Complex logical, mathematical, analytical, or multi-step reasoning.",
                    "general": "General conversation, explanation, knowledge questions, or tasks that do not fit the other categories.",
                },
            }
        }

        result = self.model.predict(
            message,
            questions,
        )

        answer = result["answers"]["task"]

        return TaskAnalysis(
            task_type=TaskType(answer["choice"]),
            confidence=answer["confidence"],
        )
