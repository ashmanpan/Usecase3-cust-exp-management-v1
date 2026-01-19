"""
Impact Analyzer

Analyzes service impact based on degraded links.
From DESIGN.md: Determine impact severity based on service type and redundancy.
"""

import os
from typing import List, Dict, Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class ImpactAnalyzer:
    """
    Analyzes impact of degraded links on services.

    From DESIGN.md:
    - Determine impact level (full_outage, degraded, at_risk)
    - Check for redundancy availability
    - Aggregate by service type
    """

    # Impact levels
    IMPACT_FULL_OUTAGE = "full_outage"
    IMPACT_DEGRADED = "degraded"
    IMPACT_AT_RISK = "at_risk"

    def __init__(self):
        """Initialize impact analyzer."""
        pass

    def analyze_service_impact(
        self,
        service: dict,
        degraded_links: List[str],
    ) -> Dict[str, Any]:
        """
        Analyze impact on a single service.

        Args:
            service: Service dict from CNC
            degraded_links: List of degraded link IDs

        Returns:
            Impact assessment dict
        """
        service_id = service.get("service_id", "unknown")
        service_type = service.get("service_type", "unknown")
        current_path = service.get("current_path", [])

        # Count how many degraded links affect this service
        affected_links = [
            link for link in degraded_links
            if link in current_path or self._link_affects_service(link, service)
        ]

        # Determine impact level
        has_redundancy = service.get("redundancy_available", False)
        total_path_links = len(current_path) if current_path else 1

        if len(affected_links) == 0:
            impact_level = self.IMPACT_AT_RISK
        elif len(affected_links) == total_path_links and not has_redundancy:
            impact_level = self.IMPACT_FULL_OUTAGE
        elif has_redundancy:
            impact_level = self.IMPACT_DEGRADED
        else:
            impact_level = self.IMPACT_DEGRADED

        logger.debug(
            "Service impact analyzed",
            service_id=service_id,
            impact_level=impact_level,
            affected_link_count=len(affected_links),
            has_redundancy=has_redundancy,
        )

        return {
            "service_id": service_id,
            "service_type": service_type,
            "impact_level": impact_level,
            "affected_links": affected_links,
            "redundancy_available": has_redundancy,
        }

    def _link_affects_service(self, link_id: str, service: dict) -> bool:
        """
        Check if a link affects a service.

        Uses heuristics when path info is incomplete.
        """
        # Check if link is in service path
        current_path = service.get("current_path", [])
        if link_id in current_path:
            return True

        # Check if link endpoints match service endpoints
        endpoint_a = service.get("endpoint_a", "")
        endpoint_z = service.get("endpoint_z", "")

        # Simple heuristic: link contains endpoint name
        if endpoint_a in link_id or endpoint_z in link_id:
            return True

        return False

    def aggregate_impact(
        self,
        services: List[dict],
        degraded_links: List[str],
    ) -> Dict[str, Any]:
        """
        Aggregate impact across all services.

        Args:
            services: List of service dicts
            degraded_links: List of degraded link IDs

        Returns:
            Aggregated impact assessment
        """
        total = len(services)
        by_type = {}
        by_impact = {
            self.IMPACT_FULL_OUTAGE: 0,
            self.IMPACT_DEGRADED: 0,
            self.IMPACT_AT_RISK: 0,
        }

        for service in services:
            # Count by type
            svc_type = service.get("service_type", "unknown")
            by_type[svc_type] = by_type.get(svc_type, 0) + 1

            # Analyze impact
            impact = self.analyze_service_impact(service, degraded_links)
            impact_level = impact.get("impact_level", self.IMPACT_AT_RISK)
            by_impact[impact_level] = by_impact.get(impact_level, 0) + 1

        logger.info(
            "Impact aggregation complete",
            total_services=total,
            by_type=by_type,
            by_impact=by_impact,
        )

        return {
            "total_affected": total,
            "services_by_type": by_type,
            "services_by_impact": by_impact,
            "degraded_links": degraded_links,
        }


# Singleton instance
_impact_analyzer: Optional[ImpactAnalyzer] = None


def get_impact_analyzer() -> ImpactAnalyzer:
    """Get singleton impact analyzer instance."""
    global _impact_analyzer
    if _impact_analyzer is None:
        _impact_analyzer = ImpactAnalyzer()
    return _impact_analyzer
