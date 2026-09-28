from pathlib import Path


class FilesystemScope:

    def __init__(self, workspace: str):
        self.workspace = Path(workspace).expanduser().resolve()

    def resolve_workspace_path(self, path: str) -> Path:
        requested = Path(path).expanduser().resolve()

        try:
            requested.relative_to(self.workspace)
        except ValueError:
            raise PermissionError(
                f"Path is outside the allowed workspace: {requested}"
            )

        return requested


filesystem_scope = FilesystemScope(
    "/home/prince/projects/speed"
)