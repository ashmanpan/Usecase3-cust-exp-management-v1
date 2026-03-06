"""Create Tunnel Node - From DESIGN.md

Supports two tunnel deployment models controlled by TUNNEL_PROVISIONING_MODE:

  nso (default) — PCC-initiated:
      NSO pushes YANG/CLI config to the head-end router.
      The router (PCC) then signals the RSVP-TE LSP or SR policy itself.
      Uses CNCTunnelClient (cnc_tunnel.py).

  pce — PCE-initiated:
      The COE REST API instructs the PCE to take full control of the LSP.
      COE programs the router via PCEP — no config is pushed by NSO.
      Uses COETunnelOpsClient (coe_tunnel_ops_client.py).
"""
import os
from typing import Any
import structlog
from ..schemas.tunnels import TunnelConfig, TunnelResult

logger = structlog.get_logger(__name__)


def _bandwidth_mbps(config: TunnelConfig) -> int:
    """Convert bandwidth_gbps → Mbps integer for COE API (expects int32 Mbps)."""
    if config.bandwidth_gbps is None:
        return 0
    return int(config.bandwidth_gbps * 1000)


def _segment_list_from_config(config: TunnelConfig) -> list[dict]:
    """Build COE SR policy hops list from TunnelConfig explicit_hops or empty for dynamic."""
    if config.explicit_hops:
        return config.explicit_hops
    return []


def _coe_result_to_tunnel_result(raw: dict, te_type: str) -> TunnelResult:
    """Convert COE raw dict response → TunnelResult for unified handling downstream."""
    results = raw.get("output", {}).get("results", [])
    first = results[0] if results else {}
    state = first.get("state", "")
    success = state in ("success", "CREATED", "MODIFIED", "")  # COE may omit state on success
    tunnel_id = first.get("path-name") or first.get("color") or ""
    binding_sid = first.get("binding-sid") or first.get("binding-label")
    message = first.get("message", "COE operation complete")

    return TunnelResult(
        success=bool(success),
        tunnel_id=str(tunnel_id) if tunnel_id else None,
        binding_sid=int(binding_sid) if binding_sid else None,
        te_type=te_type,
        operational_status="unknown",
        state="success" if success else "failure",
        message=message,
    )


async def _create_via_pce(config: TunnelConfig) -> TunnelResult:
    """PCE-initiated path: COE REST API → PCE programs router via PCEP."""
    from ..tools.coe_tunnel_ops_client import get_coe_tunnel_ops_client
    coe = get_coe_tunnel_ops_client()

    if config.te_type in ("sr-mpls", "srv6"):
        color = config.color or 0
        raw = await coe.create_sr_policy_coe(
            head_end=config.head_end,
            color=color,
            end_point=config.end_point,
            segment_list=_segment_list_from_config(config),
        )
    else:
        # rsvp-te
        path_options: dict[str, Any] = {
            "optimization-objective": config.optimization_objective,
        }
        if config.explicit_hops:
            path_options["hops"] = config.explicit_hops
        raw = await coe.create_rsvp_tunnel(
            tunnel_name=config.path_name,
            source=config.head_end,
            destination=config.end_point,
            bandwidth=_bandwidth_mbps(config),
            path_options=path_options,
        )

    return _coe_result_to_tunnel_result(raw, config.te_type)


async def _create_via_nso(config: TunnelConfig, nso_mode: str, client: Any) -> TunnelResult:
    """PCC-initiated path: NSO pushes config to router; router signals the tunnel."""
    if config.te_type in ("sr-mpls", "srv6"):
        result = await client.create_sr_policy(config)
    else:
        # rsvp-te — prefer the NSO-native method which returns a job-id for async polling
        result = await client.create_rsvp_tunnel_via_nso(config)

    # Async NSO job polling: if the response contains a job-id marker, poll to completion
    if nso_mode == "async" and result.success and result.message.startswith("job-id:"):
        job_id = result.message.removeprefix("job-id:").strip()
        logger.info("Detected async NSO job, polling for completion", job_id=job_id)
        result = await client._poll_nso_job(job_id)

    return result


async def create_tunnel_node(state: dict[str, Any]) -> dict[str, Any]:
    """Create a tunnel via PCE-initiated (COE) or PCC-initiated (NSO) path.

    Environment variables:
      TUNNEL_PROVISIONING_MODE  "nso" (default) | "pce"
      NSO_PROVISIONING_MODE     "async" (default) | "sync"  — NSO path only
    """
    incident_id = state.get("incident_id")
    tunnel_payload = state.get("tunnel_payload", {})
    retry_count = state.get("retry_count", 0)

    nso_mode = os.getenv("NSO_PROVISIONING_MODE", "async").lower()

    config = TunnelConfig(**tunnel_payload)

    # Priority: per-tunnel config.provisioning_mode > TUNNEL_PROVISIONING_MODE env var > "nso"
    provisioning_mode = (
        config.provisioning_mode
        or os.getenv("TUNNEL_PROVISIONING_MODE", "nso")
    ).lower()

    logger.info(
        "Creating tunnel",
        incident_id=incident_id,
        retry=retry_count,
        te_type=config.te_type,
        provisioning_mode=provisioning_mode,
        per_tunnel_override=config.provisioning_mode is not None,
    )

    if provisioning_mode == "pce":
        # PCE-initiated: COE REST → PCEP → router (COE owns the LSP)
        logger.info("Using PCE-initiated path via COE", incident_id=incident_id)
        result = await _create_via_pce(config)
    else:
        # PCC-initiated (default): NSO pushes config → router signals tunnel
        logger.info("Using PCC-initiated path via NSO", incident_id=incident_id, nso_mode=nso_mode)
        from ..tools.cnc_tunnel import get_cnc_tunnel_client
        client = get_cnc_tunnel_client()
        result = await _create_via_nso(config, nso_mode, client)

    if result.success:
        logger.info("Tunnel created", incident_id=incident_id, tunnel_id=result.tunnel_id)
        return {
            "current_node": "create_tunnel",
            "nodes_executed": state.get("nodes_executed", []) + ["create_tunnel"],
            "tunnel_id": result.tunnel_id,
            "creation_success": True,
            "binding_sid": result.binding_sid,
        }
    else:
        logger.error("Tunnel creation failed", incident_id=incident_id, error=result.message)
        return {
            "current_node": "create_tunnel",
            "nodes_executed": state.get("nodes_executed", []) + ["create_tunnel"],
            "creation_success": False,
            "creation_error": result.message,
            "retry_count": retry_count + 1,
        }
