import logging
import os
from pathlib import Path

import httpx
import yaml

from app.routing.models import ModelConfig

logger = logging.getLogger("speed.models")
ROOT = Path(__file__).resolve().parents[3]


class ModelRouter:
    def __init__(self, config_path: str | None = None):
        self.config_path = Path(config_path or os.getenv("SPEED_MODELS_CONFIG", ROOT / "config/models/models.yaml"))
        with self.config_path.open(encoding="utf-8") as file:
            config = yaml.safe_load(file)
        self.models = {}
        for name, value in config["models"].items():
            values = dict(value)
            for field in ("model", "endpoint", "device"):
                variable = values.pop(f"{field}_env", None)
                if variable and os.getenv(variable):
                    values[field] = os.environ[variable]
            path = Path(values["model"]).expanduser()
            values["model"] = str(path if path.is_absolute() else ROOT / path)
            self.models[name] = ModelConfig(name=name, **values)

    async def health(self, model: ModelConfig) -> dict:
        state = {"id": model.name, "purpose": model.capabilities, "kind": model.kind,
                 "endpoint": model.endpoint, "artifact_exists": Path(model.model).exists()}
        if model.kind == "in_process":
            from app.task.analyzer import TaskAnalyzer
            state["artifact_exists"] = Path(model.model).is_dir()
            state["availability"] = ("missing_artifact" if not state["artifact_exists"]
                                     else TaskAnalyzer.status)
        else:
            try:
                async with httpx.AsyncClient(timeout=2, trust_env=False, follow_redirects=False) as client:
                    response = await client.get(f"{model.endpoint.rstrip('/')}/health")
                    response.raise_for_status()
                    if response.json().get("status") != "ok":
                        raise ValueError("Model is not ready")
                    models = await client.get(f"{model.endpoint.rstrip('/')}/v1/models")
                    models.raise_for_status()
                    available = {entry["id"] for entry in models.json()["data"]}
                    state["availability"] = ("healthy" if available.intersection({model.model, model.model_id})
                                             else "model_mismatch")
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
                state["availability"] = "unavailable"
        logger.info("model health id=%s purpose=%s endpoint=%s availability=%s",
                    model.name, model.capabilities, model.endpoint, state["availability"])
        return state

    async def route(self, task_type: str) -> ModelConfig | None:
        for model in self.models.values():
            if model.kind == "llama_server" and task_type in model.capabilities:
                if (await self.health(model))["availability"] == "healthy":
                    logger.info("router selected model=%s purpose=%s", model.name, task_type)
                    return model
        logger.warning("router unavailable purpose=%s", task_type)
        return None

    def get(self, model_name: str) -> ModelConfig | None:
        return self.models.get(model_name)
