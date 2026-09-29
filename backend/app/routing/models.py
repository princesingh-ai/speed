from typing import Literal
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, model_validator


class ModelConfig(BaseModel):
    name: str
    kind: Literal["llama_server", "in_process"] = "llama_server"
    endpoint: str | None = None
    model: str
    capabilities: list[str]
    device: str = "cuda"

    @property
    def model_id(self) -> str:
        return Path(self.model).name

    @model_validator(mode="after")
    def local_endpoint(self):
        if self.kind == "llama_server":
            url = urlsplit(self.endpoint or "")
            if (url.scheme not in {"http", "https"}
                    or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                    or url.username or url.password or url.query or url.fragment
                    or url.path not in {"", "/"} or url.port == 0):
                raise ValueError("Model endpoint must be a loopback HTTP origin")
        elif self.endpoint is not None:
            raise ValueError("In-process analyzers have no endpoint")
        return self
