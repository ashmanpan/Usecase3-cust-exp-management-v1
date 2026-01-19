"""Tunnel Provisioning Agent Main Entry Point - Port 8004"""
import asyncio, os, sys
from typing import Any, Optional
import structlog, uvicorn
from dotenv import load_dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from agent_template.config_loader import load_config
from agent_template.api.server import A2ATaskServer
from agent_template.tools.mcp_client import MCPToolClient
from agent_template.tools.a2a_client import A2AClient, configure_a2a_client
from .workflow import TunnelProvisioningWorkflow

load_dotenv()
structlog.configure(processors=[structlog.stdlib.filter_by_level, structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level, structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.TimeStamper(fmt="iso"), structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info, structlog.processors.UnicodeDecoder(),
    structlog.processors.JSONRenderer() if os.getenv("LOG_FORMAT", "json") == "json" else structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.stdlib.BoundLogger, context_class=dict, logger_factory=structlog.stdlib.LoggerFactory(), cache_logger_on_first_use=True)
logger = structlog.get_logger(__name__)

class TunnelProvisioningRunner:
    def __init__(self, config_path: Optional[str] = None):
        self.config = load_config(config_path or os.path.join(os.path.dirname(__file__), "config.yaml"))
        self._workflow: Optional[TunnelProvisioningWorkflow] = None
        self._server: Optional[A2ATaskServer] = None

    async def initialize(self) -> None:
        logger.info("Initializing Tunnel Provisioning agent", name=self.config.agent.name)
        self._workflow = TunnelProvisioningWorkflow(agent_name=self.config.agent.name, agent_version=self.config.agent.version,
            max_iterations=self.config.workflow.max_iterations, stage_tools=self.config.workflow.stages)
        self._workflow.compile()
        logger.info("Tunnel Provisioning agent initialized")

    async def execute_workflow(self, task_id: str, task_type: str, incident_id: Optional[str] = None,
                               payload: dict[str, Any] = None, correlation_id: Optional[str] = None) -> dict[str, Any]:
        if self._workflow is None: raise RuntimeError("Workflow not initialized")
        return await self._workflow.execute(task_id, task_type, incident_id, payload, correlation_id)

    def create_server(self) -> A2ATaskServer:
        self._server = A2ATaskServer(agent_name=self.config.agent.name, agent_version=self.config.agent.version,
            agent_description=self.config.agent.description, workflow_executor=self.execute_workflow,
            supported_task_types=self.config.a2a.capabilities, tags=[self.config.agent.type])
        return self._server

    def run(self) -> None:
        asyncio.run(self.initialize())
        server = self.create_server()
        logger.info("Starting Tunnel Provisioning A2A server", port=self.config.a2a.port)
        uvicorn.run(server.app, host=self.config.a2a.host, port=self.config.a2a.port, log_level=self.config.observability.log_level.lower())

def main(): TunnelProvisioningRunner().run()
if __name__ == "__main__": main()
