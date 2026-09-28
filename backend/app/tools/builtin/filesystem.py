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
        "path": str(target.relative_to(filesystem_scope.workspace)),
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

    if target.stat().st_size > 1_000_000:
        raise ValueError("Text files are limited to 1 MB.")
    content = target.read_text(encoding="utf-8")

    return {
        "path": str(target.relative_to(filesystem_scope.workspace)),
        "content": content,
        "size": target.stat().st_size,
    }


def write_file(path: str, content: str) -> dict:
    target = filesystem_scope.resolve_workspace_path(path)
    if len(content.encode("utf-8")) > 1_000_000:
        raise ValueError("Text files are limited to 1 MB.")
    created = not target.exists()
    old = read_file(path)["content"] if not created else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    target = filesystem_scope.resolve_workspace_path(path)
    target.write_text(content, encoding="utf-8")
    from difflib import ndiff
    changes = list(ndiff(old.splitlines(), content.splitlines()))
    return {
        "path": str(target.relative_to(filesystem_scope.workspace)),
        "size": target.stat().st_size,
        "created": created,
        "lines_added": sum(line.startswith("+ ") for line in changes),
        "lines_removed": sum(line.startswith("- ") for line in changes),
    }
