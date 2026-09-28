from app.security.gateway import security_gateway
from app.security.models import User
from app.tools.models import ToolRequest, ToolResult, ToolStatus
from app.tools.registry import tool_registry
from app.orchestration.events import current_trace
from time import perf_counter


class ToolRuntime:

    def execute(
        self,
        *,
        user: User,
        request: ToolRequest,
        consent_id: str | None = None,
    ) -> ToolResult:

        definition = tool_registry.get_definition(request.tool_name)

        if definition is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                tool_name=request.tool_name,
                task_id=request.task_id,
                error=f"Unknown tool: {request.tool_name}",
            )

        decision = security_gateway.authorize(
            user=user,
            task_id=request.task_id,
            permission=definition.permission,
            scope=definition.scope,
            resource=request.arguments.get("path", "/"),
            reason=f"Tool execution: {request.tool_name}",
            consent_id=consent_id,
        )

        if not decision.allowed:
            return ToolResult(
                status=ToolStatus.DENIED,
                tool_name=request.tool_name,
                task_id=request.task_id,
                error=decision.reason,
            )

        if decision.requires_consent:
            return ToolResult(
                status=ToolStatus.DENIED,
                tool_name=request.tool_name,
                task_id=request.task_id,
                error="Tool execution requires user consent.",
            )

        handler = tool_registry.get_handler(request.tool_name)

        if handler is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                tool_name=request.tool_name,
                task_id=request.task_id,
                error=f"No handler registered for tool: {request.tool_name}",
            )

        trace = current_trace.get()
        started = perf_counter()
        if trace:
            trace.emit("tool.started", request.tool_name, "running",
                       metadata={"tool_name": request.tool_name})
        try:
            result = handler(**request.arguments)

            if trace:
                metadata = {key: value for key, value in result.items() if key in {
                    "path", "size", "created", "lines_added", "lines_removed"}}
                if request.tool_name.startswith("file."):
                    event_type = request.tool_name
                    if request.tool_name == "file.write":
                        event_type = "file.created" if result.get("created") else "file.updated"
                    trace.emit(event_type, f"{event_type} {result.get('path', '')}",
                               metadata=metadata)
                trace.emit("tool.completed", request.tool_name,
                           duration_ms=int((perf_counter() - started) * 1000))

            return ToolResult(
                status=ToolStatus.SUCCESS,
                tool_name=request.tool_name,
                task_id=request.task_id,
                result=result,
            )

        except PermissionError as exc:
            if trace:
                trace.emit("tool.failed", "File access denied", "failed")
            return ToolResult(
                status=ToolStatus.DENIED,
                tool_name=request.tool_name,
                task_id=request.task_id,
                error=str(exc),
            )

        except Exception as exc:
            if trace:
                trace.emit("tool.failed", "Tool execution failed", "failed")
            return ToolResult(
                status=ToolStatus.ERROR,
                tool_name=request.tool_name,
                task_id=request.task_id,
                error=str(exc),
            )


tool_runtime = ToolRuntime()
