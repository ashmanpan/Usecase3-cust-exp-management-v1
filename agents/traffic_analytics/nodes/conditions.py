"""Conditional Edge Functions - From DESIGN.md workflow transitions"""
from typing import Any, Literal


def check_congestion_level(state: dict[str, Any]) -> Literal["analyze", "store"]:
    """
    Check if congestion level requires analysis.
    From DESIGN.md: threshold check after predict_congestion
    >= 70% -> analyze_risk, < 70% -> store_metrics
    """
    max_utilization = state.get("max_utilization", 0.0)
    high_risk_count = state.get("high_risk_count", 0)
    medium_risk_count = state.get("medium_risk_count", 0)

    # If any high or medium risks, proceed to analysis
    if high_risk_count > 0 or medium_risk_count > 0:
        return "analyze"

    # Also check raw utilization
    if max_utilization >= 0.70:
        return "analyze"

    return "store"


def check_risk_level(state: dict[str, Any]) -> Literal["alert", "warn", "log"]:
    """
    Route based on risk level.
    From DESIGN.md: high -> proactive_alert, medium -> warn, low -> log
    """
    risk_level = state.get("risk_level", "low")

    if risk_level == "high":
        return "alert"
    elif risk_level == "medium":
        return "warn"
    else:
        return "log"
