from enum import Enum

from pydantic import BaseModel


class Permission(str, Enum):
    CHAT_USE = "chat.use"

    FILE_LIST = "file.list"
    FILE_READ = "file.read"
    FILE_WRITE = "file.write"
    FILE_DELETE = "file.delete"
    FILE_SCAN_DEVICE = "file.scan_device"

    SANDBOX_CREATE = "sandbox.create"
    SANDBOX_EXECUTE = "sandbox.execute"

    DOCUMENT_READ = "document.read"
    DOCUMENT_CREATE = "document.create"

    AGENT_EXECUTE = "agent.execute"
    AGENT_SPAWN = "agent.spawn"

    MCP_USE = "mcp.use"

    NETWORK_INTERNAL = "network.internal"
    NETWORK_EXTERNAL = "network.external"


class User(BaseModel):
    id: str
    username: str
    password_hash: str
    roles: list[str]


class Role(BaseModel):
    name: str
    permissions: set[Permission]