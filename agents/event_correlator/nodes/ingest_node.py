"""
Ingest Node

Parse PCA/CNC alert, normalize to internal format.
From DESIGN.md: ingest -> dedup
"""

from typing import Any
from datetime import datetime
from uuid import uuid4

import structlog

from ..schemas.alerts import NormalizedAlert

logger = structlog.get_logger(__name__)


async def ingest_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Ingest Node - Parse and normalize incoming alert.

    Actions:
    1. Parse raw alert based on source (pca, cnc, proactive)
    2. Normalize to internal NormalizedAlert format
    3. Extract key fields (link_id, severity, metrics)

    Args:
        state: Current workflow state

    Returns:
        Updated state with normalized alert
    """
    alert_source = state.get("alert_source", "unknown")
    raw_alert = state.get("raw_alert", {})

    logger.info(
        "Ingesting alert",
        source=alert_source,
    )

    # Generate alert ID if not present
    alert_id = raw_alert.get("alert_id") or f"ALERT-{uuid4().hex[:12]}"

    # Normalize based on source
    if alert_source == "pca":
        normalized = _normalize_pca_alert(alert_id, raw_alert)
    elif alert_source == "cnc":
        normalized = _normalize_cnc_alert(alert_id, raw_alert)
    elif alert_source == "proactive":
        normalized = _normalize_proactive_alert(alert_id, raw_alert)
    else:
        normalized = _normalize_generic_alert(alert_id, raw_alert)

    logger.info(
        "Alert normalized",
        alert_id=alert_id,
        link_id=normalized.get("link_id"),
        severity=normalized.get("severity"),
    )

    return {
        "current_node": "ingest",
        "nodes_executed": state.get("nodes_executed", []) + ["ingest"],
        "normalized_alert": normalized,
    }


def _normalize_pca_alert(alert_id: str, raw: dict) -> dict:
    """Normalize PCA alert"""
    # Determine severity based on metric values
    current_value = raw.get("current_value", 0)
    threshold_value = raw.get("threshold_value", 0)
    metric_type = raw.get("metric_type", "latency")

    ratio = current_value / threshold_value if threshold_value > 0 else 1

    if ratio >= 2.0:
        severity = "critical"
    elif ratio >= 1.5:
        severity = "major"
    elif ratio >= 1.2:
        severity = "minor"
    else:
        severity = "warning"

    # Build link_id from source/dest IPs (in real impl, would lookup in KG)
    link_id = raw.get("link_id") or f"link-{raw.get('source_ip', 'unknown')}-{raw.get('dest_ip', 'unknown')}"

    return {
        "alert_id": alert_id,
        "source": "pca",
        "timestamp": raw.get("timestamp") or datetime.utcnow().isoformat(),
        "link_id": link_id,
        "interface_a": raw.get("interface_a", f"{raw.get('source_ip', 'unknown')}:unknown"),
        "interface_z": raw.get("interface_z", f"{raw.get('dest_ip', 'unknown')}:unknown"),
        "latency_ms": raw.get("current_value") if metric_type == "latency" else None,
        "jitter_ms": raw.get("current_value") if metric_type == "jitter" else None,
        "packet_loss_pct": raw.get("current_value") if metric_type == "loss" else None,
        "violated_thresholds": [metric_type],
        "severity": severity,
        "raw_payload": raw,
    }


def _normalize_cnc_alert(alert_id: str, raw: dict) -> dict:
    """Normalize CNC alarm"""
    severity_map = {
        "critical": "critical",
        "major": "major",
        "minor": "minor",
        "warning": "warning",
        "clear": "warning",
    }

    return {
        "alert_id": alert_id,
        "source": "cnc",
        "timestamp": raw.get("timestamp") or datetime.utcnow().isoformat(),
        "link_id": raw.get("resource_id", "unknown"),
        "interface_a": raw.get("interface_a", "unknown"),
        "interface_z": raw.get("interface_z", "unknown"),
        "latency_ms": None,
        "jitter_ms": None,
        "packet_loss_pct": None,
        "violated_thresholds": [raw.get("alarm_type", "unknown")],
        "severity": severity_map.get(raw.get("severity", "warning"), "warning"),
        "raw_payload": raw,
    }


def _normalize_proactive_alert(alert_id: str, raw: dict) -> dict:
    """Normalize proactive alert from Traffic Analytics"""
    return {
        "alert_id": alert_id,
        "source": "proactive",
        "timestamp": raw.get("timestamp") or datetime.utcnow().isoformat(),
        "link_id": raw.get("link_id", "unknown"),
        "interface_a": raw.get("interface_a", "unknown"),
        "interface_z": raw.get("interface_z", "unknown"),
        "latency_ms": raw.get("predicted_latency_ms"),
        "jitter_ms": None,
        "packet_loss_pct": None,
        "violated_thresholds": raw.get("predicted_violations", ["congestion"]),
        "severity": raw.get("severity", "warning"),
        "raw_payload": raw,
    }


def _normalize_generic_alert(alert_id: str, raw: dict) -> dict:
    """Normalize generic alert"""
    return {
        "alert_id": alert_id,
        "source": "unknown",
        "timestamp": datetime.utcnow().isoformat(),
        "link_id": raw.get("link_id", "unknown"),
        "interface_a": raw.get("interface_a", "unknown"),
        "interface_z": raw.get("interface_z", "unknown"),
        "latency_ms": raw.get("latency_ms"),
        "jitter_ms": raw.get("jitter_ms"),
        "packet_loss_pct": raw.get("packet_loss_pct"),
        "violated_thresholds": raw.get("violated_thresholds", []),
        "severity": raw.get("severity", "warning"),
        "raw_payload": raw,
    }
