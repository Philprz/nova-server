# mcp_app.py
from mcp.server.fastmcp import FastMCP

# single source-of-truth for your MCP server
mcp = FastMCP("nova_middleware")
