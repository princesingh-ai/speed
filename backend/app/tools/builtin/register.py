from app.security.models import Permission
from app.security.policy import ResourceScope
from app.tools.builtin.filesystem import list_files, read_file, write_file
from app.tools.models import ToolDefinition
from app.tools.registry import tool_registry


def register_builtin_tools() -> None:
    for name, handler, permission in (
        ("file.list", list_files, Permission.FILE_LIST),
        ("file.read", read_file, Permission.FILE_READ),
        ("file.write", write_file, Permission.FILE_WRITE),
    ):
        if tool_registry.get_definition(name) is None:
            tool_registry.register(ToolDefinition(
                name=name, description=handler.__name__.replace("_", " "),
                permission=permission, scope=ResourceScope.WORKSPACE,
            ), handler)
