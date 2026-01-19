"""
Agent Template Package

A reusable template for building LangGraph-based agents with A2A protocol support.

Quick Start:
    1. Copy this template to create your agent
    2. Create your workflow by extending BaseWorkflow
    3. Define your nodes and graph structure
    4. Configure your agent in config.yaml
    5. Run with: python -m your_agent.main

Example:
    from agent_template import BaseWorkflow, run_agent
    from agent_template.schemas.state import WorkflowState
    from langgraph.graph import StateGraph, START, END

    class MyWorkflow(BaseWorkflow):
        def get_state_class(self):
            return WorkflowState

        def build_graph(self, graph: StateGraph):
            # Add your nodes and edges
            pass

    if __name__ == "__main__":
        run_agent(MyWorkflow)
"""

from .workflow import BaseWorkflow
from .main import run_agent, AgentRunner
from .config_loader import load_config, get_config, Config

__version__ = "1.0.0"

__all__ = [
    "BaseWorkflow",
    "run_agent",
    "AgentRunner",
    "load_config",
    "get_config",
    "Config",
]
