"""
Tools module for agent template.

Provides:
- MCP client for tool execution
- A2A client for inter-agent communication
"""

from .mcp_client import MCPToolClient, get_mcp_tools, get_filtered_tools
from .a2a_client import A2AClient, get_a2a_client

__all__ = [
    "MCPToolClient",
    "get_mcp_tools",
    "get_filtered_tools",
    "A2AClient",
    "get_a2a_client",
]
