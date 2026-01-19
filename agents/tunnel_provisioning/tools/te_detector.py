"""TE Type Detector - From DESIGN.md TETypeDetector"""
import os
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger(__name__)

class TETypeDetector:
    """Auto-detect appropriate TE technology based on service config - From DESIGN.md"""
    SUPPORTED_TYPES = ["sr-mpls", "srv6", "rsvp-te"]
    DEFAULT_TYPE = "sr-mpls"

    def detect(self, service_te_type: Optional[str], path: dict, device_capabilities: Dict[str, Any] = None) -> str:
        """Detection priority: 1. Match existing service TE type, 2. Check capabilities, 3. Default to SR-MPLS"""
        # 1. Match existing
        if service_te_type and service_te_type in self.SUPPORTED_TYPES:
            logger.info("Using existing service TE type", te_type=service_te_type)
            return service_te_type

        # 2. Check capabilities
        caps = device_capabilities or {}
        if "srv6" in caps.get("supported_te", []):
            logger.info("Device supports SRv6")
            return "srv6"
        elif "sr-mpls" in caps.get("supported_te", []):
            return "sr-mpls"
        elif "rsvp-te" in caps.get("supported_te", []):
            return "rsvp-te"

        # 3. Default
        logger.info("Using default TE type", te_type=self.DEFAULT_TYPE)
        return self.DEFAULT_TYPE

_te_detector: Optional[TETypeDetector] = None

def get_te_detector() -> TETypeDetector:
    global _te_detector
    if _te_detector is None:
        _te_detector = TETypeDetector()
    return _te_detector
