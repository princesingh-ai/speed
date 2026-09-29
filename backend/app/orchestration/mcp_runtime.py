import asyncio
import json
import sys
from pathlib import Path


def decode_result(result):
    """Accept an MCP object result in either supported content channel."""
    if result.is_error:
        raise RuntimeError("MCP tool failed")
    data = result.structured_content
    if data is None:
        blocks = getattr(result, "content", [])
        if len(blocks) != 1 or blocks[0].type != "text" or len(blocks[0].text) > 1_000_000:
            raise RuntimeError("MCP tool failed")
        try:
            data = json.loads(blocks[0].text)
        except (ValueError, RecursionError) as exc:
            raise RuntimeError("MCP tool failed") from exc
    if not isinstance(data, dict):
        raise RuntimeError("MCP tool failed")
    return data


class MCPRuntime:
    """Only the bundled stdio definition is approved; no user command or URL."""
    async def call(self, name, arguments, trace):
        trace.emit("mcp.started", f"MCP: {name}", "running", metadata={"tool_name": name})
        try:
            if name not in {"calculator", "search_internal_docs"}:
                raise ValueError("Unapproved MCP tool")
            from mcp import Client, StdioServerParameters
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[str(Path(__file__).with_name("demo_mcp.py"))],
                env={},
            )
            failure = None
            data = None
            async with asyncio.timeout(20):
                async with Client(parameters) as client:
                    discovered = await client.list_tools()
                    if name not in {tool.name for tool in discovered.tools}:
                        failure = ValueError("MCP tool not discovered")
                    else:
                        result = await client.call_tool(name, arguments)
                        try:
                            data = decode_result(result)
                        except RuntimeError as exc:
                            failure = exc
            # Exit the SDK task group normally before raising our mapped tool error.
            # Transport, protocol and cleanup exceptions retain their original types.
            if failure is not None:
                raise failure
            trace.emit("mcp.completed", f"MCP: {name} returned",
                       metadata={"result_count": data.get("result_count", 1)})
            return data
        except Exception:
            trace.emit("mcp.failed", f"MCP: {name} failed", "failed")
            raise
