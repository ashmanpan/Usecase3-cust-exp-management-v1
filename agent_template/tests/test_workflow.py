"""
Tests for Workflow Base Class
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langgraph.graph import StateGraph, START, END

from ..workflow import BaseWorkflow
from ..schemas.state import WorkflowState


class TestWorkflow(BaseWorkflow):
    """Test workflow implementation"""

    def get_state_class(self):
        return WorkflowState

    def build_graph(self, graph: StateGraph):
        async def test_node(state: dict) -> dict:
            return {
                "result": {"test": "success"},
                "status": "success",
            }

        graph.add_node("test", test_node)
        graph.add_edge(START, "test")
        graph.add_edge("test", END)


@pytest.fixture
def workflow():
    """Create test workflow"""
    return TestWorkflow(
        agent_name="test_agent",
        agent_version="1.0.0",
    )


class TestBaseWorkflow:
    """Tests for BaseWorkflow"""

    def test_init(self, workflow):
        """Test workflow initialization"""
        assert workflow.agent_name == "test_agent"
        assert workflow.agent_version == "1.0.0"
        assert workflow.max_iterations == 3

    def test_compile(self, workflow):
        """Test workflow compilation"""
        app = workflow.compile()
        assert app is not None

    @pytest.mark.asyncio
    async def test_execute(self, workflow):
        """Test workflow execution"""
        result = await workflow.execute(
            task_id="test-123",
            task_type="test",
            payload={"key": "value"},
        )

        assert result is not None
        assert result.get("test") == "success"

    def test_get_initial_state(self, workflow):
        """Test initial state creation"""
        state = workflow.get_initial_state(
            task_id="test-123",
            task_type="test",
            incident_id="INC-001",
            payload={"key": "value"},
        )

        assert state["task_id"] == "test-123"
        assert state["incident_id"] == "INC-001"
        assert state["input_payload"] == {"key": "value"}
        assert state["iteration_count"] == 0
        assert state["status"] == "running"


class TestIterationCheck:
    """Tests for iteration check functions"""

    def test_make_iteration_check(self):
        from ..workflow import make_iteration_check

        check = make_iteration_check(3)

        # Under limit
        assert check({"iteration_count": 0}) == "continue"
        assert check({"iteration_count": 2}) == "continue"

        # At/over limit
        assert check({"iteration_count": 3}) == "max_reached"
        assert check({"iteration_count": 5}) == "max_reached"


class TestChecklistCheck:
    """Tests for checklist check functions"""

    def test_make_checklist_check(self):
        from ..workflow import make_checklist_check

        check = make_checklist_check()

        # Items remaining
        assert check({"remaining_checklist": ["item1"]}) == "continue"

        # Complete
        assert check({"remaining_checklist": []}) == "complete"


class TestErrorCheck:
    """Tests for error check functions"""

    def test_make_error_check(self):
        from ..workflow import make_error_check

        check = make_error_check()

        # No error
        assert check({}) == "success"
        assert check({"error": None}) == "success"

        # Has error
        assert check({"error": "Something failed"}) == "error"
