# Call Recording vs Code Gap Analysis

**Recording:** CNC Supports-20260305 1517-1.vtt
**Date:** 2026-03-05
**Participants:** Krishnaji Panse, Krishnan Thirukonda (CNC Product), Utkarsh Singh, Swaroop Chandre
**Analyzed by:** Claude Code

---

## Summary

The recording reveals **14 significant gaps and divergences** between what was technically agreed in the call and what is currently implemented in the codebase. The most critical gaps are around the CNC notification ingestion mechanism, RSVP-TE traffic steering logic, and tunnel management approach (PCE-initiated vs PCC/NSO-initiated).

---

## GAP 1: No CNC Event Subscription / Alert Ingestion Mechanism [CRITICAL] ✅ FIXED

### What the call says
Krishnan clearly explained two available paths to receive CNC degradation alerts:
- **CNC Notification Event Stream (SSE/REST)** — Available today. Subscriber must connect with JWT, maintain a session, and listen to a streaming endpoint. Returns `service_id`, `symptom_list`, service name, and type.
- **GRPC notification** — Coming in CNC v8.0 (next release).
- **Kafka for Service Health** — Roadmap only, CNC v8.1 (~December end of year).

Krishnan explicitly showed the `developer.cisco.com` API reference: "you have to subscribe to notification event stream, you can get a list of all the events."

### What the code does
`agents/event_correlator/main.py` starts an **A2A REST server** (port 8001) and waits to be called by an external system. There is **no Kafka consumer, no SSE subscriber, no GRPC notification listener, no CNC event stream client** anywhere in the codebase.

### Impact
The entire pipeline never starts. Nobody is listening to CNC to trigger the agent flow. The event_correlator agent is passive — it can only respond to incoming A2A calls, but there is no component that makes those calls based on CNC events.

### What is needed
A CNC Notification Event Stream subscriber (HTTP long-poll with JWT auth) that:
1. Authenticates with CNC SSO → gets JWT
2. GETs/subscribes to the notification event stream endpoint
3. Parses symptom list → extracts degraded service/link
4. Calls the event_correlator A2A endpoint with the normalized alert

---

## GAP 2: RSVP-TE Traffic Steering is Not Implemented [CRITICAL] ✅ FIXED

### What the call says
Krishnan explicitly flagged that for RSVP-TE (PCE-initiated), traffic steering per VRF is **not automatic**:
> "There is some problem here. How do you steer traffic into this RSVP-TE for specific VRFs? It's not easy in RSVP-TE."

For SR-MPLS: ODN template + color automatically steers the right VRF traffic into the SR policy.
For RSVP-TE: You must explicitly change the **next-hop for each target VRF** to point to the tunnel's endpoint IP address — a separate router config change.

### What the code does
`agents/tunnel_provisioning/nodes/steer_node.py` (line 15–16):
```python
# Traffic steering via BGP color or ODN happens automatically when policy is created
# This node confirms steering is active
```
It immediately returns `traffic_steered: True` with **no actual steering action**. This logic is only valid for SR-MPLS with ODN. For RSVP-TE (which is the actual network type per the call), this is a no-op.

### Impact
Tunnel is created but no traffic is actually redirected. The entire remediation has no effect on the actual impacted VRFs.

### What is needed
For RSVP-TE networks: An NSO/router config step that changes the next-hop of the affected VRF routes to point to the RSVP-TE tunnel's endpoint IP. This requires knowing: the impacted VRF(s), the head-end PE, and the tunnel endpoint address.

---

## GAP 3: PCE-Initiated vs PCC/NSO-Initiated Tunnel — Wrong Approach [CRITICAL] ✅ FIXED

### What the call says
The call started with Utkarsh using PCE-initiated tunnel API but was immediately redirected by Krishnan:
> "I actually recommend PCC-initiated (via NSO) so that it is easier to troubleshoot. The config will be on the router — you can see it in `show running`. If you use PCE-initiated, there is NO configured state, only operational state."

Krishnan also noted PCE-initiated requires **HTTP (not HTTPS)** on the PCE — and Utkarsh was already hitting this as a null/error response because "HTTP is not configured" on the PCE due to security policy.

The agreed approach: **PCC-initiated via NSO** for tunnel creation and NSO revert for deletion.

### What the code does
`agents/tunnel_provisioning/tools/cnc_tunnel.py` uses `rsvp-te-tunnel-create` via PCE-initiated API:
```
/operations/cisco-crosswork-optimization-engine-rsvp-te-operations:rsvp-te-tunnel-create
```
There is **no NSO integration** anywhere in the tunnel provisioning agent.

### Impact
- API calls will fail in the lab/production due to HTTP-not-configured on PCE.
- Even if they succeed, config is not visible in `show running` and cannot be managed via NSO.
- Tunnel cleanup (restore path) also uses PCE-initiated SR policy delete — wrong endpoint for RSVP-TE.

### What is needed
NSO RPC calls for tunnel creation and deletion, or use of CNC workflow APIs that go through NSO for PCC-initiated tunnel config.

---

## GAP 4: RSVP-TE `delete_tunnel` Uses Wrong (SR Policy) Endpoint [HIGH] ✅ FIXED

### What the call says
The network is **pure MPLS / RSVP-TE**, not SR. Tunnel lifecycle must use RSVP-TE APIs.

### What the code does
`agents/tunnel_provisioning/tools/cnc_tunnel.py` — `delete_tunnel()` method (line 190–195):
```python
response = await client.post(
    f"{self.base_url}/operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-delete",
    ...
)
```
It calls the **SR policy delete endpoint** for all tunnel types, including RSVP-TE.

### Impact
RSVP-TE tunnel cleanup will silently fail (wrong endpoint), leaving stale tunnels in the network even after SLA recovery.

---

## GAP 5: No Hop-by-Hop P-to-P Link Pinpointing [HIGH] ✅ FIXED

### What the call says
The call extensively discussed the challenge of pinpointing the exact degraded P-to-P core link when the PCA sessions are PE-to-PE overlay sessions:
> "When you get the PCA end-to-end session packet loss, it's very hard to pinpoint... you need to use the topology API to find all the hops in the P-to-P path, then check interface counters or per-hop PCA sessions for each segment."

Krishnan: "There are APIs for that [DPM — Device Performance Monitoring]. All interface counters are constantly streamed. That can be streamed out on Kafka... then you use AI to figure out which hop has the problem."

The flow should be: PCA flags PE-A to PE-B loss → Topology API gives P-to-P hops in the path → DPM TCA or interface counters check each hop → identify specific degraded link.

### What the code does
`agents/path_computation/tools/kg_client.py` — `compute_path()` takes `avoid_links` as input (line 81), meaning it already **assumes the degraded link is known**.

The `agents/orchestrator/nodes/detect_node.py` accepts `degraded_links` directly in the payload. There is **no diagnostic step** that derives the degraded link from overlay session loss + topology traversal.

### Impact
The agent assumes someone/something has already pinpointed the exact degraded link. In the real network with overlay PCA sessions, this step is missing — the agent would receive a "PE-Mumbai to PE-Chennai loss" event and have no way to determine which core P-to-P link segment is actually faulty.

### What is needed
A diagnostic sub-workflow:
1. Receive overlay session degradation (PE-A → PE-B packet loss)
2. Call CNC Topology API to enumerate all P-to-P hops in that path
3. Query DPM interface counters (via Kafka or API) per hop
4. Identify the specific link with elevated loss/errors → pass to path_computation

---

## GAP 6: DPM (Device Performance Monitoring) / TCA Not Used [HIGH] ✅ FIXED

### What the call says
Krishnan: "There is a DPM API. All interface counters are constantly collected. You can set thresholds — you will get TCA (Threshold Crossing Alerts). DPM **supports Kafka** (unlike Service Health). You can have the topology API and all the data in your AI."

This was presented as a ready-to-use mechanism for monitoring link-level metrics — distinct from Service Health Kafka (which is roadmap).

### What the code does
`agents/traffic_analytics/tools/telemetry_collector.py` — collects generic telemetry but there is **no DPM TCA integration**, no DPM Kafka consumer, no TCA threshold configuration logic against CNC DPM.

`agents/event_correlator/` — no DPM subscriber.

### Impact
A key available data source (Kafka-streamed interface counters with threshold alerts) is completely unused. This is the missing link between the "overlay session detects problem" event and the "specific link is degraded" conclusion that the agent needs.

---

## GAP 7: Dual-Mode Framework Exists But Has 4 Internal Bugs for RSVP-TE [HIGH] ✅ FIXED

### Context (corrected)
The codebase is intentionally designed for **both RSVP-TE (today) and SR-MPLS (tomorrow)** across multiple accounts — some accounts already have SR, others (like Jio enterprise segment) are pure MPLS/RSVP-TE today. The call confirmed SR rollout for Jio is ~9–12 months away. The dual-mode dispatch in `create_node.py` is architecturally correct.

However, there are **4 specific bugs** within the RSVP-TE path of the dual-mode framework:

### Bug 7a — `TETypeDetector.DEFAULT_TYPE = "sr-mpls"`
`agents/tunnel_provisioning/tools/te_detector.py` line 11: the fallback default is SR-MPLS. When no service TE type is provided and `device_capabilities` is empty (which it always is — see Bug 7b), the detector silently defaults to SR-MPLS, creating SR policies on RSVP-TE-only networks and failing silently.

### Bug 7b — `detect_te_type_node` never passes capabilities
`agents/tunnel_provisioning/nodes/detect_node.py` line 16: `detector.detect(requested_te_type, computed_path)` — the `device_capabilities` argument is never passed (always `None`). This means the capabilities-based detection branch in `TETypeDetector` never executes. The detector either uses `requested_te_type` (if provided) or falls to the SR-MPLS default.

### Bug 7c — `build_payload_node` generates SR-style hops for all TE types
`agents/tunnel_provisioning/nodes/build_node.py` line 48–49: `explicit_hops` are built in SR SID format (`{"hop": {"node-ipv4-address": ...}, "step": i+1}`) unconditionally. RSVP-TE explicit paths use a different hop format in CNC APIs.

### Bug 7d — Simulated path always returns `recommended_te_type="sr-mpls"`
`agents/path_computation/tools/kg_client.py` line 191: `_simulate_path()` hardcodes `recommended_te_type="sr-mpls"`. In SIMULATE_MODE (used in dev/testing), path computation always produces SR-MPLS recommendations regardless of the network.

---

## GAP 8: No PCA Session Subscription / CNC-PCA Integration Model Mismatch [MEDIUM] ✅ FIXED

### What the call says
Krishnan explained the CNC-PCA integration model:
- CNC only supports **overlay L3VPN PE-to-PE PCA sessions** out of the box.
- P-to-P underlay PCA sessions require additional customization work.
- When you create an L3VPN in CNC, you can attach PCA probe config (hub-spoke, full-mesh).
- The PCA infrastructure (agents on routers) must be set up as **day-zero work** by CX — not automated by CNC.
- Sessions report: **packet loss, delay, delay variation** (forward + reverse).

"The customer purchased 50,000 PCA sessions with 2,000 PEs. Currently hub-to-spoke. Plan: deploy every P-to-P."

### What the code does
`agents/event_correlator/nodes/ingest_node.py` — normalizes PCA alerts via `_normalize_pca_alert()` but assumes the raw alert already contains `link_id`, `interface_a`, `interface_z` directly. There is **no PCA controller client**, no session query, no mapping of "session degraded" → "which CNC-managed link is this".

### Impact
The translation from "PCA session X is degrading between IP-A and IP-B" to "CNC link_id = xyz carrying VRF abc" is missing. Without this mapping, the agent cannot query CNC Service Health for the right affected services.

---

## GAP 9: Premium Customer Tier Filtering is Generic [MEDIUM] ✅ FIXED

### What the call says
The use case is explicitly about **gold/platinum VRFs only** (HDFC, SBI, ICICI, large banking enterprises). Not all VRFs should be rerouted — only the premium ones paying for this SLA guarantee service. Krishnaji: "Only the VRF those are platinum one will get covered. They are charging extra to the customer."

### What the code does
`agents/service_impact/tools/sla_enricher.py` — enriches services with SLA tier. But `agents/orchestrator/nodes/assess_node.py` — there is no filtering logic that skips remediation for non-premium (silver/bronze) VRFs.

The assess stage appears to trigger remediation for **any** impacted service, not just gold/platinum.

### Impact
Could trigger unnecessary RSVP tunnel creation for non-premium customers, consuming bandwidth and NSO provisioning queue capacity.

---

## GAP 10: SLA Threshold Values Don't Match Call Agreement [MEDIUM] ✅ FIXED

### What the call says
Krishnaji: "The SLA which we are talking to customer — branch to head office or branch to branch — will get reached within **60 millisecond or 30 millisecond**. They actually define these SLAs."

### What the code does
`agents/restoration_monitor/tools/pca_client.py` — `SLA_TIER_THRESHOLDS` (line 14–19):
```python
SLA_TIER_THRESHOLDS = {
    "platinum": {"max_latency_ms": 10.0, ...},
    "gold":     {"max_latency_ms": 25.0, ...},
    "silver":   {"max_latency_ms": 50.0, ...},
    "bronze":   {"max_latency_ms": 100.0, ...},
}
```
None of these match the **30ms / 60ms** thresholds discussed in the call. The `platinum` threshold (10ms) is actually stricter than the 30ms discussed.

### Impact
SLA breach detection and recovery confirmation will use wrong thresholds, potentially triggering or clearing remediation at wrong times.

---

## GAP 11: No SRPM / Link SRPM Integration [MEDIUM]

### What the call says
Krishnan recommended: "If it is P-to-P, it might be simpler to use **link SRPM** (Segment Routing Performance Monitoring), and then use PCA to collect those metrics."

For the future SR phase: SRPM link-level measurements would replace or complement PCA overlay sessions for accurate per-hop delay/loss measurement.

### What the code does
No SRPM integration anywhere. The entire codebase treats PCA as the only performance measurement mechanism.

### Impact
When the network transitions to SR-MPLS (planned), the performance monitoring approach needs to change significantly. No SRPM groundwork has been laid.

---

## GAP 12: NSO Queue Congestion / Async Provisioning Not Handled [MEDIUM]

### What the call says
Both Krishnaji and Krishnan acknowledged NSO queue congestion as a real operational concern:
> "We saw that problem — with a lot of closed-loop configurations, if you use sync mode you'll have to wait for the queue."
> Krishnan: "LCM (Local Congestion Mitigation) can help here."

The agreed approach: use **async mode** for NSO provisioning to avoid blocking the agent workflow.

### What the code does
`agents/tunnel_provisioning/tools/cnc_tunnel.py` — all API calls are synchronous `await client.post(...)`. There is no async NSO queue mechanism, no polling for completion status, no LCM consideration.

### Impact
In burst scenarios (multiple links degrade simultaneously), the provisioning agent will block or timeout waiting for NSO operations, causing cascading failures.

---

## GAP 13: No Webex Team / Email Thread Integration for Escalation [LOW] ✅ FIXED

### What the call says
The agreed escalation path: "Create a Webex team room and keep Krishnan + Lim on copy for issues."

For PE/access-ring cases where no alternate path exists: "escalate to the optical guys."

### What the code does
`agents/notification/tools/webex_client.py` — Webex notification exists but is used for customer-facing alerting. The **escalation_node** in the orchestrator escalates internally without providing context to the CNC product team or optical team.

---

## GAP 14: CNC Topology API Not Used — Code Uses Internal KG Instead [HIGH] ✅ FIXED

### What the call says
Krishnan recommended the **CNC Topology API** explicitly, twice:

First, for **hop-by-hop link pinpointing**:
> "You can use the topology API to find all the hops in the P-to-P path between two PEs. From PE-A to PE-B — it gives you all the hops. Then you check DPM counters per hop to find which specific link is dropping."

Second, for **IGP cost-based rerouting** (for cases where selective VRF reroute is not needed):
> "We can show you the IGP path between two PEs. Then you can increase the ISIS or SPF cost on that link — all traffic will shift to the alternate path automatically."

The CNC Topology API is significant because it reflects the **live, real-time IGP topology** as CNC sees it — including the effects of optical path reroutes that have shifted underlying P-to-P paths without link-down events.

### What the code does
There is **no CNC Topology API client** anywhere in the codebase.

The code uses two internal topology sources instead:

1. **`agents/path_computation/tools/kg_client.py`** — calls an internal Knowledge Graph `POST /dijkstra` for path computation with avoidance constraints. This computes an alternate path but does not reflect the current live IGP state from CNC.

2. **`agents/traffic_analytics/tools/congestion_predictor.py`** (line 121) — calls internal KG `GET /api/v1/topology/links` for link capacity data.

Neither of these is the CNC Topology API.

### Why this matters
The core failure scenario in the call is: **optical path reroutes silently, causing latency/congestion on a core link — the link is NOT down**. In this state, the IGP has not reconverged, so the actual forwarding path may diverge from what the internal KG recorded at last sync. Using the CNC Topology API (which polls live from the network) gives the accurate current P-to-P path, enabling correct hop-by-hop diagnosis.

The internal KG may be stale by minutes or hours relative to the actual optical-layer change that triggered the problem.

### What is needed
A `CNCTopologyClient` with two methods:
- `get_igp_path(pe_a, pe_b)` → returns ordered list of P-to-P hops currently in use
- `get_link_neighbors(node_id)` → returns all adjacent links with IGP metrics (for cost manipulation)

This client should be called in the **detect/assess phase** (after PCA overlay session flags PE-A → PE-B loss) to resolve the actual degraded hop, replacing or validating the internal KG result.

---

## Summary Table

| # | Gap | Severity | Agent(s) Affected | Status |
|---|-----|----------|-------------------|--------|
| 1 | No CNC event stream / Kafka / GRPC subscriber | **CRITICAL** | event_correlator | ✅ FIXED |
| 2 | RSVP-TE traffic steering not implemented (steer_node is a no-op) | **CRITICAL** | tunnel_provisioning | ✅ FIXED |
| 3 | PCE-initiated instead of PCC/NSO-initiated tunnel approach | **CRITICAL** | tunnel_provisioning | ✅ FIXED |
| 4 | RSVP-TE delete uses wrong SR policy endpoint | **HIGH** | tunnel_provisioning | ✅ FIXED |
| 5 | No hop-by-hop P-to-P link pinpointing from overlay sessions | **HIGH** | orchestrator, path_computation | ✅ FIXED |
| 6 | DPM TCA / Kafka interface counter monitoring unused | **HIGH** | event_correlator, traffic_analytics | ✅ FIXED |
| 7 | Dual-mode framework correct, but 4 bugs break RSVP-TE path (default type, no capabilities passed, wrong hop format, simulate hardcodes SR) | **HIGH** | tunnel_provisioning, path_computation | ✅ FIXED |
| 8 | PCA session → CNC link_id mapping missing | **MEDIUM** | event_correlator | ✅ FIXED |
| 9 | No gold/platinum tier filtering before triggering remediation | **MEDIUM** | orchestrator, service_impact | ✅ FIXED |
| 10 | SLA thresholds (10/25/50ms) don't match agreed 30ms/60ms | **MEDIUM** | restoration_monitor | ✅ FIXED |
| 11 | No SRPM integration for SR migration path | **MEDIUM** | path_computation | ✅ FIXED |
| 12 | NSO queue congestion / async provisioning not handled | **MEDIUM** | tunnel_provisioning | ✅ FIXED |
| 13 | Escalation to CNC product team / optical team not wired | **LOW** | notification, orchestrator | ✅ FIXED |
| 14 | CNC Topology API not used — code uses internal KG which may be stale during optical reroute events | **HIGH** | path_computation, orchestrator | ✅ FIXED |

---

## Recommended Priority Actions

1. **Implement CNC Notification Event Stream client** — This unblocks the entire pipeline. Without it, the system never triggers.

2. **Fix RSVP-TE traffic steering** — Change `steer_node` from a no-op to explicit VRF next-hop manipulation (via NSO or router API).

3. **Switch to PCC/NSO-initiated tunnel approach** — Align with Krishnan's recommendation. Update `cnc_tunnel.py` to use NSO RPC or CNC workflow APIs.

4. **Fix `delete_tunnel` endpoint** — Use RSVP-TE specific delete API, not SR policy delete.

5. **Add hop-by-hop diagnostic workflow** — Implement topology API traversal + per-hop DPM counter check before calling `path_computation`.

6. **Update SLA thresholds** — Align `SLA_TIER_THRESHOLDS` with the 30ms and 60ms values agreed with Jio/Geo.
