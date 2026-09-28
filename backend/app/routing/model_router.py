from pathlib import Path

import yaml

from app.routing.models import ModelConfig


class ModelRouter:
    def __init__(self, config_path: str = "config/models/models.yaml"):
        self.config_path = Path(config_path)

        with self.config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

        self.models = {
            name: ModelConfig(name=name, **model_config)
            for name, model_config in config["models"].items()}

    def route(self, task_type: str) -> ModelConfig | None:

        for model in self.models.values():
            if task_type in model.capabilities:
                return model
        return None

    def get(self, model_name: str) -> ModelConfig | None:
        return self.models.get(model_name)