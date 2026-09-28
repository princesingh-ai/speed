"""Approved fixture-only MCP server. Nothing starts on import."""
from pathlib import Path
from mcp.server import MCPServer

server = MCPServer("SPEED local fixtures")
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "internal_docs"


@server.tool()
def calculator(a: float, b: float, operation: str = "add") -> dict:
    """Perform one arithmetic operation without evaluating code."""
    if operation == "add":
        value = a + b
    elif operation == "multiply":
        value = a * b
    else:
        raise ValueError("Supported operations: add, multiply")
    return {"value": value}


@server.tool()
def search_internal_docs(query: str) -> dict:
    """Keyword search over bundled, non-confidential demonstration policies."""
    words = query[:500].lower().split()
    documents = []
    for path in sorted(FIXTURES.glob("*.txt")):
        if path.is_symlink():
            continue
        content = path.read_text(encoding="utf-8")[:4000]
        if any(word in content.lower() for word in words):
            documents.append({"name": path.name, "text": content})
    return {"documents": documents[:10], "result_count": len(documents[:10])}


if __name__ == "__main__":
    server.run(transport="stdio")
