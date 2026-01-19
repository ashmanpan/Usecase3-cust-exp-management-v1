"""
Enrich SLA Node

Enrich services with SLA tier information.
From DESIGN.md: analyze_impact -> enrich_sla -> return_affected
"""

from typing import Any
import structlog

from ..tools.sla_enricher import get_sla_enricher

logger = structlog.get_logger(__name__)


async def enrich_sla_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Enrich SLA Node - Add SLA tier info and priority.

    From DESIGN.md:
    - Lookup SLA tier from service metadata
    - Determine priority based on tier
    - Sort services by priority

    Args:
        state: Current workflow state

    Returns:
        Updated state with enriched services
    """
    incident_id = state.get("incident_id")
    raw_services = state.get("raw_services", [])
    impact_assessment = state.get("impact_assessment", {})

    logger.info(
        "Enriching services with SLA",
        incident_id=incident_id,
        service_count=len(raw_services),
    )

    if not raw_services:
        logger.info(
            "No services to enrich",
            incident_id=incident_id,
        )
        return {
            "current_node": "enrich_sla",
            "nodes_executed": state.get("nodes_executed", []) + ["enrich_sla"],
            "affected_services": [],
            "services_by_tier": {},
            "highest_priority_tier": None,
            "auto_protect_required": False,
        }

    enricher = get_sla_enricher()

    # Enrich services with SLA info
    enriched_services = enricher.enrich_services(raw_services, impact_assessment)

    # Aggregate by tier
    services_by_tier = enricher.aggregate_by_tier(enriched_services)

    # Get highest priority tier
    highest_priority_tier = enriched_services[0].get("sla_tier") if enriched_services else None

    # Check if auto-protection required
    auto_protect_required = enricher.should_auto_protect(enriched_services)

    logger.info(
        "SLA enrichment complete",
        incident_id=incident_id,
        services_by_tier=services_by_tier,
        highest_priority_tier=highest_priority_tier,
        auto_protect_required=auto_protect_required,
    )

    return {
        "current_node": "enrich_sla",
        "nodes_executed": state.get("nodes_executed", []) + ["enrich_sla"],
        "affected_services": enriched_services,
        "services_by_tier": services_by_tier,
        "highest_priority_tier": highest_priority_tier,
        "auto_protect_required": auto_protect_required,
    }
