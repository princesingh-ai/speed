from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Literal
from pydantic import Field

class Settings(BaseSettings):
    llama_host: str = "127.0.0.1"
    llama_port: int = 8080

    speed_jwt_secret: str
    speed_demo_auth: bool = False
    speed_workspace: Path = Path(__file__).resolve().parents[3]
    speed_sandbox_mode: Literal["disabled", "mock", "docker"] = "disabled"
    speed_sandbox_image: str = "python:3.13-slim"
    speed_step_concurrency: int = Field(default=3, ge=1, le=8)
    speed_model_timeout: float = Field(default=30, gt=0, le=120)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

settings = Settings()
