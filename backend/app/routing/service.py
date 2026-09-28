from app.routing.model_router import ModelRouter


class RoutingService:
    def __init__(self):
        self.task_analyzer = None
        self.model_router = ModelRouter()

    def route(self, message: str):
        if self.task_analyzer is None:
            from app.task.analyzer import TaskAnalyzer
            self.task_analyzer = TaskAnalyzer()
        analysis = self.task_analyzer.analyze(message)

        model = self.model_router.route(analysis.task_type.value)

        return analysis, model
