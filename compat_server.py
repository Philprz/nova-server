# compat_server.py
from mcp.server.fastmcp import FastMCP

# Version compatible avec mode strict
mcp = FastMCP("compat_test", version="0.4.0")

@mcp.tool()
def echo(text: str) -> str:
    """Echo simple."""
    return text

if __name__ == "__main__":
    mcp.run(transport="stdio")