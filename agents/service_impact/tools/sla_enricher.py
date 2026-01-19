"""
SLA Enricher

Enriches services with SLA tier information and priority.
From DESIGN.md: Lookup SLA tier from service metadata, determine priority.
"""

import os
from typing import List, Dict, Any, Optional

import structlog

logger = structlog.get_logger(__name__)


# SLA Tier configuration from DESIGN.md
SLA_TIER_CONFIG = {
    "platinum": {
        "priority": 1,
        "hold_timer_seconds": 60,
        "notification_channels": ["webex", "servicenow", "email"],
        "auto_protect": True,
    },
    "gold": {
        "priority": 2,
        "hold_timer_seconds": 120,
        "notification_channels": ["webex", "servicenow"],
        "auto_protect": True,
    },
    "silver": {
        "priority": 3,
        "hold_timer_seconds": 300,
        "notification_channels": ["servicenow"],
        "auto_protect": True,
    },
    "bronze": {
        "priority": 4,
        "hold_timer_seconds": 600,
        "notification_channels": ["email"],
        "auto_protect": False,
    },
}


class SLAEnricher:
    """
    Enriches services with SLA tier info.

    From DESIGN.md:
    - Lookup SLA tier from service metadata
    - Determine priority based on tier
    - Calculate priority score for sorting
    """

    # Impact level multipliers for priority score
    IMPACT_MULTIPLIERS = {
        "full_outage": 100,
        "degraded": 50,
        "at_risk": 10,
    }

    def __init__(self, tier_config: Dict[str, dict] = None):
        """
        Initialize SLA enricher.

        Args:
            tier_config: SLA tier configuration (uses default if not provided)
        """
        self.tier_config = tier_config or SLA_TIER_CONFIG

    def enrich_service(
        self,
        service: dict,
        impact: dict,
    ) -> Dict[str, Any]:
        """
        Enrich a single service with SLA info.

        Args:
            service: Service dict from CNC
            impact: Impact assessment dict

        Returns:
            Enriched service dict (AffectedService format)
        """
        service_id = service.get("service_id", "unknown")
        sla_tier = service.get("sla_tier", "bronze").lower()

        # Get tier config
        tier_config = self.tier_config.get(sla_tier, self.tier_config["bronze"])
        tier_priority = tier_config.get("priority", 4)

        # Calculate priority score (lower = higher priority)
        impact_level = impact.get("impact_level", "at_risk")
        impact_mult = self.IMPACT_MULTIPLIERS.get(impact_level, 10)

        # Priority score: tier_priority * 1000 - impact_mult
        # Lower tier priority and higher impact = lower score = higher priority
        priority_score = tier_priority * 1000 - impact_mult

        enriched = {
            "service_id": service_id,
            "service_name": service.get("service_name", service_id),
            "service_type": service.get("service_type", "unknown"),
            "endpoint_a": service.get("endpoint_a", "unknown"),
            "endpoint_z": service.get("endpoint_z", "unknown"),
            "customer_id": service.get("customer_id", "unknown"),
            "customer_name": service.get("customer_name", "unknown"),
            "sla_tier": sla_tier,
            "current_te_type": service.get("current_te_type", "igp"),
            "current_path": service.get("current_path", []),
            "impact_level": impact_level,
            "redundancy_available": impact.get("redundancy_available", False),
            "affected_by_link": impact.get("affected_links", ["unknown"])[0] if impact.get("affected_links") else "unknown",
            "priority_score": priority_score,
            # SLA tier config for downstream use
            "hold_timer_seconds": tier_config.get("hold_timer_seconds", 300),
            "notification_channels": tier_config.get("notification_channels", []),
            "auto_protect": tier_config.get("auto_protect", False),
        }

        logger.debug(
            "Service enriched with SLA",
            service_id=service_id,
            sla_tier=sla_tier,
            priority_score=priority_score,
        )

        return enriched

    def enrich_services(
        self,
        services: List[dict],
        impacts: Dict[str, dict],
    ) -> List[Dict[str, Any]]:
        """
        Enrich multiple services with SLA info.

        Args:
            services: List of service dicts
            impacts: Dict mapping service_id to impact assessment

        Returns:
            List of enriched services, sorted by priority
        """
        enriched = []

        for service in services:
            service_id = service.get("service_id", "unknown")
            impact = impacts.get(service_id, {"impact_level": "at_risk"})
            enriched.append(self.enrich_service(service, impact))

        # Sort by priority score (lower = higher priority)
        enriched.sort(key=lambda x: x.get("priority_score", 9999))

        logger.info(
            "Services enriched and sorted",
            total_services=len(enriched),
            highest_priority_tier=enriched[0].get("sla_tier") if enriched else None,
        )

        return enriched

    def aggregate_by_tier(
        self,
        enriched_services: List[dict],
    ) -> Dict[str, int]:
        """
        Count services by SLA tier.

        Args:
            enriched_services: List of enriched service dicts

        Returns:
            Dict mapping tier to count
        """
        by_tier = {}
        for service in enriched_services:
            tier = service.get("sla_tier", "bronze")
            by_tier[tier] = by_tier.get(tier, 0) + 1
        return by_tier

    def should_auto_protect(
        self,
        enriched_services: List[dict],
    ) -> bool:
        """
        Check if any service requires auto-protection.

        Args:
            enriched_services: List of enriched service dicts

        Returns:
            True if auto-protection required
        """
        for service in enriched_services:
            if service.get("auto_protect", False):
                return True
        return False


# Singleton instance
_sla_enricher: Optional[SLAEnricher] = None


def get_sla_enricher() -> SLAEnricher:
    """Get singleton SLA enricher instance."""
    global _sla_enricher
    if _sla_enricher is None:
        _sla_enricher = SLAEnricher()
    return _sla_enricher
