from app.tools.builtin.filesystem_scope import filesystem_scope


def list_files(path: str = ".") -> dict:
    target = filesystem_scope.resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(
            f"Path does not exist: {target}"
        )

    if not target.is_dir():
        raise NotADirectoryError(
            f"Not a directory: {target}"
        )

    entries = []

    for entry in sorted(
        target.iterdir(),
        key=lambda p: p.name.lower(),
    ):
        entries.append(
            {
                "name": entry.name,
                "type": (
                    "directory"
                    if entry.is_dir()
                    else "file"
                ),
            }
        )

    return {
        "path": str(target),
        "entries": entries,
    }

def read_file(path: str) -> dict:
    target = filesystem_scope.resolve_workspace_path(path)

    if not target.exists():
        raise FileNotFoundError(
            f"Path does not exist: {target}"
        )

    if not target.is_file():
        raise IsADirectoryError(
            f"Not a file: {target}"
        )

    content = target.read_text(encoding="utf-8")

    return {
        "path": str(target),
        "content": content,
    }