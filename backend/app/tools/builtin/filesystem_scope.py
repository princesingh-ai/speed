from pathlib import Path
from app.core.config import settings


class FilesystemScope:

    def __init__(self, workspace: str):
        self.workspace = Path(workspace).expanduser().resolve()

    def resolve_workspace_path(self, path: str) -> Path:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            raise PermissionError("Use a relative workspace path without traversal.")
        requested = (self.workspace / relative).resolve()

        try:
            requested.relative_to(self.workspace)
        except ValueError:
            raise PermissionError(
                f"Path is outside the allowed workspace: {requested}"
            )

        return requested


filesystem_scope = FilesystemScope(str(settings.speed_workspace))
