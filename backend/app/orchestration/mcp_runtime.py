import asyncio
import sys
from pathlib import Path


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
            async with asyncio.timeout(20):
                async with Client(parameters) as client:
                    discovered = await client.list_tools()
                    if name not in {tool.name for tool in discovered.tools}:
                        raise ValueError("MCP tool not discovered")
                    result = await client.call_tool(name, arguments)
                    if result.is_error or result.structured_content is None:
                        raise RuntimeError("MCP tool failed")
                    data = result.structured_content
            trace.emit("mcp.completed", f"MCP: {name} returned",
                       metadata={"result_count": data.get("result_count", 1)})
            return data
        except Exception:
            trace.emit("mcp.failed", f"MCP: {name} failed", "failed")
            raise
