"""
Query Services Node

Query CNC Service Health API for services affected by degraded links.
From DESIGN.md: query_services -> analyze_impact
"""

from typing import Any
import structlog

from ..tools.cnc_client import get_cnc_client

logger = structlog.get_logger(__name__)


async def query_services_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Query Services Node - Query CNC for affected services.

    From DESIGN.md:
    - Call CNC Service Health API for services using degraded links
    - Return service list for impact analysis

    Args:
        state: Current workflow state

    Returns:
        Updated state with raw services
    """
    incident_id = state.get("incident_id")
    degraded_links = state.get("degraded_links", [])

    logger.info(
        "Querying services for degraded links",
        incident_id=incident_id,
        degraded_link_count=len(degraded_links),
    )

    if not degraded_links:
        logger.warning(
            "No degraded links provided",
            incident_id=incident_id,
        )
        return {
            "current_node": "query_services",
            "nodes_executed": state.get("nodes_executed", []) + ["query_services"],
            "raw_services": [],
            "query_success": True,
            "query_error": None,
        }

    try:
        client = get_cnc_client()

        # Query services for each degraded link
        all_services = []
        seen_service_ids = set()

        for link_id in degraded_links:
            services = await client.get_services_by_link(link_id)
            for service in services:
                service_id = service.get("service_id")
                if service_id and service_id not in seen_service_ids:
                    seen_service_ids.add(service_id)
                    # Track which link affects this service
                    service["affected_by_link"] = link_id
                    all_services.append(service)

        logger.info(
            "Services query complete",
            incident_id=incident_id,
            total_services=len(all_services),
            links_queried=len(degraded_links),
        )

        return {
            "current_node": "query_services",
            "nodes_executed": state.get("nodes_executed", []) + ["query_services"],
            "raw_services": all_services,
            "query_success": True,
            "query_error": None,
        }

    except Exception as e:
        logger.error(
            "Failed to query services",
            incident_id=incident_id,
            error=str(e),
        )
        return {
            "current_node": "query_services",
            "nodes_executed": state.get("nodes_executed", []) + ["query_services"],
            "raw_services": [],
            "query_success": False,
            "query_error": str(e),
        }
