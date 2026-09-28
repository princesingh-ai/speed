from pydantic import BaseModel

class ModelConfig(BaseModel):
    name: str
    endpoint: str
    model: str
    capabilities: list[str]