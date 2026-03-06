# How This Use Case Works — End-to-End

**Cisco AI Use Case: Automated Customer Experience Management**
**Crosswork + LangGraph Multi-Agent System**
**Author: Krishnaji Panse, APJ SP CTO**

---

## 1. What Problem This Solves

Service providers carry Platinum and Gold tier customer traffic (L3VPN / L2VPN) over IP/MPLS and SRv6 backbones. When a link degrades — not necessarily fails completely, just gets congested or lossy — SLA thresholds are breached before any human is even aware.

This system **automatically detects** SLA breaches, **identifies which customer services are affected**, **computes an alternate path**, **provisions a protection tunnel** (RSVP-TE or SR policy), **steers traffic** onto it, **waits for the original path to recover**, then **cuts traffic back** and cleans up — all without human intervention, in under 60 seconds.

Additionally, the **Traffic Analytics** agent runs continuously and **proactively detects congestion** before SLA breach occurs, giving the Orchestrator early warning.

---

## 2. System Architecture — 9 Agents

```
                            ┌──────────────────────┐
    CNC SSE Stream ─────────►                      │
    Kafka TCA Alerts ───────►   ORCHESTRATOR       │ :8000
    PCA Alerts ─────────────►   (Supervisor)       │
    Traffic Analytics ──────►                      │
                            └──────────┬───────────┘
                                       │ A2A / HTTP
          ┌──────────┬─────────────────┼──────────┬──────────┬──────────┬──────────┐
          ▼          ▼                 ▼          ▼          ▼          ▼          ▼
    ┌──────────┐┌──────────┐    ┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
    │  Event   ││ Service  │    │  Path    ││  Tunnel  ││Restoration│ Traffic  ││  Notify  ││  Audit  │
    │Correlator││  Impact  │    │ Compute  ││Provision ││  Monitor ││Analytics ││          ││         │
    │  :8001   ││  :8002   │    │  :8003   ││  :8004   ││  :8005   ││  :8006   ││  :8007   ││  :8008  │
    └──────────┘└──────────┘    └──────────┘└──────────┘└──────────┘└──────────┘└──────────┘└──────────┘
```

| # | Agent | Role |
|---|-------|------|
| 1 | Orchestrator | Supervisor state machine. Receives events, drives the protection workflow, coordinates all agents via A2A |
| 2 | Event Correlator | Receives raw PCA/CNC alarms, deduplicates, correlates, detects link flapping, emits clean incidents |
| 3 | Service Impact | Queries CNC CAT to find which L3VPN/L2VPN services traverse the degraded links |
| 4 | Path Computation | Queries Knowledge Graph (BGP-LS + Dijkstra) for alternate path avoiding degraded links, enriched with live CNC topology |
| 5 | Tunnel Provisioning | Creates RSVP-TE or SR policy via NSO (PCC) or COE/PCEP (PCE), verifies UP, steers traffic |
| 6 | Restoration Monitor | Polls SLA metrics every 30s; when original path recovers, manages hold timer, cutover, and cleanup |
| 7 | Traffic Analytics | Continuously collects telemetry (SR-PM, MDT, NetFlow, COE metrics); builds demand matrix; predicts congestion proactively |
| 8 | Notification | Sends alerts to Webex, ServiceNow, Email based on severity and SLA tier |
| 9 | Audit | Logs all actions to Elasticsearch for compliance and post-incident review |

---

## 3. Two Entry Points

### Path A — Reactive: SLA Degradation Detected

```
CNC SSE / PCA alarm → Event Correlator → Orchestrator → protection workflow
```

### Path B — Proactive: Traffic Analytics Predicts Congestion

```
SR-PM + MDT + COE metrics (every 5 min) → Traffic Analytics → Orchestrator → protection workflow
```

Both paths converge at the Orchestrator and trigger the same downstream flow.

---

## 4. End-to-End Workflow — Step by Step

### PHASE 1: Alert Ingestion and Correlation

#### Trigger Sources
- **CNC SSE Notification Stream** — real-time events from Crosswork (link state, SLA threshold crossing)
- **DPM Kafka TCA** — Threshold Crossing Alerts from telemetry (latency, jitter, loss)
- **PCA (Path Computation Agent)** — proactive SLA alerts

#### Agent: Event Correlator (port 8001)

**Workflow:** `INGEST → DEDUP → CORRELATE → FLAP_DETECT → EMIT | SUPPRESS | DISCARD`

| Node | Action | Data In | Data Out |
|------|--------|---------|----------|
| `ingest` | Parse and normalize raw alert to standard schema | Raw alert dict (source, type, timestamp, link IDs) | `normalized_alert`: `{alert_id, source_pe, dest_pe, link_id, metric, value, threshold, severity}` |
| `dedup` | Check Redis for duplicate alert within 60s window | `normalized_alert` | `is_duplicate: bool`, `duplicate_of: alert_id` |
| `correlate` | Group related alerts (same link, different metrics) | Multiple `normalized_alert`s | `correlated_alerts: list`, `degraded_links: list` |
| `flap_detect` | Check if link has been bouncing (>3 state changes in 5 min) | `correlated_alerts` | `is_flapping: bool`, `flap_count: int` |
| `emit` | POST incident to Orchestrator via A2A | Clean incident dict | `emitted: True` |
| `suppress` | Hold for dampen period, don't emit | — | `suppressed: True` |
| `discard` | Drop duplicate | — | `discarded: True` |

**APIs called:** None — internal Redis lookup for dedup state.

**Output to Orchestrator:**
```json
{
  "incident_id": "INC-2026-001",
  "degraded_links": ["te:1.1.1.1_2.2.2.2", "te:1.1.1.1_3.3.3.3"],
  "source_pe": "PE-Mumbai-01",
  "dest_pe": "PE-Delhi-02",
  "severity": "critical",
  "sla_metric": "latency_ms",
  "measured_value": 45.2,
  "threshold": 30.0,
  "alert_source": "pca"
}
```

---

### PHASE 2: Service Impact Assessment

#### Agent: Service Impact (port 8002)

Called by Orchestrator via A2A with `degraded_links` list.

**Workflow:** `QUERY_SERVICES → ANALYZE_IMPACT → ENRICH_SLA → RETURN_AFFECTED`

| Node | Action | API Called | Data Out |
|------|--------|-----------|---------|
| `query_services` | Find all VPN services on degraded links | **CNC CAT RESTCONF** | `raw_services: list` |
| `analyze_impact` | Determine severity, count affected services by type | Internal | `impact_assessment`, `services_by_tier`, `total_affected` |
| `enrich_sla` | Add SLA tier (Platinum/Gold/Silver/Bronze) and priority score | Internal SLA DB | `affected_services` sorted by priority |
| `return_affected` | Return to Orchestrator | — | Final payload |

**APIs called by `query_services`:**

| API | Endpoint | Purpose |
|-----|----------|---------|
| CAT L3VPN Services | `GET /restconf/data/ietf-l3vpn-svc:l3vpn-svc/vpn-services` | All L3VPN service configs |
| CAT L3VPN Operational | `GET /restconf/data/ietf-l3vpn-oper:l3vpn-oper/vpn-services` | Operational state of L3VPNs |
| CAT L3VPN Discovered Transports | `GET /restconf/data/ietf-l3vpn-oper:l3vpn-oper/vpn-services/{id}/discovered-transport-data` | Which transport links carry this VPN |
| CAT L2VPN Services | `GET /restconf/data/ietf-l2vpn-svc:l2vpn-svc/vpn-services` | L2VPN service configs |
| CAT L2VPN Operational | `GET /restconf/data/ietf-l2vpn-oper:l2vpn-oper/vpn-services` | L2VPN operational state |
| CNC Service Health (Assurance Graph) | `GET /crosswork/aa/agmgr/v1/health` | Health status of services |

**Authentication:** All CNC calls use JWT. TGT → JWT exchange at startup, auto-refresh 5 min before 8h expiry.

**Output to Orchestrator:**
```json
{
  "affected_services": [
    {"service_id": "L3VPN-Jio-Platinum-001", "tier": "platinum", "type": "l3vpn", "head_end": "PE-Mumbai-01"},
    {"service_id": "L3VPN-Gold-Corp-007", "tier": "gold", "type": "l3vpn", "head_end": "PE-Mumbai-01"}
  ],
  "auto_protect_required": true,
  "highest_priority_tier": "platinum",
  "total_affected": 12
}
```

**Decision at Orchestrator:**
- Platinum or Gold tier → proceed with auto-protection
- Silver / Bronze → notify only, no tunnel provisioning

---

### PHASE 3: Path Computation

#### Agent: Path Computation (port 8003)

Called by Orchestrator with `degraded_links`, `source_pe`, `destination_pe`, `required_sla`.

**Workflow:** `BUILD_CONSTRAINTS → QUERY_KG → VALIDATE_PATH → [RELAX → QUERY_KG loop] → RETURN_PATH`

| Node | Action | API Called | Data Out |
|------|--------|-----------|---------|
| `build_constraints` | Build avoidance constraints: exclude degraded links, SRLGs, disjoint from existing policies | Internal `ConstraintBuilder` | `constraints: PathConstraints` |
| `query_kg` | **Step 1:** Get live topology path hint from CNC | **CNC COE Topology** `get_igp_path(pe_a, pe_b)` | `topology_path_hint: [hops]` |
| `query_kg` | **Step 2:** Get SR-PM link metrics for path | **SRPM Client** `get_path_metrics(segment_list)` | `srpm_metrics` |
| `query_kg` | **Step 3:** Compute optimal path via KG Dijkstra | **Knowledge Graph Dijkstra API** | `computed_path: Path` |
| `validate_path` | Check computed path meets SLA: Platinum ≤30ms, Gold ≤60ms | Internal | `path_valid: bool`, `violations: list` |
| `relax_constraints` | If no valid path: progressively loosen constraints (Level 1: allow SRLGs, Level 2: allow shared risk) | Internal | Relaxed `constraints` |
| `return_path` | Return best valid path | — | Final path payload |

**APIs called by `query_kg`:**

| API | Client | Endpoint | Purpose |
|-----|--------|----------|---------|
| CNC IGP Path | `CNCTopologyClient.get_igp_path()` | `GET /crosswork/nbi/cat-topology/v1/...` | Live IGP hop-by-hop path between PEs |
| CNC Network Links | `CNCTopologyClient.get_network_topology_links()` | `GET /restconf/data/ietf-network:networks/network/{id}/link/{link-id}` | Link state and metrics |
| CNC RSVP Tunnels | `CNCTopologyClient.get_all_rsvp_tunnels()` | `GET /restconf/data/coe-rsvp-te-lsp-details:rsvp-te-lsp-details` | Existing tunnel inventory |
| CNC SR Policies | `CNCTopologyClient.get_all_sr_policy_details()` | `GET /restconf/data/coe-sr-policy-details:sr-policy-details` | Existing SR policy inventory |
| SR-PM Link Metrics | `SRPMClient.get_link_metrics()` | SR-PM internal API | Current utilisation per link |
| SR-PM Path Metrics | `SRPMClient.get_path_metrics()` | SR-PM internal API | Latency, jitter, loss on path |
| KG Dijkstra | `KGClient.compute_path()` | KG HTTP API | Shortest path with avoidance |

**Output to Orchestrator:**
```json
{
  "path_found": true,
  "path_valid": true,
  "computed_path": {
    "path_id": "PATH-001",
    "hops": ["PE-Mumbai-01", "P-Pune-01", "P-Hyderabad-01", "PE-Delhi-02"],
    "total_delay_ms": 22.4,
    "total_hops": 4,
    "segment_list": ["16001", "16050", "16030"]
  },
  "topology_path_hint": [...],
  "srpm_metrics": {"latency_ms": 22.4, "utilization_pct": 34}
}
```

---

### PHASE 4: Tunnel Provisioning

#### Agent: Tunnel Provisioning (port 8004)

Called by Orchestrator with computed path, head_end, end_point, te_type, service requirements.

**Workflow:** `DETECT_TE → BUILD_PAYLOAD → CREATE_TUNNEL → VERIFY_TUNNEL → STEER_TRAFFIC → RETURN`

| Node | Action | API Called | Data Out |
|------|--------|-----------|---------|
| `detect_te_type` | Determine tunnel type: `rsvp-te`, `sr-mpls`, or `srv6` | CNC device capabilities | `detected_te_type` |
| `build_payload` | Build `TunnelConfig`: allocate BSID, set path, bandwidth, priority | BSID Allocator | `tunnel_payload: TunnelConfig` |
| `create_tunnel` | **Branch on TUNNEL_PROVISIONING_MODE** | See below | `tunnel_id`, `creation_success` |
| `verify_tunnel` | Confirm tunnel is operationally UP | See below | `tunnel_verified`, `operational_status` |
| `steer_traffic` | Activate traffic forwarding into tunnel | See below | `traffic_steered`, `policy_verified` |
| `return_success` | Return tunnel details to Orchestrator | — | Final result |

#### TE Type Detection (`detect_node.py`)

| Priority | Check | Outcome |
|----------|-------|---------|
| 1st | Service config specifies TE type | Use that |
| 2nd | Device capability query | `rsvp-te` if router has TE enabled, `sr-mpls` if SR is preferred |
| 3rd | `DEFAULT_TE_TYPE` env var | Default `rsvp-te` |

#### CREATE_TUNNEL — Two Provisioning Paths

**Provisioning Mode Selection:**
```
tunnel_payload.provisioning_mode  (per-tunnel, highest priority)
        ↓ if None
TUNNEL_PROVISIONING_MODE env var  (system default)
        ↓ if not set
"nso"                             (built-in default)
```

---

##### PATH A: NSO / PCC-Initiated (`TUNNEL_PROVISIONING_MODE=nso`)

> NSO pushes YANG/CLI config to the router. Config IS visible on the device. The router (PCC) signals the tunnel itself.

**For RSVP-TE:**

| Step | API | Endpoint | Payload |
|------|-----|----------|---------|
| 1 | `CNCTunnelClient.create_rsvp_tunnel_via_nso()` | `POST /crosswork/nbi/nso/v1/restconf/data/cisco-rsvp-te:rsvp-te/tunnel` | `{tunnel-name, source, destination, bandwidth, path-option}` |
| 2 (async) | `CNCTunnelClient._poll_nso_job()` | `GET /crosswork/nbi/nso/v1/job/{job-id}` | Poll every 3s, up to 30s |
| Router result | — | `show mpls traffic-eng tunnels` on head-end | Config visible: `interface Tunnel100` |

**For SR-MPLS / SRv6:**

| Step | API | Endpoint | Payload |
|------|-----|----------|---------|
| 1 | `CNCTunnelClient.create_sr_policy()` | `POST /crosswork/nbi/cat-inventory/v1/restconf/data/cisco-sr-te-cfp:sr-te/sr-policies/sr-policy` | `{head-end, color, end-point, path-name, segment-list}` |
| Router result | — | `show segment-routing traffic-eng policy` | Config visible on router |

---

##### PATH B: PCE-Initiated via COE (`TUNNEL_PROVISIONING_MODE=pce`)

> COE REST API instructs the PCE. PCE programs router via PCEP. **NO config on router.** Tunnel exists only in LFIB as PCEP-delegated LSP.

**For RSVP-TE:**

| Step | API | Endpoint | Payload |
|------|-----|----------|---------|
| 1 | `COETunnelOpsClient.create_rsvp_tunnel()` | `POST /operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:rsvp-te-tunnel-create` | `{rsvp-te-tunnels: [{head-end, end-point, path-name, signaled-bandwidth, rsvp-te-tunnel-path}]}` |
| COE → PCE | Internal | PCE computes path | — |
| PCE → Router | PCEP PCInitiate | RFC 8281 | LSP installed in LFIB, NOT in running-config |

**For SR-MPLS / SRv6:**

| Step | API | Endpoint | Payload |
|------|-----|----------|---------|
| 1 | `COETunnelOpsClient.create_sr_policy_coe()` | `POST /operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-create` | `{sr-policies: [{head-end, end-point, color, sr-policy-path}]}` |
| PCE → Router | PCEP | SR-TE policy installed dynamically | — |

---

#### VERIFY_TUNNEL

| Mode | API | Check |
|------|-----|-------|
| NSO/PCC | `CNCTunnelClient.verify_tunnel(tunnel_id, te_type)` | Queries CNC for `operational-status == "up"` |
| PCE (RSVP-TE) | `COETunnelOpsClient.get_rsvp_tunnel(head_end, end_point, tunnel_id)` | Filters `rsvp-datalist` for matching entry, checks `operational-status` |
| PCE (SR) | `COETunnelOpsClient.get_sr_policy_details(head_end, end_point, color)` | Filters `sr-policy-datalist`, checks `operational-status` |

If verify fails → retry create (up to 3 times).

---

#### STEER_TRAFFIC

| TE Type | Steering Mechanism | API |
|---------|-------------------|-----|
| SR-MPLS / SRv6 | **ODN (On-Demand Next-Hop) auto-steering via BGP color** — no explicit API needed. Traffic automatically follows SR policy color | `CNCSRTEConfigClient.get_sr_policy()` to verify policy exists on CAT |
| RSVP-TE | **Manual VRF next-hop update** via NSO RESTCONF | `POST {CNC_NSO_URL}/api/running/devices/device/{head_end}/config/vrf-steering` — updates BGP next-hop per VRF to point at tunnel endpoint |

---

**Output to Orchestrator:**
```json
{
  "tunnel_id": "Tunnel100",
  "tunnel_verified": true,
  "traffic_steered": true,
  "binding_sid": 16100,
  "operational_status": "up",
  "provisioning_mode": "nso"
}
```

---

### PHASE 5: Restoration Monitoring

#### Agent: Restoration Monitor (port 8005)

Started by Orchestrator after tunnel is active. Runs until original path recovers.

**Workflow:** `POLL_SLA → CHECK_RECOVERY → [WAIT 30s → POLL loop] → START_TIMER → WAIT_TIMER → VERIFY_STABILITY → CUTOVER_TRAFFIC → CLEANUP_TUNNEL → RETURN`

| Node | Action | API Called | Data |
|------|--------|-----------|------|
| `poll_sla` | Query PCA for current SLA metrics on original path | `PCAClient.get_path_sla(endpoints, tier)` | `current_metrics: {latency_ms, jitter_ms, packet_loss_pct, meets_sla}` |
| `check_recovery` | **Step 1:** Check SLA metrics | Internal | `sla_recovered: bool` |
| `check_recovery` | **Step 2:** Verify no services still impacted | `ServiceHealthClient.get_impacted_services(transport_ids)` → `GET /crosswork/aa/agmgr/v1/impacted-services` | `impacted_service_count`, `impacted_service_ids` |
| Recovery logic | `sla_recovered=True` AND `impacted_count=0` → `hold_timer` / else → `monitoring` | — | `status` |
| `wait_poll` | Sleep 30 seconds | — | — |
| `start_timer` | Start hold timer (Platinum: 300s, Gold: 600s) | `HoldTimer.start()` | `timer_id`, `timer_started: True` |
| `wait_timer` | Block until timer expires or cancels | `HoldTimer.wait()` | `timer_expired: bool` |
| `verify_stability` | Confirm SLA still stable after hold period | `PCAClient` again | `stability_verified: bool` |
| `cutover_traffic` | Restore traffic to original path | `CutoverClient.execute_cutover()` | `cutover_complete: bool` |
| `cleanup_tunnel` | Delete protection tunnel and release BSID | `TunnelDeleter.delete()` | `tunnel_deleted: bool` |
| `return_restored` | Report restoration complete | — | Duration, summary |

**SLA Thresholds:**
- Platinum: ≤ 30ms latency
- Gold: ≤ 60ms latency

**APIs called by `check_recovery` (Service Health):**

| API | Base URL | Endpoint | Purpose |
|-----|----------|----------|---------|
| Impacted Services | `/crosswork/aa/agmgr/v1` | `POST /impacted-services` with transport IDs | Which services still show impact |
| Historical Metrics | `/crosswork/aa/aaapp/v1` | `GET /historical-data/{subservice-id}` | Historical SLA timeline |
| Probe Status | `/crosswork/probemgr/v1` | `GET /probe-status` | Active measurement probe health |

---

### PHASE 6: Notification (Parallel with all phases)

#### Agent: Notification (port 8007)

Triggered by Orchestrator at every major state transition.

**Workflow:** `SELECT_CHANNEL → FORMAT_MESSAGE → SEND → LOG → RETURN`

| Event | Channel | Recipients |
|-------|---------|-----------|
| SLA breach detected | Webex + ServiceNow ticket | NOC team |
| Protection tunnel UP | Webex | NOC team |
| Platinum SLA impacted | Webex + Email | NOC + Account team |
| Restoration complete | Webex + ServiceNow update + Email | NOC + Account team |
| Monitoring timeout (no recovery) | Webex + Email escalation | NOC + Optical team + CNC team |

---

### PHASE 7: Audit (Background)

#### Agent: Audit (port 8008)

Captures every state transition to Elasticsearch.

```json
{
  "incident_id": "INC-2026-001",
  "timestamp": "2026-03-06T10:00:00Z",
  "event": "tunnel_created",
  "agent": "tunnel_provisioning",
  "tunnel_id": "Tunnel100",
  "provisioning_mode": "nso",
  "te_type": "rsvp-te",
  "duration_ms": 4200
}
```

---

## 5. Traffic Analytics — Proactive Path (Parallel Workflow)

This agent runs independently on a schedule (every 5 minutes). If it detects congestion risk, it alerts the Orchestrator which can pre-provision tunnels before SLA breach occurs.

**Workflow:** `COLLECT_TELEMETRY → BUILD_MATRIX → PREDICT_CONGESTION → [ANALYZE_RISK → EMIT_ALERT | WARN] → STORE_METRICS`

### Step 1: COLLECT_TELEMETRY

Sources collected simultaneously:

| Source | Client | API/Mechanism | Data |
|--------|--------|--------------|------|
| SR-PM | `TelemetryCollector` | SR Performance Measurement API | Per-LSP delay, loss, BW |
| MDT | `TelemetryCollector` | gRPC Model-Driven Telemetry | Interface counters, queue depths |
| NetFlow | `TelemetryCollector` | NetFlow collector | Flow bytes/packets per PE pair |
| COE IGP Links | `COEMetricsClient.get_igp_links_metrics()` | `GET /crosswork/optimization-engine/.../igp-links` | Link utilisation |
| COE SR Policies | `COEMetricsClient.get_sr_policies_metrics()` | `GET /crosswork/optimization-engine/.../sr-policies` | SR policy performance |
| COE RSVP Tunnels | `COEMetricsClient.get_rsvp_policies_metrics()` | `GET /crosswork/optimization-engine/.../rsvp-policies` | RSVP tunnel metrics |

**Additional COE operations (on-demand):**

| Operation | Method | Endpoint | Purpose |
|-----------|--------|----------|---------|
| SR Policy Metrics | `get_sr_policy_metrics(head_end, color, end_point)` | `POST /operations/..:get-sr-policy-metrics` | Per-policy detail metrics |
| SR Policies on Interface | `get_sr_policies_on_interface(node, interface)` | `POST /operations/..:get-sr-policies-on-interface` | Which policies use this interface |
| SR Policies on Node | `get_sr_policies_on_node(node_id)` | `POST /operations/..:get-sr-policies-on-node` | All policies through a node |
| Optimization Plan | `get_optimization_plan()` | `POST /operations/..:get-optimization-plan` | COE's recommended TE optimization |
| NPM Metrics | `get_npm_metrics()` | `POST /api/v1/lsp/utilizations` | Network Performance Monitor LSP data |

### Step 2: BUILD_MATRIX

Builds PE-to-PE traffic demand matrix:

```
        PE1     PE2     PE3     PE4
   PE1   -    10Gbps   5Gbps   2Gbps
   PE2  8Gbps   -      3Gbps   7Gbps
   PE3  4Gbps  6Gbps    -     12Gbps
   PE4  1Gbps  9Gbps   2Gbps    -
```

### Step 3: PREDICT_CONGESTION

EMA-smoothed utilisation prediction per link. Threshold:
- < 70% utilisation → store metrics, done
- ≥ 70% → analyze risk

### Step 4: ANALYZE_RISK → EMIT_ALERT

| Risk Level | Condition | Action |
|------------|-----------|--------|
| High | > 85% utilisation, Platinum/Gold services at risk | Emit proactive alert to Orchestrator → pre-provision tunnel |
| Medium | 70–85% utilisation | Warn NOC via Webex |
| Low | < 70% | Log to Elasticsearch only |

---

## 6. CNC API Reference — All APIs Used

### Authentication (All Agents)

```
POST /crosswork/sso/v1/tickets              → TGT (Ticket-Granting Ticket)
POST /crosswork/sso/v1/tickets/{tgt}        → JWT (8h TTL)
Auto-refresh: 5 min before expiry
Header: Authorization: Bearer {jwt}
```

### CAT (Crosswork Active Topology) APIs

| Agent | API Group | Base Path | Operations |
|-------|-----------|-----------|-----------|
| Service Impact | L3VPN Config | `/crosswork/nbi/cat-inventory/v1/restconf/data/ietf-l3vpn-svc:l3vpn-svc` | GET vpn-services, GET vpn-service/{id} |
| Service Impact | L3VPN Operational | `/crosswork/nbi/cat-inventory/v1/restconf/data/ietf-l3vpn-oper:l3vpn-oper` | GET vpn-services, GET discovered-transport-data |
| Service Impact | L2VPN Config | `/crosswork/nbi/cat-inventory/v1/restconf/data/ietf-l2vpn-svc:l2vpn-svc` | GET vpn-services |
| Service Impact | L2VPN Operational | `/crosswork/nbi/cat-inventory/v1/restconf/data/ietf-l2vpn-oper:l2vpn-oper` | GET vpn-services |
| Tunnel Provisioning | SR-TE Config (CAT) | `/crosswork/nbi/cat-inventory/v1/restconf/data/cisco-sr-te-cfp:sr-te/sr-policies` | CREATE, GET, UPDATE segment-list, DELETE, LIST |
| Tunnel Provisioning | NSO Connector | `/crosswork/nbi/nso/v1/restconf/data` | CREATE rsvp-te tunnel, GET job status |

### COE (Crosswork Optimization Engine) APIs

| Agent | API Group | Base Path | Operations |
|-------|-----------|-----------|-----------|
| Path Computation | Topology IETF Networks | `/crosswork/nbi/cat-topology/v1/restconf/data/ietf-network:networks` | GET all networks, GET network/{id}, GET node, GET link |
| Path Computation | RSVP-TE LSP Details | `/restconf/data/coe-rsvp-te-lsp-details:rsvp-te-lsp-details` | GET all tunnels, GET by headend/endpoint/tunnel-id |
| Path Computation | SR Policy Details | `/restconf/data/coe-sr-policy-details:sr-policy-details` | GET all policies, GET by headend/endpoint/color |
| Tunnel Provisioning | RSVP-TE Tunnel Ops | `/operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:` | rsvp-te-tunnel-create, delete, modify, dryrun |
| Tunnel Provisioning | SR Policy Ops | `/operations/cisco-crosswork-optimization-engine-sr-policy-operations:` | sr-policy-create, delete, modify, dryrun |
| Traffic Analytics | Performance Metrics | `/crosswork/optimization-engine/v1` | GET igp-links, GET sr-policies, GET rsvp-policies |
| Traffic Analytics | COE Operations | `/operations/cisco-crosswork-optimization-engine:` | get-sr-policy-metrics, get-sr-policies-on-interface, get-sr-policies-on-node, get-optimization-plan |
| Traffic Analytics | NPM | `/api/v1/lsp/utilizations` | POST for LSP utilisation data |

### CNC Service Health APIs

| Agent | API Group | Base Path | Operations |
|-------|-----------|-----------|-----------|
| Restoration Monitor | Assurance Graph | `/crosswork/aa/agmgr/v1` | POST impacted-services (by transport IDs) |
| Restoration Monitor | Historical Data | `/crosswork/aa/aaapp/v1` | GET historical-data/{id}, GET service/{id}, GET timeline/{id} |
| Restoration Monitor | Probe Manager | `/crosswork/probemgr/v1` | GET probe-status |

---

## 7. Data State Flow — What Each Agent Passes to the Next

```
EVENT CORRELATOR
  ↓  incident_id, degraded_links, source_pe, dest_pe, severity

ORCHESTRATOR (receives, dispatches in parallel)
  ├──► SERVICE IMPACT
  │      ↓  affected_services[], auto_protect_required, highest_priority_tier
  │
  ├──► PATH COMPUTATION (only if auto_protect_required=True)
  │      ↓  computed_path{hops, delay_ms, segment_list}, topology_path_hint, srpm_metrics
  │
  └──► NOTIFICATION (SLA breach alert)

ORCHESTRATOR (receives path, dispatches)
  └──► TUNNEL PROVISIONING
         ↓  tunnel_id, tunnel_verified, traffic_steered, binding_sid, provisioning_mode

ORCHESTRATOR (receives tunnel, dispatches)
  ├──► RESTORATION MONITOR (long-running)
  │      ↓  [polling every 30s] sla_recovered, impacted_service_count
  │      ↓  [when recovered] cutover_complete, tunnel_deleted, duration_seconds
  │
  └──► NOTIFICATION (tunnel UP alert)
       AUDIT (log all events)

RESTORATION MONITOR completion
  └──► ORCHESTRATOR
         └──► NOTIFICATION (restoration complete)
              AUDIT (final log)
```

---

## 8. Environment Variables — Configuration Reference

### CNC Connectivity
```bash
CNC_URL=https://cnc.example.com:30603       # Crosswork base URL
CNC_COE_URL=https://cnc.example.com:30609   # COE REST API
CNC_SH_URL=https://cnc.example.com:30613    # Service Health
CNC_PM_URL=https://cnc.example.com:30621    # Performance Metrics
CNC_NPM_URL=https://cnc.example.com:30625   # Network Performance Monitor
CNC_NSO_URL=https://cnc.example.com:8888    # NSO northbound
CNC_L3VPN_OPER_URL=...                      # L3VPN operational data
CNC_L2VPN_OPER_URL=...                      # L2VPN operational data
CNC_USERNAME=admin
CNC_PASSWORD=...
```

### Tunnel Provisioning
```bash
TUNNEL_PROVISIONING_MODE=nso    # "nso" (PCC, config on router) | "pce" (PCE, no config on router)
NSO_PROVISIONING_MODE=async     # "async" | "sync"
DEFAULT_TE_TYPE=rsvp-te         # "rsvp-te" | "sr-mpls" | "srv6"
```

### SLA Thresholds
```bash
SLA_PLATINUM_LATENCY_MS=30
SLA_GOLD_LATENCY_MS=60
```

---

## 9. Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Trigger | SLA degradation, not link failure | Optical reroutes may heal the physical layer but leave SLA degraded |
| Topology source | CNC live topology (COE IETF Network APIs) | KG can be stale during optical reroutes |
| Tunnel type | RSVP-TE default, SR-MPLS/SRv6 auto-detected | Most enterprise PEs today still run RSVP-TE |
| Provisioning mode | NSO/PCC default | NSO path is more debuggable (config visible on router); PCE for dynamic low-latency TE |
| SR steering | ODN / BGP color automatic | No per-VRF API calls needed |
| RSVP steering | Explicit VRF next-hop update via NSO | RSVP-TE does not have automatic ODN |
| Recovery trigger | SLA + zero impacted services | Avoids premature cutover while services still show impact |
| Hold timer | Configurable per tier (default 5 min) | Prevents oscillation when path is borderline |
| Agent comms | A2A protocol (HTTP) | Each agent is a separate container; no shared memory |
| State store | Redis + PostgreSQL | Redis for speed, PostgreSQL for durability across restarts |
| Scope | Platinum + Gold only | Silver/Bronze: too many services, alert-only is sufficient |
