"""
MCP (Model Context Protocol) Client Implementation

Provides async client for calling MCP servers to execute tools.
Supports tool filtering by stage, sanitization, and caching.
"""

import os
import re
from typing import Any, Optional

import structlog
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool

logger = structlog.get_logger(__name__)


class MCPToolClient:
    """
    MCP Tool Client for executing tools via MCP servers.

    Features:
    - Tool discovery and caching
    - Tool name sanitization (for LangChain compatibility)
    - Stage-based tool filtering
    - Blocked tool filtering
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        server_type: str = "sse",
        timeout: int = 300,
        blocked_tools: list[str] = None,
    ):
        """
        Initialize MCP client.

        Args:
            server_url: MCP server URL (defaults to MCP_SERVER_URL env var)
            server_type: Server type ('sse' or 'stdio')
            timeout: Request timeout in seconds
            blocked_tools: List of tool names to block
        """
        self.server_url = server_url or os.getenv("MCP_SERVER_URL", "http://mcp-server:5000/sse")
        self.server_type = server_type
        self.timeout = timeout
        self.blocked_tools = set(blocked_tools or [])

        self._client: Optional[MultiServerMCPClient] = None
        self._tools_cache: Optional[list[BaseTool]] = None
        self._original_names: dict[str, str] = {}  # sanitized -> original

    def _get_mcp_config(self) -> dict:
        """Get MCP server configuration"""
        return {
            "network_tools": {
                "url": self.server_url,
                "transport": self.server_type,
            }
        }

    def _sanitize_tool_name(self, name: str) -> str:
        """
        Sanitize tool name for LangChain compatibility.

        LangChain requires tool names to match: [a-zA-Z0-9_-]+
        """
        # Replace invalid characters with underscores
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        # Remove consecutive underscores
        sanitized = re.sub(r"_+", "_", sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")
        return sanitized

    async def get_tools(self, refresh: bool = False) -> list[BaseTool]:
        """
        Get all available MCP tools.

        Args:
            refresh: Force refresh of tool cache

        Returns:
            List of LangChain BaseTool objects
        """
        if self._tools_cache and not refresh:
            return self._tools_cache

        logger.info("Fetching MCP tools", server_url=self.server_url)

        try:
            self._client = MultiServerMCPClient(self._get_mcp_config())
            raw_tools = await self._client.get_tools()

            sanitized_tools = []
            self._original_names = {}

            for tool in raw_tools:
                original_name = tool.name

                # Skip blocked tools
                if original_name in self.blocked_tools:
                    logger.debug("Skipping blocked tool", tool_name=original_name)
                    continue

                # Sanitize name
                sanitized_name = self._sanitize_tool_name(original_name)

                if sanitized_name != original_name:
                    self._original_names[sanitized_name] = original_name
                    tool.name = sanitized_name
                    logger.debug(
                        "Sanitized tool name",
                        original=original_name,
                        sanitized=sanitized_name,
                    )

                sanitized_tools.append(tool)

            self._tools_cache = sanitized_tools
            logger.info("Loaded MCP tools", count=len(sanitized_tools))
            return sanitized_tools

        except Exception as e:
            logger.error("Failed to fetch MCP tools", error=str(e))
            raise

    async def get_filtered_tools(
        self,
        allowed_tools: list[str] = None,
        excluded_tools: list[str] = None,
        tool_prefix: str = None,
    ) -> list[BaseTool]:
        """
        Get filtered subset of MCP tools.

        Args:
            allowed_tools: Only include these tools (exact names)
            excluded_tools: Exclude these tools
            tool_prefix: Only include tools starting with this prefix

        Returns:
            Filtered list of tools
        """
        all_tools = await self.get_tools()
        filtered = []

        for tool in all_tools:
            name = tool.name

            # Check allowed list
            if allowed_tools and name not in allowed_tools:
                continue

            # Check excluded list
            if excluded_tools and name in excluded_tools:
                continue

            # Check prefix
            if tool_prefix and not name.startswith(tool_prefix):
                continue

            filtered.append(tool)

        logger.info(
            "Filtered MCP tools",
            total=len(all_tools),
            filtered=len(filtered),
            allowed=allowed_tools,
            excluded=excluded_tools,
            prefix=tool_prefix,
        )
        return filtered

    async def get_tools_by_stage(
        self,
        stage_config: dict[str, list[str]],
        stage_name: str,
    ) -> list[BaseTool]:
        """
        Get tools for a specific workflow stage.

        Args:
            stage_config: Dict mapping stage names to tool lists
            stage_name: Name of the stage

        Returns:
            Tools configured for that stage
        """
        if stage_name not in stage_config:
            logger.warning("Unknown stage, returning all tools", stage=stage_name)
            return await self.get_tools()

        allowed_tools = stage_config[stage_name]
        if not allowed_tools:
            # Empty list means all tools
            return await self.get_tools()

        return await self.get_filtered_tools(allowed_tools=allowed_tools)

    def get_original_name(self, sanitized_name: str) -> str:
        """Get original tool name from sanitized name"""
        return self._original_names.get(sanitized_name, sanitized_name)

    async def close(self) -> None:
        """Close MCP client connection"""
        if self._client:
            # MultiServerMCPClient doesn't have explicit close
            self._client = None
            self._tools_cache = None


# Module-level functions for convenience

async def get_mcp_tools(
    server_url: Optional[str] = None,
    blocked_tools: list[str] = None,
) -> list[BaseTool]:
    """
    Get all MCP tools (convenience function).

    Args:
        server_url: MCP server URL
        blocked_tools: Tools to block

    Returns:
        List of tools
    """
    client = MCPToolClient(server_url=server_url, blocked_tools=blocked_tools)
    return await client.get_tools()


async def get_filtered_tools(
    allowed_tools: list[str] = None,
    excluded_tools: list[str] = None,
    server_url: Optional[str] = None,
) -> list[BaseTool]:
    """
    Get filtered MCP tools (convenience function).

    Args:
        allowed_tools: Only include these tools
        excluded_tools: Exclude these tools
        server_url: MCP server URL

    Returns:
        Filtered list of tools
    """
    client = MCPToolClient(server_url=server_url)
    return await client.get_filtered_tools(
        allowed_tools=allowed_tools,
        excluded_tools=excluded_tools,
    )
