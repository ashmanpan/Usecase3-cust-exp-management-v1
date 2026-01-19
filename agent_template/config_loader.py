"""
Configuration Loader

Loads agent configuration from YAML file with environment variable substitution.
"""

import os
import re
from typing import Any, Optional
from pathlib import Path

import yaml
import structlog
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

logger = structlog.get_logger(__name__)


def _substitute_env_vars(value: Any) -> Any:
    """
    Recursively substitute environment variables in configuration.

    Supports format: ${VAR_NAME:-default_value}
    """
    if isinstance(value, str):
        # Pattern: ${VAR:-default} or ${VAR}
        pattern = r"\$\{([^}:]+)(?::-([^}]*))?\}"

        def replace(match):
            var_name = match.group(1)
            default = match.group(2) if match.group(2) is not None else ""
            return os.getenv(var_name, default)

        return re.sub(pattern, replace, value)

    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}

    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]

    return value


class AgentConfig(BaseModel):
    """Agent identification configuration"""
    name: str
    type: str
    version: str
    description: str


class A2AConfig(BaseModel):
    """A2A server configuration"""
    host: str = "0.0.0.0"
    port: int = 8080
    capabilities: list[str] = Field(default_factory=list)


class WorkflowConfig(BaseModel):
    """Workflow configuration"""
    max_iterations: int = 3
    timeout_seconds: int = 300
    stages: dict[str, dict] = Field(default_factory=dict)


class LLMSettings(BaseModel):
    """LLM configuration"""
    provider: str = "bedrock"
    model: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    temperature: float = 0.0
    max_tokens: int = 4096


class MCPConfig(BaseModel):
    """MCP server configuration"""
    server_url: str = "http://mcp-server:5000"
    timeout_seconds: int = 300
    blocked_tools: list[str] = Field(default_factory=list)


class RedisConfig(BaseModel):
    """Redis configuration"""
    url: str = "redis://redis:6379"
    db: int = 0
    key_prefix: str = "agent:"


class ServiceEndpoints(BaseModel):
    """External service endpoints"""
    kg: dict = Field(default_factory=dict)
    rag: dict = Field(default_factory=dict)
    cnc: dict = Field(default_factory=dict)
    pca: dict = Field(default_factory=dict)


class ObservabilityConfig(BaseModel):
    """Observability configuration"""
    log_level: str = "INFO"
    log_format: str = "json"
    otel: dict = Field(default_factory=dict)


class HealthConfig(BaseModel):
    """Health check configuration"""
    enabled: bool = True
    port: int = 8081
    path: str = "/health"
    ready_path: str = "/ready"


class Config(BaseModel):
    """Complete agent configuration"""
    agent: AgentConfig
    a2a: A2AConfig = Field(default_factory=lambda: A2AConfig())
    workflow: WorkflowConfig = Field(default_factory=lambda: WorkflowConfig())
    llm: LLMSettings = Field(default_factory=lambda: LLMSettings())
    mcp: MCPConfig = Field(default_factory=lambda: MCPConfig())
    redis: RedisConfig = Field(default_factory=lambda: RedisConfig())
    services: ServiceEndpoints = Field(default_factory=lambda: ServiceEndpoints())
    observability: ObservabilityConfig = Field(default_factory=lambda: ObservabilityConfig())
    health: HealthConfig = Field(default_factory=lambda: HealthConfig())


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, looks for config.yaml in current dir.

    Returns:
        Parsed Config object
    """
    if config_path is None:
        config_path = os.getenv("CONFIG_PATH", "config.yaml")

    path = Path(config_path)
    if not path.exists():
        logger.warning(
            "Config file not found, using defaults",
            path=str(path),
        )
        return Config(
            agent=AgentConfig(
                name="default_agent",
                type="default",
                version="1.0.0",
                description="Default agent configuration",
            )
        )

    logger.info("Loading configuration", path=str(path))

    with open(path, "r") as f:
        raw_config = yaml.safe_load(f)

    # Substitute environment variables
    config_data = _substitute_env_vars(raw_config)

    # Parse into Config model
    config = Config(**config_data)

    logger.info(
        "Configuration loaded",
        agent_name=config.agent.name,
        agent_version=config.agent.version,
    )

    return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration (loads on first call)"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Set global configuration (for testing)"""
    global _config
    _config = config
