"""
Tools module for agent template.

Provides:
- MCP client for tool execution
- A2A client for inter-agent communication
- IO Agent client for human UI updates
"""

from .mcp_client import MCPToolClient, get_mcp_tools, get_filtered_tools
from .a2a_client import A2AClient, get_a2a_client
from .io_agent_client import IOAgentClient, get_io_client, configure_io_client

__all__ = [
    "MCPToolClient",
    "get_mcp_tools",
    "get_filtered_tools",
    "A2AClient",
    "get_a2a_client",
    "IOAgentClient",
    "get_io_client",
    "configure_io_client",
]
