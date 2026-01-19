"""
Analyze Impact Node

Analyze impact on services based on degraded links.
From DESIGN.md: query_services -> analyze_impact -> enrich_sla
"""

from typing import Any
import structlog

from ..tools.impact_analyzer import get_impact_analyzer

logger = structlog.get_logger(__name__)


async def analyze_impact_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze Impact Node - Determine impact severity.

    From DESIGN.md:
    - Determine impact severity based on service type and redundancy
    - Impact levels: full_outage, degraded, at_risk

    Args:
        state: Current workflow state

    Returns:
        Updated state with impact assessment
    """
    incident_id = state.get("incident_id")
    raw_services = state.get("raw_services", [])
    degraded_links = state.get("degraded_links", [])

    logger.info(
        "Analyzing service impact",
        incident_id=incident_id,
        service_count=len(raw_services),
        degraded_link_count=len(degraded_links),
    )

    if not raw_services:
        logger.info(
            "No services to analyze",
            incident_id=incident_id,
        )
        return {
            "current_node": "analyze_impact",
            "nodes_executed": state.get("nodes_executed", []) + ["analyze_impact"],
            "impact_assessment": {},
            "total_affected": 0,
            "services_by_type": {},
        }

    analyzer = get_impact_analyzer()

    # Analyze impact on each service
    service_impacts = {}
    for service in raw_services:
        service_id = service.get("service_id", "unknown")
        impact = analyzer.analyze_service_impact(service, degraded_links)
        service_impacts[service_id] = impact

    # Aggregate impact
    aggregation = analyzer.aggregate_impact(raw_services, degraded_links)

    logger.info(
        "Impact analysis complete",
        incident_id=incident_id,
        total_affected=aggregation.get("total_affected", 0),
        by_impact=aggregation.get("services_by_impact", {}),
    )

    return {
        "current_node": "analyze_impact",
        "nodes_executed": state.get("nodes_executed", []) + ["analyze_impact"],
        "impact_assessment": service_impacts,
        "total_affected": aggregation.get("total_affected", 0),
        "services_by_type": aggregation.get("services_by_type", {}),
    }
