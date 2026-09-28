from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    llama_host: str = "127.0.0.1"
    llama_port: int = 8080

    speed_jwt_secret: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

settings = Settings()