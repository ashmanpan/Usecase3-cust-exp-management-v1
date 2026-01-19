"""
LLM Factory

Provides unified LLM instantiation for different providers.
Supports: AWS Bedrock, OpenAI, Anthropic
"""

import os
from typing import Any, Optional, Literal
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LLMConfig:
    """LLM Configuration"""
    provider: Literal["bedrock", "openai", "anthropic"] = "bedrock"
    model: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    temperature: float = 0.0
    max_tokens: int = 4096
    # AWS Bedrock specific
    aws_region: Optional[str] = None
    # API keys (prefer env vars)
    api_key: Optional[str] = None


def get_llm(config: LLMConfig = None) -> Any:
    """
    Get LLM instance based on configuration.

    Args:
        config: LLM configuration. If None, uses defaults from env vars.

    Returns:
        LangChain chat model instance
    """
    if config is None:
        config = LLMConfig(
            provider=os.getenv("LLM_PROVIDER", "bedrock"),
            model=os.getenv("LLM_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        )

    logger.info(
        "Creating LLM",
        provider=config.provider,
        model=config.model,
    )

    if config.provider == "bedrock":
        return _get_bedrock_llm(config)
    elif config.provider == "openai":
        return _get_openai_llm(config)
    elif config.provider == "anthropic":
        return _get_anthropic_llm(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")


def _get_bedrock_llm(config: LLMConfig) -> Any:
    """Get AWS Bedrock LLM"""
    try:
        from langchain_aws import ChatBedrock
    except ImportError:
        from langchain_community.chat_models import BedrockChat as ChatBedrock

    region = config.aws_region or os.getenv("AWS_REGION", "us-west-2")

    return ChatBedrock(
        model_id=config.model,
        region_name=region,
        model_kwargs={
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        },
    )


def _get_openai_llm(config: LLMConfig) -> Any:
    """Get OpenAI LLM"""
    from langchain_openai import ChatOpenAI

    api_key = config.api_key or os.getenv("OPENAI_API_KEY")

    return ChatOpenAI(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        api_key=api_key,
    )


def _get_anthropic_llm(config: LLMConfig) -> Any:
    """Get Anthropic LLM"""
    from langchain_anthropic import ChatAnthropic

    api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")

    return ChatAnthropic(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        api_key=api_key,
    )


# Convenience functions for common configurations

def get_bedrock_claude_sonnet() -> Any:
    """Get Claude 3 Sonnet via Bedrock (default for production)"""
    return get_llm(LLMConfig(
        provider="bedrock",
        model="anthropic.claude-3-sonnet-20240229-v1:0",
    ))


def get_bedrock_claude_haiku() -> Any:
    """Get Claude 3 Haiku via Bedrock (fast, lower cost)"""
    return get_llm(LLMConfig(
        provider="bedrock",
        model="anthropic.claude-3-haiku-20240307-v1:0",
    ))


def get_openai_gpt4() -> Any:
    """Get GPT-4 via OpenAI"""
    return get_llm(LLMConfig(
        provider="openai",
        model="gpt-4-turbo-preview",
    ))
