# Agent Template

A reusable template for building LangGraph-based agents with A2A (Agent-to-Agent) protocol support.

## Features

- **LangGraph Workflow**: StateGraph-based workflow orchestration
- **A2A Protocol**: Inter-agent communication via A2A TaskServer/TaskClient
- **MCP Integration**: Tool execution via Model Context Protocol
- **Checklist Pattern**: Multi-step verification with progress tracking
- **Configuration**: YAML-based configuration with env var substitution
- **Observability**: Structured logging, OpenTelemetry support
- **Health Checks**: Built-in /health and /ready endpoints

## Structure

```
agent_template/
├── __init__.py           # Package exports
├── main.py               # Entry point and AgentRunner
├── workflow.py           # BaseWorkflow class
├── config_loader.py      # Configuration loading
├── config.yaml           # Default configuration
├── Dockerfile            # Container build
├── pyproject.toml        # Dependencies
├── api/
│   └── server.py         # A2A TaskServer
├── chains/
│   ├── llm_factory.py    # LLM instantiation
│   └── prompts.py        # Prompt templates
├── nodes/
│   ├── base_nodes.py     # Common nodes
│   └── checklist_nodes.py # Checklist pattern
├── schemas/
│   ├── state.py          # WorkflowState TypedDict
│   ├── tasks.py          # A2A TaskInput/Output
│   └── models.py         # Domain models
├── tools/
│   ├── a2a_client/       # A2A client for calling agents
│   └── mcp_client/       # MCP client for tools
└── tests/
    └── test_workflow.py  # Unit tests
```

## Quick Start

### 1. Create Your Agent

```python
from agent_template import BaseWorkflow, run_agent
from agent_template.schemas.state import WorkflowState
from langgraph.graph import StateGraph, START, END

class MyAgentWorkflow(BaseWorkflow):
    def get_state_class(self):
        return WorkflowState

    def build_graph(self, graph: StateGraph):
        graph.add_node("process", self.process_node)
        graph.add_edge(START, "process")
        graph.add_edge("process", END)

    async def process_node(self, state: dict) -> dict:
        # Your logic here
        return {"result": {"status": "done"}}

if __name__ == "__main__":
    run_agent(MyAgentWorkflow)
```

### 2. Configure Your Agent

Copy and modify `config.yaml`:

```yaml
agent:
  name: "my_agent"
  type: "custom"
  version: "1.0.0"
  description: "My custom agent"

a2a:
  host: "0.0.0.0"
  port: 8080
  capabilities:
    - "my_task_type"

workflow:
  max_iterations: 3
```

### 3. Run

```bash
# Local
python -m my_agent.main

# Docker
docker build -t my-agent .
docker run -p 8080:8080 my-agent
```

## A2A Protocol

### Receiving Tasks

Tasks are received via POST /a2a/tasks:

```json
{
  "task_id": "task-123",
  "task_type": "my_task_type",
  "incident_id": "INC-001",
  "payload": {"key": "value"},
  "priority": 1,
  "timeout_seconds": 60
}
```

### Calling Other Agents

```python
from agent_template.tools.a2a_client import get_a2a_client

client = get_a2a_client()
client.register_agent("other_agent", "http://other-agent:8080")

result = await client.send_task(
    agent_name="other_agent",
    task_type="other_task",
    payload={"data": "value"},
    incident_id="INC-001",
)
```

## Extending WorkflowState

Create agent-specific state:

```python
from agent_template.schemas.state import WorkflowState

class MyAgentState(WorkflowState, total=False):
    my_field: str
    my_list: list[dict]
```

## Nodes

### Using Base Nodes

```python
from agent_template.nodes import initialize_node, finalize_node

graph.add_node("init", initialize_node)
graph.add_node("final", finalize_node)
```

### Using Checklist Pattern

```python
from agent_template.nodes import (
    generate_checklist_node,
    process_checklist_item_node,
    check_checklist_complete,
)

graph.add_conditional_edges(
    "process_item",
    check_checklist_complete,
    {"complete": "finalize", "continue": "process_item", "error": "error_handler"},
)
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| CONFIG_PATH | Path to config.yaml | config.yaml |
| LLM_PROVIDER | LLM provider | bedrock |
| LLM_MODEL | Model ID | claude-3-sonnet |
| MCP_SERVER_URL | MCP server URL | http://mcp-server:5000/sse |
| REDIS_URL | Redis URL | redis://redis:6379 |
| LOG_LEVEL | Log level | INFO |
| LOG_FORMAT | Log format (json/text) | json |

## Testing

```bash
pytest tests/ -v
```

## License

Internal use only.
