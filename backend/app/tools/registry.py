from collections.abc import Callable

from app.tools.models import ToolDefinition


class ToolRegistry:
    def __init__(self):
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable] = {}

    def register(
        self,
        definition: ToolDefinition,
        handler: Callable,
    ) -> None:
        if definition.name in self._definitions:
            raise ValueError(
                f"Tool already registered: {definition.name}"
            )

        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    def get_definition(
        self,
        tool_name: str,
    ) -> ToolDefinition | None:
        return self._definitions.get(tool_name)

    def get_handler(
        self,
        tool_name: str,
    ) -> Callable | None:
        return self._handlers.get(tool_name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._definitions.values())


tool_registry = ToolRegistry()