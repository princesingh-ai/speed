import laya

from app.task.models import TaskAnalysis, TaskType


class TaskAnalyzer:
    def __init__(self):
        self.model = laya.load(
            "/home/prince/projects/speed/models/laya",
            device="cuda",
        )

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