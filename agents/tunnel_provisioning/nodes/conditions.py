"""Conditional Edge Functions - From DESIGN.md workflow transitions"""
from typing import Any, Literal

def check_creation_success(state: dict[str, Any]) -> Literal["verify", "retry"]:
    """Check if tunnel creation succeeded"""
    return "verify" if state.get("creation_success", False) else "retry"

def check_tunnel_verified(state: dict[str, Any]) -> Literal["steer", "retry"]:
    """Check if tunnel is verified"""
    return "steer" if state.get("tunnel_verified", False) else "retry"

def check_can_retry(state: dict[str, Any]) -> Literal["create", "return"]:
    """Check if retry is possible (max 3 attempts)"""
    return "create" if state.get("retry_count", 0) < 3 else "return"
