from app.routing.model_router import ModelRouter
from app.task.analyzer import TaskAnalyzer


class RoutingService:
    def __init__(self):
        self.task_analyzer = TaskAnalyzer()
        self.model_router = ModelRouter()

    def route(self, message: str):
        analysis = self.task_analyzer.analyze(message)

        model = self.model_router.route(analysis.task_type.value)

        return analysis, model