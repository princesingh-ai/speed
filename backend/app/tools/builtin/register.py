from app.security.models import Permission
from app.security.policy import ResourceScope
from app.tools.builtin.filesystem import list_files, read_file
from app.tools.models import ToolDefinition
from app.tools.registry import tool_registry


def register_builtin_tools() -> None:
    tool_registry.register(
        ToolDefinition(
            name="file.list",
            description="List files and directories in an allowed location.",
            permission=Permission.FILE_LIST,
            scope=ResourceScope.WORKSPACE,
        ),
        list_files,
    )

    tool_registry.register(
    ToolDefinition(
        name="file.read",
        description="Read a text file from an allowed location.",
        permission=Permission.FILE_READ,
        scope=ResourceScope.WORKSPACE,
    ),
    read_file,
)