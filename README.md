# Customer Experience Management — AI Multi-Agent System

Automated SLA protection for L3VPN/L2VPN services on Cisco IOS XR networks using LangGraph-based multi-agent AI.

**Last updated:** 2026-03-06 (aligned with CNC Supports call recording 2026-03-05)

---

## What This System Does

When a network link degrades (high latency, packet loss, jitter) — but is still **up** — customers on that link suffer SLA violations without any automatic response.

This system detects the degradation, identifies which premium customers are affected, computes an alternate path, provisions a protection tunnel, steers traffic, and restores when SLA recovers — all autonomously, within seconds.

```
Link degrades (but stays UP)
        │
        ▼
PCA probe detects SLA violation
DPM TCA detects interface errors      ◄── New: CNC SSE + DPM Kafka event streams
CNC SSE notification fires
        │
        ▼
Event Correlator: deduplicate, flap-filter, map to link
        │
        ▼
Orchestrator: assess → diagnose → provision → monitor → restore
        │
        ▼
Customer SLA protected automatically
```

---

## Network Technology Support

The system supports **both current and future TE technologies** across all accounts:

| Technology | Status | Accounts |
|------------|--------|----------|
| **RSVP-TE** | ✅ Fully supported | Jio/Geo (pure MPLS today) |
| **SR-MPLS** | ✅ Fully supported | Accounts already on SR |
| **SRv6** | ✅ Fully supported | Future / proactive phase |

The system **auto-detects** which technology is in use per account/device and applies the correct provisioning path. The default is configurable via `DEFAULT_TE_TYPE` env var (defaults to `rsvp-te`).

---

## Agent Architecture (10 Agents)

```
                    ┌─────────────────────────────────────┐
                    │           IO AGENT (8009)           │
                    │     Human UI — Ticket Dashboard     │
                    └──────────────┬──────────────────────┘
                                   │ A2A
                    ┌──────────────▼──────────────────────┐
                    │        ORCHESTRATOR (8000)          │
                    │   Supervisor · State Machine · LLM  │
                    └──┬──┬──┬──┬──┬──┬──┬──┬────────────┘
                       │  │  │  │  │  │  │  │
        ┌──────────────┘  │  │  │  │  │  │  └─────────────────┐
        ▼                 ▼  │  ▼  │  ▼  ▼                   ▼
  ┌──────────┐    ┌────────┐ │ ┌────────┐ ┌────────┐   ┌──────────┐
  │  Event   │    │Service │ │ │Tunnel  │ │Restore │   │  Audit   │
  │Correlator│    │Impact  │ │ │Provison│ │Monitor │   │  (8008)  │
  │  (8001)  │    │ (8002) │ │ │ (8004) │ │ (8005) │   └──────────┘
  └──────────┘    └────────┘ │ └────────┘ └────────┘
                             │
              ┌──────────────┼──────────────────┐
              ▼              ▼                  ▼
        ┌──────────┐  ┌────────────┐    ┌──────────────┐
        │  Path    │  │  Traffic   │    │  Notification│
        │Computation│ │ Analytics  │    │    (8007)    │
        │  (8003)  │  │  (8006)   │    └──────────────┘
        └──────────┘  └────────────┘
```

| Port | Agent | Role |
|------|-------|------|
| 8000 | Orchestrator | Workflow supervisor, incident state machine |
| 8001 | Event Correlator | Alert ingestion, dedup, flap detection, link mapping |
| 8002 | Service Impact | CNC Service Health — affected VPN services |
| 8003 | Path Computation | Knowledge Graph + CNC Topology — alternate routes |
| 8004 | Tunnel Provisioning | NSO/PCE — RSVP-TE/SR-MPLS/SRv6 tunnel lifecycle |
| 8005 | Restoration Monitor | PCA SLA recovery, hold timers, cutover |
| 8006 | Traffic Analytics | SRv6 demand matrix, proactive congestion prediction |
| 8007 | Notification | Webex, ServiceNow, Email by severity |
| 8008 | Audit | Compliance logging, reports |
| 8009 | IO Agent | Human ticket dashboard, real-time updates |

---

## End-to-End Workflow

### Phase 1 — Event Ingestion (NEW)

**What happens:** CNC Notification Event Stream sends SSE alerts when service health degrades. DPM (Device Performance Monitoring) streams interface TCA events via Kafka.

```
CNC SSE ──► cnc_notification_subscriber.py ──► Event Correlator A2A
DPM Kafka ──► dpm_client.py (TCA filter) ──► Event Correlator A2A
PCA Probe alert ──► ingest_node ──► normalize
```

- CNC SSE reconnects automatically on disconnect
- DPM filters on `packet_loss_pct` and `error_rate` TCA events
- All alerts normalized to: `{link_id, pe_source, pe_destination, severity, timestamp}`
- PCA session IPs resolved to CNC link_id via `pca_session_mapper.py` (5-min cache)

**Key files:**
- `agents/event_correlator/tools/cnc_notification_subscriber.py` — SSE subscriber
- `agents/event_correlator/tools/dpm_client.py` — DPM Kafka + REST fallback
- `agents/event_correlator/tools/pca_session_mapper.py` — IP → link_id resolution
- `agents/event_correlator/nodes/ingest_node.py` — normalization

---

### Phase 2 — Orchestrator: Assess Premium Impact

**What happens:** Orchestrator receives alert, queries CNC Service Health for all affected VPN services, then filters to **premium tiers only** (platinum + gold) before triggering remediation.

```
Alert received
     │
     ▼
assess_node ──► CNC Service Health API ──► affected_services[]
     │
     ▼
Filter: platinum + gold tiers only
     │
     ├── No premium services? ──► Log, notify, close (no automated action)
     └── Premium services found? ──► Continue to Phase 3
```

- **Platinum SLA:** 30ms latency threshold
- **Gold SLA:** 60ms latency threshold
- Tier filter prevents automation for non-premium customers (silver, bronze)
- Configured accounts: HDFC, SBI, ICICI (platinum); others per tier config

**Key files:**
- `agents/orchestrator/nodes/assess_node.py`
- `agents/restoration_monitor/tools/pca_client.py` — SLA thresholds

---

### Phase 3 — Orchestrator: Hop-by-Hop Diagnosis (NEW)

**What happens:** Before requesting a full alternate path, the orchestrator pinpoints exactly which P-to-P underlay hop is causing the degradation using live IGP topology from CNC.

```
diagnose_node ──► CNCTopologyClient.get_igp_path(pe_a, pe_b)
                        │
                        ▼
              Enumerate P-to-P hops between the PEs
                        │
                        ▼
              Check DPM counters per hop
                        │
                        ▼
              candidate_links[] ──► Path Computation Agent
```

- Uses **CNC Topology API** (live IGP topology) — not the internal Knowledge Graph which can be stale during optical reroutes
- If link already identified (from CNC SSE alert), diagnosis is skipped
- Stores `candidate_links` in state for path computation

**Key files:**
- `agents/orchestrator/nodes/diagnose_node.py`
- `agents/path_computation/tools/cnc_topology_client.py`

**Orchestrator node sequence:**
```
start → detect → dampen → assess → diagnose → compute → provision → steer → monitor → restore → close
                                     ▲ NEW
```

---

### Phase 4 — Path Computation

**What happens:** Path Computation Agent queries the Knowledge Graph (350K device topology) for an alternate path that avoids the degraded links.

```
Path Computation Agent ──► Knowledge Graph (Dijkstra API)
                                │
                                ├── RSVP-TE: returns explicit IP hops []
                                └── SR-MPLS: returns SID list []
```

- `DEFAULT_TE_TYPE` env var controls path format (`rsvp-te` or `sr-mpls`)
- RSVP-TE paths return plain IP addresses (no SIDs)
- SR-MPLS paths return node SIDs for segment list
- Falls back to CNC Topology API if KG returns stale data

**Key files:**
- `agents/path_computation/tools/kg_client.py`
- `agents/path_computation/tools/cnc_topology_client.py`
- `agents/path_computation/tools/srpm_client.py` — SR Performance Monitoring (SR phase)

---

### Phase 5 — Tunnel Provisioning

**What happens:** Tunnel Provisioning Agent creates a protection tunnel using the correct method for the TE technology in use.

#### RSVP-TE Provisioning (Today — Jio/Geo and MPLS accounts)

```
Tunnel Provisioning Agent
     │
     ▼
create_rsvp_tunnel()
     │
     ├── TUNNEL_PROVISIONING_MODE=nso (default)
     │        │
     │        ▼
     │   NSO RPC endpoint: POST /api/operations/mpls-te:create-tunnel
     │   Body: {head-end, tail-end, bandwidth, explicit-path: [{hop, strict}]}
     │        │
     │        ▼
     │   Async: poll job-id every 3s (up to 30s) for NSO queue completion
     │
     └── TUNNEL_PROVISIONING_MODE=pce (optional, requires HTTP on PCE)
              │
              ▼
         PCE REST API: POST /pce/tunnels (blocked in most environments)
```

> **Why NSO, not PCE?** PCE requires HTTP access on the PCE node, which is blocked by security policy in most deployments. NSO is the recommended approach per Krishnan (2026-03-05 call).

#### SR-MPLS / SRv6 Provisioning

```
create_sr_policy() ──► CNC PCE API: POST /pce/sr-policies
                        Body: {head-end, tail-end, segment-list: [SIDs]}
```

#### RSVP-TE Delete (Fixed)

```
delete_tunnel(tunnel_type="rsvp-te")
     │
     ▼
NSO DELETE: /api/running/mpls-te/tunnels/{tunnel-name}   ← correct endpoint
(NOT SR policy delete — that was the bug)
```

#### Hop Format (Fixed)

| TE Type | Hop Format |
|---------|-----------|
| RSVP-TE | `{"address": "10.0.0.1", "hop-type": "strict", "index": 1}` |
| SR-MPLS | `{"hop": {"node-ipv4-address": "10.0.0.1"}, "step": 1}` |

**Key files:**
- `agents/tunnel_provisioning/tools/cnc_tunnel.py`
- `agents/tunnel_provisioning/nodes/create_node.py`
- `agents/tunnel_provisioning/tools/te_detector.py`
- `agents/tunnel_provisioning/nodes/build_node.py`

---

### Phase 6 — Traffic Steering

**What happens:** After tunnel is created, traffic is steered from the degraded path to the protection tunnel.

#### SR-MPLS / SRv6 Steering

ODN (On-Demand Next-hop) auto-steers via colour-community — no explicit VRF manipulation needed.

#### RSVP-TE Steering (Fixed — was a no-op)

```
steer_node ──► NSO REST API
     │
     ▼
POST /api/running/devices/device/{head-end}/config/vrf-steering
Body: {
  "vrf": "{vrf_name}",
  "next-hop": "{tunnel_endpoint_ip}",
  "tunnel-id": "{tunnel_id}"
}
```

- Requires `affected_vrfs` and `tunnel_endpoint_ip` in orchestrator state
- Returns `steer_error` if VRF params missing (non-blocking — logs warning)

**Key files:**
- `agents/tunnel_provisioning/nodes/steer_node.py`

---

### Phase 7 — Restoration Monitoring

**What happens:** Restoration Monitor polls PCA to detect SLA recovery on the original path. When stable, traffic is cut back over.

```
Restoration Monitor
     │
     ▼
Poll PCA every {poll_interval} seconds
     │
     ├── Degraded? Continue protecting
     │
     ├── Recovered? Start hold timer ({hold_time} seconds)
     │        │
     │        └── Still stable after hold? ──► Phase 8
     │
     └── SLA thresholds:
              Platinum: 30ms
              Gold:     60ms
              Silver:   100ms
              Bronze:   150ms
```

**Key files:**
- `agents/restoration_monitor/tools/pca_client.py`

---

### Phase 8 — Traffic Restoration + Cleanup

**What happens:** Traffic is restored to the original path, protection tunnel is deleted, incident closed.

```
Restore: Immediate OR Gradual
  Immediate: 100% back to original path
  Gradual:   75/25 → 50/50 → 25/75 → 0/100 (weighted ECMP)
     │
     ▼
Delete protection tunnel (RSVP-TE: NSO DELETE / SR: CNC PCE delete)
     │
     ▼
Close incident → Notify → Audit log
```

---

### Escalation (NEW)

If automation fails at any point, the system escalates to the right team automatically:

| Failure Type | Escalation |
|--------------|-----------|
| No alternate path found | Webex → Optical team room + Email thread |
| Tunnel provisioning failed | Webex → CNC product team room |
| Traffic steering failed | Webex → CNC product team room |

**Key files:**
- `agents/orchestrator/nodes/escalate_node.py`

---

## CNC API Integrations

| API | Purpose | Auth |
|-----|---------|------|
| CNC SSE Notification Stream | Real-time service health alerts | JWT (TGT→JWT) |
| CNC Service Health API | Affected VPN services per link | JWT (TGT→JWT) |
| CNC Topology API | Live IGP topology, P-to-P hops | JWT (TGT→JWT) |
| NSO REST API | RSVP-TE tunnel create/delete, VRF steering | Basic/Token |
| PCA REST API | SLA probe data, session mapping | API Key |
| DPM Kafka | Interface TCA events (packet loss, errors) | SASL |
| SRPM REST API | SR per-link metrics (SR phase) | JWT |

All CNC clients use the same JWT authentication pattern:
```
1. POST /crosswork/sso/v1/tickets  →  TGT
2. POST /crosswork/sso/v2/tickets/jwt  →  JWT (8h TTL, refresh 5min before expiry)
3. Use JWT in Authorization: Bearer header
```

---

## Environment Variables

### CNC Connectivity
```bash
CNC_URL=https://cnc.example.com:30603
CNC_USERNAME=admin
CNC_PASSWORD=<secret>
CNC_AUTH_URL=https://cnc.example.com:30603/crosswork/sso/v1/tickets
CNC_JWT_URL=https://cnc.example.com:30603/crosswork/sso/v2/tickets/jwt
CNC_SERVICE_HEALTH_URL=https://cnc.example.com:30603/crosswork/nbi/servicehealth/v1
CNC_TOPOLOGY_URL=https://cnc.example.com:30603/crosswork/nbi/topology/v1
CNC_NOTIFICATION_URL=https://cnc.example.com:30603/crosswork/nbi/servicehealth/v1/notification-stream
CA_CERT_PATH=/path/to/ca.crt
```

### NSO Connectivity
```bash
CNC_NSO_URL=https://nso.example.com:8443
NSO_USERNAME=admin
NSO_PASSWORD=<secret>
```

### TE Technology
```bash
DEFAULT_TE_TYPE=rsvp-te          # rsvp-te | sr-mpls | srv6
TUNNEL_PROVISIONING_MODE=nso     # nso (default) | pce
NSO_PROVISIONING_MODE=async      # async (default) | sync
```

### SR Phase (Future)
```bash
SRPM_ENABLED=false               # true when SR deployed
SRPM_URL=https://srpm.example.com
```

### DPM / Kafka
```bash
DPM_KAFKA_BROKERS=kafka:9092
DPM_KAFKA_TOPIC=dpm-tca-alerts
DPM_KAFKA_GROUP_ID=cem-event-correlator
DPM_REST_URL=https://cnc.example.com:30603/crosswork/dpm/v1
```

### Escalation Channels
```bash
OPTICAL_TEAM_WEBEX_ROOM=<room-id>
OPTICAL_TEAM_EMAIL=optical-oncall@example.com
CNC_TEAM_WEBEX_ROOM=<room-id>
WEBEX_BOT_TOKEN=<token>
```

### SLA Tiers
```bash
PREMIUM_SLA_ACCOUNTS=HDFC,SBI,ICICI   # Comma-separated platinum accounts
```

---

## Changes Made (2026-03-05 — Based on CNC Supports Call)

The following 14 gaps were identified from the Krishnan Thirukonda support call and fixed in code. See `callrecording_vs_code_gap.md` for full details.

### Critical Fixes
| Gap | Fix |
|-----|-----|
| No event ingestion | Added `CNCNotificationSubscriber` (SSE) + `DPMKafkaConsumer` wired into startup |
| RSVP-TE steer was no-op | Implemented VRF next-hop steering via NSO REST API |
| PCE-initiated tunnels | Switched to NSO-initiated RSVP-TE (PCE HTTP blocked by security) |

### High Priority Fixes
| Gap | Fix |
|-----|-----|
| Wrong RSVP-TE delete endpoint | Fixed to use NSO `/mpls-te/tunnels/{name}` not SR policy delete |
| No hop-by-hop diagnosis | Added `diagnose_node` + `CNCTopologyClient` using live IGP topology |
| DPM TCA unused | Added `DPMKafkaConsumer` + `DPMRestClient` for interface counter TCA events |
| 4 dual-mode TE bugs | Fixed: default type, capabilities passing, hop format, path simulation |
| CNC Topology API unused | Added `CNCTopologyClient` for real-time IGP data (replacing stale KG) |

### Medium Priority Fixes
| Gap | Fix |
|-----|-----|
| PCA session mapping missing | Added `PCASessionMapper` to resolve session IPs → CNC link_id |
| No premium tier filtering | Added platinum/gold filter in `assess_node` before triggering remediation |
| Wrong SLA thresholds | Fixed to 30ms (platinum) / 60ms (gold) per Jio/Geo agreement |
| No SRPM integration | Added `SRPMClient` stub (activated by `SRPM_ENABLED=true` for SR phase) |
| NSO async not handled | Added job-id polling (3s interval, 30s max) for NSO queue congestion |

### Low Priority Fixes
| Gap | Fix |
|-----|-----|
| Escalation not wired | Added Webex + Email escalation by failure type in `escalate_node` |

---

## RSVP-TE vs SR-MPLS — How Dual-Mode Works

```
Device capabilities check
     │
     ├── Capabilities available in state?
     │        YES ──► Use reported capability
     │        NO  ──► Use DEFAULT_TE_TYPE env var (default: rsvp-te)
     │
     ▼
TE type detected
     │
     ├── rsvp-te ──► NSO RPC tunnel creation
     │              Explicit hops: [{address, hop-type: strict, index}]
     │              VRF steering via NSO
     │              Delete: NSO DELETE /mpls-te/tunnels/{name}
     │
     └── sr-mpls / srv6 ──► CNC PCE SR policy creation
                            Segment list: [{node-ipv4-address, SID}]
                            ODN auto-steering (no explicit VRF config)
                            Delete: CNC PCE SR policy delete
```

SR-MPLS phase is expected for Jio/Geo in September/October 2026. The code already handles it — only `SRPM_ENABLED` and `DEFAULT_TE_TYPE` need to change at that time.

---

## Project Structure

```
agents/
├── orchestrator/              # Workflow supervisor (port 8000)
│   ├── nodes/
│   │   ├── start_node.py
│   │   ├── detect_node.py
│   │   ├── dampen_node.py
│   │   ├── assess_node.py        ← premium tier filter (updated)
│   │   ├── diagnose_node.py      ← NEW: hop-by-hop diagnosis
│   │   ├── compute_node.py
│   │   ├── provision_node.py
│   │   ├── steer_node.py
│   │   ├── monitor_node.py
│   │   ├── restore_node.py
│   │   ├── close_node.py
│   │   └── escalate_node.py      ← Webex+Email escalation (updated)
│   └── workflow.py               ← diagnose node wired in (updated)
│
├── event_correlator/          # Alert ingestion (port 8001)
│   ├── tools/
│   │   ├── cnc_notification_subscriber.py   ← NEW: CNC SSE subscriber
│   │   ├── dpm_client.py                    ← NEW: DPM Kafka + REST
│   │   ├── pca_session_mapper.py            ← NEW: IP → link_id mapping
│   │   ├── correlator.py
│   │   ├── dedup_checker.py
│   │   └── flap_detector.py
│   ├── nodes/
│   │   └── ingest_node.py        ← pe_source_ip/dest_ip fields (updated)
│   └── main.py                   ← SSE subscriber wired to startup (updated)
│
├── service_impact/            # CNC Service Health (port 8002)
│   └── tools/cnc_client.py
│
├── path_computation/          # Alternate route (port 8003)
│   └── tools/
│       ├── kg_client.py              ← dual-mode path simulation (updated)
│       ├── cnc_topology_client.py    ← NEW: live IGP topology
│       └── srpm_client.py            ← NEW: SR Performance Monitoring
│
├── tunnel_provisioning/       # Tunnel lifecycle (port 8004)
│   ├── tools/
│   │   ├── cnc_tunnel.py     ← NSO mode, async polling, correct delete (updated)
│   │   └── te_detector.py    ← default rsvp-te (updated)
│   ├── nodes/
│   │   ├── detect_node.py    ← capabilities passed to detector (updated)
│   │   ├── build_node.py     ← correct RSVP-TE hop format (updated)
│   │   ├── create_node.py    ← NSO async job polling (updated)
│   │   └── steer_node.py     ← RSVP-TE VRF steering implemented (updated)
│   └── schemas/state.py      ← steer_error, affected_vrfs fields (updated)
│
├── restoration_monitor/       # SLA recovery (port 8005)
│   └── tools/pca_client.py   ← 30ms/60ms thresholds (updated)
│
├── traffic_analytics/         # Proactive TE (port 8006)
├── notification/              # Webex/Email/ServiceNow (port 8007)
├── audit/                     # Compliance logging (port 8008)
└── io_agent/                  # Human ticket UI (port 8009)
```

---

## Running the System

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your CNC, NSO, Kafka, Webex credentials

# Start all agents
docker-compose up -d

# Check health
curl http://localhost:8000/health   # Orchestrator
curl http://localhost:8001/health   # Event Correlator
```

The Event Correlator automatically starts the CNC SSE subscriber on startup. Once connected, the system is fully autonomous.

---

## Documentation

| File | Purpose |
|------|---------|
| `DESIGN.md` | Original system design and agent architecture |
| `WORKFLOW.md` | Ticket lifecycle and IO Agent integration |
| `callrecording_vs_code_gap.md` | 14 gaps found + fixed from 2026-03-05 call |
| `recording.md` | Full transcript of CNC Supports call (2026-03-05) |
| `architecture_and_design.md` | High-level architecture overview |
