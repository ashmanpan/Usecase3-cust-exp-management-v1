"""
Orchestrator Agent Main Entry Point

Supervisor agent that coordinates the entire protection workflow.
"""

import os
import sys

# Add parent directory for agent_template imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent_template.main import run_agent
from agent_template.config_loader import load_config

from workflow import OrchestratorWorkflow


def main():
    """Run the Orchestrator Agent"""
    # Load configuration
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    config = load_config(config_path)

    # Build agent registry from config
    agent_registry = {}
    if hasattr(config, "agents"):
        agents_config = config.agents if isinstance(config.agents, dict) else {}
        for agent_name, agent_config in agents_config.items():
            if isinstance(agent_config, dict) and "url" in agent_config:
                agent_registry[agent_name] = agent_config["url"]

    # Create workflow with agent registry
    class ConfiguredOrchestratorWorkflow(OrchestratorWorkflow):
        def __init__(self, **kwargs):
            super().__init__(
                agent_registry=agent_registry,
                **kwargs,
            )

    # Run the agent
    run_agent(ConfiguredOrchestratorWorkflow, config_path)


if __name__ == "__main__":
    main()
