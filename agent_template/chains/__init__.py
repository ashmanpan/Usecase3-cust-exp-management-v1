"""
LangChain Chains for Agent Template

Provides reusable chains for common patterns.
"""

from .prompts import (
    CHECKLIST_GENERATION_PROMPT,
    EVALUATION_PROMPT,
    ANALYSIS_PROMPT,
    A2A_TASK_PROMPT,
)
from .llm_factory import get_llm, LLMConfig

__all__ = [
    "CHECKLIST_GENERATION_PROMPT",
    "EVALUATION_PROMPT",
    "ANALYSIS_PROMPT",
    "A2A_TASK_PROMPT",
    "get_llm",
    "LLMConfig",
]
