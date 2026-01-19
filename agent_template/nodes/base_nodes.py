"""
Base Node Implementations

Common nodes that most agents will use.
"""

from typing import Any, Optional
from datetime import datetime

import structlog
from langchain_core.messages import HumanMessage, AIMessage

logger = structlog.get_logger(__name__)


async def initialize_node(state: dict) -> dict:
    """
    Initialize workflow execution.

    Sets up initial state and logs start.
    """
    task_id = state.get("task_id", "unknown")
    task_type = state.get("input_payload", {}).get("task_type", "unknown")

    logger.info(
        "Initializing workflow",
        task_id=task_id,
        task_type=task_type,
    )

    return {
        "current_node": "initialize",
        "nodes_executed": state.get("nodes_executed", []) + ["initialize"],
        "started_at": state.get("started_at") or datetime.utcnow().isoformat(),
        "status": "running",
    }


async def tool_execution_node(
    state: dict,
    tools: list,
    llm: Any,
    system_prompt: str = None,
) -> dict:
    """
    Execute tools based on LLM decision.

    Uses ReAct pattern - LLM decides which tools to call.

    Args:
        state: Current workflow state
        tools: Available tools for this stage
        llm: LLM instance with tool binding
        system_prompt: Optional system prompt override
    """
    task_id = state.get("task_id", "unknown")
    user_prompt = state.get("user_prompt", "")
    input_payload = state.get("input_payload", {})

    # Build context for LLM
    context = f"""
Task ID: {task_id}
Input: {input_payload}
User Request: {user_prompt}
"""

    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(tools)

    # Create message
    messages = [HumanMessage(content=context)]

    logger.info(
        "Executing tool node",
        task_id=task_id,
        available_tools=[t.name for t in tools],
    )

    try:
        response = await llm_with_tools.ainvoke(messages)

        # Track tool calls
        tool_calls = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = [tc["name"] for tc in response.tool_calls]

        return {
            "raw_result": response,
            "mcp_tools_used": state.get("mcp_tools_used", []) + tool_calls,
            "current_node": "tool_execution",
            "nodes_executed": state.get("nodes_executed", []) + ["tool_execution"],
        }

    except Exception as e:
        logger.exception("Tool execution failed", task_id=task_id)
        return {
            "error": str(e),
            "status": "failed",
            "current_node": "tool_execution",
            "nodes_executed": state.get("nodes_executed", []) + ["tool_execution"],
        }


async def analysis_node(
    state: dict,
    llm: Any,
    analysis_prompt: str,
) -> dict:
    """
    Analyze tool outputs using LLM.

    Args:
        state: Current workflow state
        llm: LLM instance
        analysis_prompt: Prompt template for analysis
    """
    task_id = state.get("task_id", "unknown")
    raw_result = state.get("raw_result")
    tool_outputs = state.get("tool_outputs", [])

    # Format tool outputs for analysis
    outputs_text = "\n".join([
        f"Tool: {o.get('tool')}\nOutput: {o.get('output')}"
        for o in tool_outputs
    ])

    prompt = analysis_prompt.format(
        task_id=task_id,
        tool_outputs=outputs_text,
        raw_result=raw_result,
    )

    logger.info("Running analysis", task_id=task_id)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        analysis = response.content if hasattr(response, "content") else str(response)

        return {
            "analysis_result": analysis,
            "current_node": "analysis",
            "nodes_executed": state.get("nodes_executed", []) + ["analysis"],
        }

    except Exception as e:
        logger.exception("Analysis failed", task_id=task_id)
        return {
            "error": str(e),
            "status": "failed",
        }


async def evaluation_node(
    state: dict,
    llm: Any,
    evaluation_prompt: str,
) -> dict:
    """
    Evaluate workflow progress and decide next action.

    Returns evaluation dict with:
    - needs_more_work: bool
    - confidence: float (0-1)
    - next_action: str
    - reasoning: str
    """
    task_id = state.get("task_id", "unknown")
    analysis = state.get("analysis_result", "")
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)

    prompt = evaluation_prompt.format(
        task_id=task_id,
        analysis=analysis,
        iteration=iteration,
        max_iterations=max_iter,
    )

    logger.info("Running evaluation", task_id=task_id, iteration=iteration)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        eval_text = response.content if hasattr(response, "content") else str(response)

        # Parse evaluation (simple approach - could use structured output)
        evaluation = {
            "raw_evaluation": eval_text,
            "needs_more_work": "needs_more_work" in eval_text.lower() or "continue" in eval_text.lower(),
            "confidence": 0.8,  # Default, could parse from response
        }

        return {
            "evaluation": evaluation,
            "iteration_count": iteration + 1,
            "current_node": "evaluation",
            "nodes_executed": state.get("nodes_executed", []) + ["evaluation"],
        }

    except Exception as e:
        logger.exception("Evaluation failed", task_id=task_id)
        return {
            "error": str(e),
            "status": "failed",
        }


async def finalize_node(state: dict) -> dict:
    """
    Finalize workflow and prepare result.

    Collects all outputs and creates final result.
    """
    task_id = state.get("task_id", "unknown")
    analysis = state.get("analysis_result", "")
    tool_outputs = state.get("tool_outputs", [])
    error = state.get("error")

    logger.info(
        "Finalizing workflow",
        task_id=task_id,
        nodes_executed=state.get("nodes_executed", []),
    )

    if error:
        return {
            "status": "failed",
            "result": {"error": error},
            "final_output": f"Workflow failed: {error}",
            "current_node": "finalize",
            "nodes_executed": state.get("nodes_executed", []) + ["finalize"],
        }

    # Build result
    result = {
        "task_id": task_id,
        "analysis": analysis,
        "tool_outputs": tool_outputs,
        "nodes_executed": state.get("nodes_executed", []),
        "iterations": state.get("iteration_count", 0),
    }

    return {
        "status": "success",
        "result": result,
        "final_output": analysis,
        "current_node": "finalize",
        "nodes_executed": state.get("nodes_executed", []) + ["finalize"],
    }


async def error_handler_node(state: dict) -> dict:
    """
    Handle workflow errors.

    Logs error and sets failure state.
    """
    task_id = state.get("task_id", "unknown")
    error = state.get("error", "Unknown error")

    logger.error(
        "Workflow error",
        task_id=task_id,
        error=error,
        nodes_executed=state.get("nodes_executed", []),
    )

    return {
        "status": "failed",
        "result": {
            "error": error,
            "task_id": task_id,
            "failed_at_node": state.get("current_node"),
        },
        "final_output": f"Error: {error}",
        "current_node": "error_handler",
        "nodes_executed": state.get("nodes_executed", []) + ["error_handler"],
    }
