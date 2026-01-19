"""
API module for agent template.

Provides:
- A2A TaskServer for receiving tasks from other agents
- Health check endpoints
"""

from .server import A2ATaskServer, create_app

__all__ = ["A2ATaskServer", "create_app"]
