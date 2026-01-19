"""
Checklist Pattern Nodes

Implements the checklist pattern from the BGP agent template.
Useful for multi-step verification and processing tasks.
"""

from typing import Any, Callable

import structlog
from langchain_core.messages import HumanMessage

logger = structlog.get_logger(__name__)


async def generate_checklist_node(
    state: dict,
    llm: Any,
    checklist_prompt: str,
) -> dict:
    """
    Generate a checklist of items to process.

    Uses LLM to analyze the task and create a checklist.

    Args:
        state: Current workflow state
        llm: LLM instance
        checklist_prompt: Prompt template for checklist generation
    """
    task_id = state.get("task_id", "unknown")
    input_payload = state.get("input_payload", {})
    user_prompt = state.get("user_prompt", "")

    prompt = checklist_prompt.format(
        task_id=task_id,
        input_payload=input_payload,
        user_prompt=user_prompt,
    )

    logger.info("Generating checklist", task_id=task_id)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        response_text = response.content if hasattr(response, "content") else str(response)

        # Parse checklist from response
        # Expects format like:
        # 1. Item one
        # 2. Item two
        # etc.
        lines = response_text.strip().split("\n")
        checklist = []
        for line in lines:
            line = line.strip()
            # Remove numbering
            if line and (line[0].isdigit() or line.startswith("-")):
                item = line.lstrip("0123456789.-) ").strip()
                if item:
                    checklist.append(item)

        if not checklist:
            # Fallback: treat entire response as single item
            checklist = [response_text.strip()]

        logger.info(
            "Generated checklist",
            task_id=task_id,
            item_count=len(checklist),
        )

        return {
            "checklist": checklist,
            "remaining_checklist": checklist.copy(),
            "resolved_checklist": [],
            "current_node": "generate_checklist",
            "nodes_executed": state.get("nodes_executed", []) + ["generate_checklist"],
        }

    except Exception as e:
        logger.exception("Checklist generation failed", task_id=task_id)
        return {
            "error": str(e),
            "status": "failed",
        }


async def process_checklist_item_node(
    state: dict,
    llm: Any,
    tools: list,
    item_prompt: str,
) -> dict:
    """
    Process the next item in the checklist.

    Uses LLM with tools to handle one checklist item.

    Args:
        state: Current workflow state
        llm: LLM instance
        tools: Available tools
        item_prompt: Prompt template for processing items
    """
    task_id = state.get("task_id", "unknown")
    remaining = state.get("remaining_checklist", [])
    resolved = state.get("resolved_checklist", [])
    tool_outputs = state.get("tool_outputs", [])

    if not remaining:
        logger.info("No items remaining", task_id=task_id)
        return {}

    current_item = remaining[0]
    logger.info(
        "Processing checklist item",
        task_id=task_id,
        item=current_item,
        remaining=len(remaining),
    )

    prompt = item_prompt.format(
        task_id=task_id,
        current_item=current_item,
        resolved_items=resolved,
        input_payload=state.get("input_payload", {}),
    )

    try:
        # Bind tools and invoke
        llm_with_tools = llm.bind_tools(tools)
        response = await llm_with_tools.ainvoke([HumanMessage(content=prompt)])

        # Track tool usage
        new_tool_calls = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            new_tool_calls = [tc["name"] for tc in response.tool_calls]

        # Update checklist
        new_remaining = remaining[1:]  # Remove processed item
        new_resolved = resolved + [current_item]

        # Collect output
        output = {
            "item": current_item,
            "response": response.content if hasattr(response, "content") else str(response),
            "tools_used": new_tool_calls,
        }

        return {
            "remaining_checklist": new_remaining,
            "resolved_checklist": new_resolved,
            "tool_outputs": tool_outputs + [output],
            "mcp_tools_used": state.get("mcp_tools_used", []) + new_tool_calls,
            "current_node": "process_checklist_item",
            "nodes_executed": state.get("nodes_executed", []) + ["process_checklist_item"],
        }

    except Exception as e:
        logger.exception(
            "Failed to process checklist item",
            task_id=task_id,
            item=current_item,
        )
        return {
            "error": f"Failed on item '{current_item}': {str(e)}",
            "status": "failed",
        }


def check_checklist_complete(state: dict) -> str:
    """
    Conditional edge function to check if checklist is complete.

    Returns:
        "complete" if no items remaining
        "continue" if more items to process
        "error" if error occurred
    """
    if state.get("error"):
        return "error"

    remaining = state.get("remaining_checklist", [])
    if not remaining:
        return "complete"

    return "continue"


def create_checklist_processor(
    llm: Any,
    tools: list,
    item_prompt: str,
) -> Callable[[dict], dict]:
    """
    Create a checklist processor function with bound parameters.

    Useful for creating the node function for graph.add_node().

    Args:
        llm: LLM instance
        tools: Available tools
        item_prompt: Prompt template

    Returns:
        Async function suitable for LangGraph node
    """

    async def processor(state: dict) -> dict:
        return await process_checklist_item_node(
            state=state,
            llm=llm,
            tools=tools,
            item_prompt=item_prompt,
        )

    return processor
