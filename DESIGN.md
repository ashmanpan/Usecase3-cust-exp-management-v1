# Multi-Agent Customer Experience Management System Design

## Project Overview
LangGraph-based multi-agent system for automated traffic protection that:
1. Detects SLA degradation (NOT link failure) via PCA + CNC alarms
2. Identifies affected L3VPN/L2VPN services via CNC Service Health
3. Computes alternate paths using Knowledge Graph (BGP-LS + Dijkstra API)
4. Provisions shared protection tunnels (RSVP-TE/SR-MPLS/SRv6) via CNC PCE
5. Monitors and restores normal forwarding when SLA recovers
6. Uses A2A protocol for microservice agent communication

---

## Confirmed Requirements Summary

| Requirement | Decision |
|-------------|----------|
| Trigger Sources | PCA + CNC Alarms |
| TE Handling | Auto-detect and match existing service technology |
| Knowledge Graph | Exists with Dijkstra API (link/node avoidance) |
| Deployment | Microservices (each agent = separate container) |
| Agent Communication | A2A Protocol (HTTP/gRPC native) |
| State Store | Redis (primary) + PostgreSQL (durability) |
| LLM Provider | Multi-provider (Claude, GPT, local models) |
| Scale | 50-500 concurrent affected services |
| Tunnel Strategy | Shared tunnel per affected path (Phase 1) |
| Restoration | Configurable: Immediate OR Gradual cutover |
| Hold Timer | Configurable per service tier |
| Notifications | Multiple channels (Webex, ServiceNow, Email) by severity |

---

## Agent Architecture (9 Agents)

```
                         ┌─────────────────────┐
                         │   ORCHESTRATOR      │
                         │   (Supervisor)      │
                         │  Hybrid: Rules+LLM  │
                         └─────────┬───────────┘
                                   │
  ┌──────────┬──────────┬──────────┼──────────┬──────────┬──────────┬──────────┐
  ▼          ▼          ▼          ▼          ▼          ▼          ▼          ▼
┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐
│ Event  ││Service ││  Path  ││ Tunnel ││Restore ││Traffic ││ Notify ││ Audit  │
│Correlate││Impact ││Compute ││Provision││Monitor ││Analytics││        ││        │
└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘
```

| # | Agent | Container | Port | Responsibility |
|---|-------|-----------|------|----------------|
| 1 | Orchestrator | orchestrator:v1 | 8000 | Supervisor, state machine, LLM for edge cases |
| 2 | Event Correlator | event-correlator:v1 | 8001 | PCA/CNC alert correlation, dedup, flap detection |
| 3 | Service Impact | service-impact:v1 | 8002 | Query CNC Service Health for affected VPN services |
| 4 | Path Computation | path-computation:v1 | 8003 | Query KG for alternate paths with constraints |
| 5 | Tunnel Provisioning | tunnel-provisioning:v1 | 8004 | Create tunnels via MCP→CNC, auto-detect TE type |
| 6 | Restoration Monitor | restoration-monitor:v1 | 8005 | Monitor SLA recovery, manage hold timers, cutover |
| 7 | **Traffic Analytics** | traffic-analytics:v1 | 8006 | **SRv6 demand matrix, congestion prediction, proactive TE** |
| 8 | Notification | notification:v1 | 8007 | Webex, ServiceNow, Email alerts |
| 9 | Audit | audit:v1 | 8008 | Compliance logging, reports |

---

## Traffic Analytics Agent (SRv6 Demand Matrix)

### Purpose
Enable **proactive traffic engineering** by analyzing SRv6 traffic demands and predicting congestion BEFORE SLA degradation occurs.

### Traffic Demand Matrix
```
        ┌──────────────────────────────────────────────────────┐
        │           DESTINATION                                 │
        │     PE1      PE2      PE3      PE4      PE5          │
   ┌────┼──────────────────────────────────────────────────────┤
   │PE1 │    -       10Gbps   5Gbps    2Gbps    8Gbps         │
S  │PE2 │  8Gbps       -      12Gbps   3Gbps    1Gbps         │
R  │PE3 │  4Gbps     7Gbps      -      6Gbps    9Gbps         │
C  │PE4 │  2Gbps     3Gbps    4Gbps      -      5Gbps         │
   │PE5 │  6Gbps     2Gbps    8Gbps    4Gbps      -           │
   └────┴──────────────────────────────────────────────────────┘
```

### Why SRv6 Enables This
| Feature | Benefit |
|---------|---------|
| IPv6 Flow Label | 20-bit field for flow identification |
| SRv6 SID | Encodes destination, function, and arguments |
| uSID (micro-SID) | Compact encoding allows more telemetry |
| In-situ OAM (IOAM) | Embed telemetry directly in packet headers |
| Alternate Marking | Precise traffic measurement per flow |

### Data Sources
| Source | Data Type | Purpose |
|--------|-----------|---------|
| SR-PM (Performance Measurement) | Delay, loss, jitter | Per-path SLA metrics |
| MDT Telemetry (CDG) | Interface counters | Utilization per link |
| NetFlow/IPFIX | Flow records with SRv6 SID | Traffic volume per flow |
| IOAM (In-situ OAM) | Hop-by-hop telemetry | Path-level visibility |
| CNC TE Dashboard | Traffic statistics | Tunnel utilization |

### Capabilities
1. **Build Demand Matrix**: Compute end-to-end traffic volumes between all PE pairs
2. **Predict Congestion**: Identify links approaching capacity threshold
3. **Proactive Alerting**: Trigger protection BEFORE SLA degrades
4. **Traffic Optimization**: Recommend load balancing across paths
5. **What-If Analysis**: Simulate impact of link failure on traffic distribution

### Two Operating Modes

**Mode 1: Reactive (Existing Flow)**
```
PCA Alert → SLA Already Degraded → Find Alternate → Provision Tunnel
```

**Mode 2: Proactive (Enhanced with Traffic Matrix)**
```
Traffic Matrix → Predict Congestion → Pre-provision Tunnel → Shift Traffic BEFORE SLA degrades
```

### Proactive Workflow (Phase 0 - NEW)
```
Phase 0: Proactive Detection (Traffic Analytics Agent)

1. Continuously monitor:
   - Link utilization (from KG/Telemetry)
   - Traffic demand trends
   - SRv6 flow volumes

2. When utilization > threshold (e.g., 70%):
   - Calculate risk of SLA violation
   - Identify services on congested path
   - Send PROACTIVE_ALERT to Orchestrator

3. Orchestrator initiates protection workflow:
   - Same as reactive, but BEFORE actual degradation
   - Customer experience preserved proactively
```

### Traffic Matrix by TE Technology (TOMORROW'S DISCUSSION)

| Technology | Traffic Visibility Method | Challenges |
|------------|--------------------------|------------|
| **SRv6** | Native IPv6 flow labels, IOAM, uSID telemetry | Best visibility - native support |
| **SR-MPLS** | ? | Need to discuss data sources |
| **RSVP-TE** | ? | Need to discuss data sources |

**Key Questions for Tomorrow:**
1. How do we build demand matrix for SR-MPLS without IPv6 features?
2. What telemetry is available for RSVP-TE tunnels?
3. Can we use MPLS FRR counters or tunnel bandwidth reservations?
4. Are there CNC/PCA APIs that provide per-tunnel traffic stats?
5. Can Knowledge Graph provide utilization data across all TE types?

---

## Workflow (7 Phases)

### Phase 1: SLA Degradation Detection
```
PCA Alert ─┐
           ├──► Event Correlator ──► Orchestrator
CNC Alarm ─┘    (dedup, correlate)   (start incident)
```
- PCA detects: latency/jitter/packet loss exceeds threshold
- Link is UP but underperforming (NOT a failure)
- Flap detection: exponential backoff (suppress rapid oscillations)

### Phase 2: Service Impact Assessment
```
Orchestrator ──► Service Impact Agent ──► CNC Service Health API
                                              │
                                              ▼
                                    affected_services[]
                                    (L3VPN, L2VPN, endpoints, SLA tier)
```

### Phase 3: Alternate Path Computation
```
Orchestrator ──► Path Computation Agent ──► Knowledge Graph API
                                               │
                                               ▼
                                    alternate_path (avoiding degraded links)
                                    Constraints: link avoidance, node avoidance
```

### Phase 4: Protection Tunnel Creation
```
Orchestrator ──► Tunnel Provisioning Agent ──► MCP Server ──► CNC PCE
                                                    │
                                                    ▼
                                         Protection tunnel created
                                         (RSVP-TE / SR-MPLS / SRv6)
```
- ONE shared tunnel per affected path
- Auto-detect TE type from existing service configuration
- Retry with exponential backoff on failure

### Phase 5: Traffic Steering
```
Tunnel Provisioning Agent ──► Steer traffic to protection tunnel
                              (original path still exists)
```

### Phase 6: Continuous Monitoring
```
Restoration Monitor Agent ──► Poll PCA for SLA recovery
                              │
                              ├── SLA normal? Start hold timer
                              ├── Hold time elapsed? Verify stability
                              └── Stable? Trigger Phase 7
```

### Phase 7: Restoration
```
1. Cutover traffic (configurable):
   - Immediate: All traffic back to original path
   - Gradual:   75/25 → 50/50 → 25/75 → 0/100 (weighted ECMP)

2. Verify SLA on original path
3. Remove protection tunnel
4. Close incident, notify, audit
```

---

## Redis State Schema

```
incident:{id}                    # Hash: status, degraded_links, severity, timestamps
incident:{id}:services           # Set: affected service IDs
tunnel:{id}                      # Hash: incident_id, te_type, path, status
restoration:timers               # Sorted Set: score=recovery_time, member=incident_id
link:{id}:incidents              # Set: incident IDs affecting this link
service:{id}:protection          # Hash: tunnel_id, original_path
```

PostgreSQL: Write-through for durability (same schema, for disaster recovery)

---

## Edge Case Handling

| Scenario | Handling |
|----------|----------|
| Cascading failure (protection path also degrades) | Re-compute path avoiding both, escalate if no options |
| No alternate path available | Escalate to operator, optionally apply QoS |
| Tunnel provisioning failure | Retry 3x with backoff, try alternate path, escalate |
| Flapping link (rapid oscillation) | Exponential backoff damping, suppress actions |

---

## A2A Communication

Each agent exposes:
- `GET /.well-known/agent.json` - Agent Card (capabilities)
- `POST /tasks` - A2A task endpoint
- `GET /health`, `/ready`, `/live` - Health probes
- `GET /metrics` - Prometheus metrics

Agent discovery: **[PLACEHOLDER]** - User has existing registry (API/code TBD)

---

## Project Structure

```
customer-experience-management/
├── pyproject.toml
├── docker-compose.yml
├── kubernetes/
│   ├── deployments/          # 8 deployment manifests
│   └── services/             # 8 service manifests
│
├── src/
│   ├── common/
│   │   ├── config.py
│   │   ├── redis_client.py
│   │   ├── postgres_client.py
│   │   ├── llm_providers.py   # Multi-LLM abstraction
│   │   ├── a2a_base.py        # A2A agent base class
│   │   ├── health.py          # Health endpoints
│   │   └── registry.py        # [PLACEHOLDER] Service registry
│   │
│   ├── agents/
│   │   ├── orchestrator/
│   │   │   ├── agent.py
│   │   │   ├── state_machine.py
│   │   │   └── agent_card.json
│   │   ├── event_correlator/
│   │   │   ├── agent.py
│   │   │   ├── correlation_rules.py
│   │   │   └── flap_detection.py
│   │   ├── service_impact/
│   │   │   ├── agent.py
│   │   │   └── cnc_service_health.py
│   │   ├── path_computation/
│   │   │   ├── agent.py
│   │   │   └── knowledge_graph.py
│   │   ├── tunnel_provisioning/
│   │   │   ├── agent.py
│   │   │   ├── te_detector.py
│   │   │   └── mcp_client.py
│   │   ├── restoration_monitor/
│   │   │   ├── agent.py
│   │   │   ├── sla_monitor.py
│   │   │   ├── hold_timer.py
│   │   │   └── gradual_cutover.py
│   │   ├── traffic_analytics/        # NEW - SRv6 Demand Matrix
│   │   │   ├── agent.py
│   │   │   ├── demand_matrix.py      # Build PE-to-PE traffic matrix
│   │   │   ├── congestion_predictor.py
│   │   │   ├── telemetry_collector.py # SR-PM, MDT, NetFlow
│   │   │   └── agent_card.json
│   │   ├── notification/
│   │   │   ├── agent.py
│   │   │   └── channels/ (webex.py, servicenow.py, email.py)
│   │   └── audit/
│   │       ├── agent.py
│   │       └── event_logger.py
│   │
│   ├── models/               # Pydantic models
│   │   ├── incident.py
│   │   ├── service.py
│   │   ├── tunnel.py
│   │   └── alert.py
│   │
│   └── api/
│       ├── pca_webhook.py    # PCA alert webhook
│       └── cnc_webhook.py    # CNC alarm webhook
│
├── tests/
└── config/
    ├── default.yaml
    └── production.yaml
```

---

## Deployment (Kubernetes)

- 8 separate containers (1 per agent)
- Each agent: 2 replicas for HA (except Orchestrator: 1 replica)
- ClusterIP services for inter-agent A2A communication
- Ingress for webhook endpoints
- Dependencies: Redis (managed), PostgreSQL (managed), Service Registry (existing)

---

## Open Items / Placeholders

1. **Service Registry API** - User to provide API spec and integration code
2. **PCA Link ID Format** - Confirm if topology IDs or interface names
3. **MCP Server Details** - Confirm existing tool definitions for CNC operations
4. **Knowledge Graph API** - Confirm exact endpoint URLs and auth

---

## CNC Integration Details (from Reference Docs)

### CNC 7.1 SR-PCE Architecture

The SR-PCE in CNC 7.1 provides centralized traffic engineering for SR-MPLS, SRv6, and RSVP-TE:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CNC 7.1 Controller                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Northbound  │  │   SR-PCE    │  │  Traffic Engineering   │ │
│  │  REST API   │──│  (IOS-XR)   │──│    Visualization       │ │
│  │  (RESTCONF) │  │             │  │                         │ │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────────┘ │
│         │                │                                      │
│         │ JWT Auth       │ BGP-LS (Topology)                   │
│         │                │ PCEP (Path Setup)                   │
└─────────┼────────────────┼──────────────────────────────────────┘
          │                │
          ▼                ▼
    ┌──────────┐    ┌──────────────────────────────────────┐
    │ External │    │           Network Devices             │
    │  OSS/BSS │    │  (PE/P routers as PCCs)              │
    └──────────┘    └──────────────────────────────────────┘
```

### JWT Authentication for CNC APIs

All CNC northbound API calls require JWT Bearer token authentication:

```python
# Step 1: Get Ticket-Granting Ticket (TGT)
POST https://{cnc_host}:30603/crosswork/sso/v1/tickets
Content-Type: application/x-www-form-urlencoded
Body: username={user}&password={pass}
Response: TGT-34-dDGV8oqlqLdD... (plain text ticket)

# Step 2: Exchange TGT for JWT
POST https://{cnc_host}:30603/crosswork/sso/v2/tickets/jwt
Content-Type: application/x-www-form-urlencoded
Body: tgt={TGT}&service=https://{cnc_host}:30603/app-dashboard
Response: eyJhbGciOiJIUzUxMiIs... (JWT token, valid 8 hours)

# Step 3: Use JWT in API calls
Authorization: Bearer {JWT_token}
Content-Type: application/yang-data+json
```

### CNC Tunnel Provisioning APIs

| Operation | Endpoint | Method |
|-----------|----------|--------|
| Create RSVP-TE Tunnel | `/crosswork/nbi/optimization/v3/restconf/operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:rsvp-te-tunnel-create` | POST |
| Create SR Policy | `/crosswork/nbi/optimization/v3/restconf/operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-create` | POST |
| Delete RSVP-TE Tunnel | `/crosswork/nbi/optimization/v3/restconf/operations/cisco-crosswork-optimization-engine-rsvp-te-tunnel-operations:rsvp-te-tunnel-delete` | POST |
| Delete SR Policy | `/crosswork/nbi/optimization/v3/restconf/operations/cisco-crosswork-optimization-engine-sr-policy-operations:sr-policy-delete` | POST |

### SR Policy Create Payload Schema

```json
{
  "input": {
    "sr-policies": [{
      "head-end": "192.0.2.1",           // Required: Source PE IP
      "end-point": "192.0.2.8",          // Required: Destination PE IP
      "color": 100,                       // Required: Policy color/ID
      "path-name": "LowLatency",          // Optional: Candidate path name
      "binding-sid": 24000,               // Optional: BSID (MPLS label)
      "description": "Low-latency path",
      "sr-policy-path": {
        // DYNAMIC PATH (PCE computes):
        "path-optimization-objective": "delay",  // igp-metric|te-metric|delay|hop-count
        "protected": true,                       // Use only protected links
        "affinities": {
          "include-all": 0,
          "include-any": 1,
          "exclude-any": 2
        },
        "disjointness": {
          "association-group": 20,
          "association-sub-group": 0,
          "disjointness-type": "node"    // node|circuit|srlg|srlg-node
        },
        // OR EXPLICIT PATH (user-defined SIDs):
        "hops": [
          {"hop": {"node-ipv4-address": "198.51.100.10"}, "step": 1},
          {"hop": {"node-ipv4-address": "198.51.100.20"}, "step": 2}
        ]
      }
    }]
  }
}
```

### API Response Schema

```json
{
  "output": {
    "results": [{
      "head-end": "192.0.2.1",
      "end-point": "192.0.2.8",
      "color": 100,
      "state": "success",    // success|failure|degraded
      "message": "Policy created"
    }]
  }
}
```

---

## Binding SID (BSID) Strategy

Binding SIDs abstract SR policies as single segments for:
- **Path Summarization**: Hide internal segments from other nodes
- **Policy Stitching**: Concatenate policies across domains
- **Service Integration**: Map services to policies

| TE Type | BSID Format | Allocation |
|---------|-------------|------------|
| SR-MPLS | MPLS Label (20-bit) | From SRLB (e.g., 24000-24999) |
| SRv6 | IPv6 Address (128-bit) | From SRv6 locator (auto-allocated) |
| RSVP-TE | Optional binding-label | User-specified or auto |

**Design Decision**: Let PCE/headend auto-allocate BSIDs. Store BSID in Redis for traffic steering reference.

---

## Traffic Matrix Data Sources (All TE Types)

### SRv6 (Best Visibility)
| Source | Data Type | Collection Method |
|--------|-----------|-------------------|
| SR-PM | Delay, loss, jitter | TWAMP-Light probes |
| IOAM (In-situ OAM) | Hop-by-hop telemetry | IPv6 extension header |
| IPv6 Flow Labels | Flow identification | 20-bit field in IPv6 header |
| NetFlow v9/IPFIX | Flow records with SRv6 SID | Export from PE routers |
| MDT Telemetry | Interface counters | gRPC streaming |

### SR-MPLS (Moderate Visibility)
| Source | Data Type | Collection Method |
|--------|-----------|-------------------|
| SR-PM (Color-aware) | Delay, loss per policy | RFC 6374 PM |
| MPLS Interface Counters | Bytes/packets per label | SNMP or telemetry |
| Policy/BSID Counters | Traffic per SR policy | IOS-XR counters |
| Segment Counters | Per-SID traffic | Headend/transit counters |
| CNC TE Dashboard | Tunnel utilization | REST API query |

### RSVP-TE (Traditional Visibility)
| Source | Data Type | Collection Method |
|--------|-----------|-------------------|
| Bandwidth Reservations | Reserved BW per LSP | RSVP signaling |
| FRR Counters | Backup path usage | SNMP/telemetry |
| Tunnel Interface Counters | Bytes/packets | Interface stats |
| RSVP Session Stats | LSP state, errors | `show mpls traffic-eng` |
| CNC RSVP Tab | LSP status, path | REST API query |

### Unified Telemetry Approach

```
┌─────────────────────────────────────────────────────────────┐
│              Traffic Analytics Agent                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ SR-PM       │  │ MDT/gRPC    │  │ NetFlow/IPFIX      │ │
│  │ Collector   │  │ Telemetry   │  │ Collector          │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │            │
│         └────────────────┼─────────────────────┘            │
│                          ▼                                  │
│              ┌───────────────────────┐                      │
│              │  Demand Matrix Builder │                      │
│              │  (PE-to-PE volumes)    │                      │
│              └───────────┬───────────┘                      │
│                          ▼                                  │
│              ┌───────────────────────┐                      │
│              │ Congestion Predictor  │                      │
│              │ (Threshold: 70%)      │                      │
│              └───────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

---

## PCEP Protocol Integration

SR-PCE uses PCEP (Path Computation Element Communication Protocol) for:

| Message | Direction | Purpose |
|---------|-----------|---------|
| PCReq | PCC → PCE | Request path computation |
| PCRep | PCE → PCC | Return computed path |
| PCInitiate | PCE → PCC | Instantiate SR policy (PCE-initiated) |
| PCUpd | PCE → PCC | Update existing policy path |
| PCRpt | PCC → PCE | Report policy state to PCE |

**Stateful PCE**: CNC's SR-PCE maintains state of all tunnels (delegated control), enabling:
- Automatic reoptimization on topology changes
- Coordinated disjoint path computation
- Bandwidth-aware path selection using demand matrix

---

## BGP-LS Topology Discovery

CNC learns network topology via BGP-LS (Link-State):

```
Network Devices (ISIS/OSPF with SR extensions)
         │
         │ BGP-LS (RFC 7752)
         ▼
┌─────────────────────────────────────┐
│  CNC SR-PCE Traffic Engineering DB  │
│  - Nodes (routers, loopbacks)       │
│  - Links (interfaces, metrics)      │
│  - SIDs (Prefix-SID, Adj-SID)       │
│  - TE attributes (affinity, BW)     │
│  - SRv6 Locators                    │
└─────────────────────────────────────┘
```

**Knowledge Graph Integration**: Our existing KG already has topology from BGP-LS. The Path Computation Agent queries KG's Dijkstra API with constraints, which mirrors what SR-PCE does internally.

---

## Traffic Steering Mechanisms

### 1. BGP Color-Based Steering (Recommended)
```
Egress PE advertises routes with Color Extended Community
         │
         ▼
Ingress PE receives route with Color X
         │
         ▼
SR Policy (Color X, Endpoint=Egress PE) auto-selected
         │
         ▼
Traffic steered into SR Policy via BSID
```

### 2. On-Demand Next-hop (ODN)
```
Route with Color X appears at Ingress PE
         │
         ▼
No existing policy for (Color X, Endpoint)?
         │
         ▼
PCE computes path dynamically (via PCEP)
         │
         ▼
SR Policy instantiated automatically
```

### 3. Autoroute Announce
SR Policy can be announced into IGP, making it preferred for destination prefix.

**Design Decision**: Use BGP Color + ODN for automated steering. Tunnel Provisioning Agent creates policies with appropriate color; Service Impact Agent maps affected services to colors.

---

## Detailed Agent Designs

### Agent 1: Orchestrator Agent

**Purpose**: Supervisor agent that coordinates the entire protection workflow using a state machine with hybrid (rules + LLM) decision logic.

#### LangGraph State Schema

```python
from typing import TypedDict, List, Optional, Literal
from pydantic import BaseModel

class IncidentState(TypedDict):
    # Incident identification
    incident_id: str
    status: Literal["detecting", "assessing", "computing", "provisioning",
                    "steering", "monitoring", "restoring", "closed", "escalated"]

    # Alert data
    alert_type: Literal["pca_sla", "cnc_alarm", "proactive"]
    degraded_links: List[str]
    severity: Literal["critical", "major", "minor", "warning"]

    # Affected services
    affected_services: List[dict]  # [{service_id, type, sla_tier, endpoints}]

    # Protection path
    alternate_path: Optional[dict]  # {path_id, segments, te_type, metrics}
    tunnel_id: Optional[str]
    binding_sid: Optional[int]

    # Restoration
    hold_timer_start: Optional[str]  # ISO timestamp
    sla_recovered: bool
    cutover_mode: Literal["immediate", "gradual"]
    cutover_progress: Optional[int]  # 0-100%

    # Workflow control
    retry_count: int
    error_message: Optional[str]
    llm_reasoning: Optional[str]  # For edge cases
```

#### LangGraph Nodes & Transitions

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR STATE MACHINE                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐      │
│   │  START   │────▶│ DETECT   │────▶│  ASSESS  │────▶│ COMPUTE  │      │
│   └──────────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘      │
│                         │                │                 │            │
│                    [flapping]       [no services]    [no path]         │
│                         │                │                 │            │
│                         ▼                ▼                 ▼            │
│                    ┌─────────┐      ┌─────────┐      ┌─────────┐       │
│                    │ DAMPEN  │      │  CLOSE  │      │ESCALATE │       │
│                    └─────────┘      └─────────┘      └─────────┘       │
│                                                                          │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐      │
│   │PROVISION │◀────│          │     │  STEER   │────▶│ MONITOR  │      │
│   └────┬─────┘     │          │     └────┬─────┘     └────┬─────┘      │
│        │           │          │          │                 │            │
│   [success]        │          │     [success]         [recovered]      │
│        │           │          │          │                 │            │
│        ▼           │          │          ▼                 ▼            │
│   ┌──────────┐     │          │     ┌──────────┐     ┌──────────┐      │
│   │  STEER   │─────┘          └─────│PROVISION │     │ RESTORE  │      │
│   └──────────┘    [retry<3]         └──────────┘     └────┬─────┘      │
│                                                            │            │
│                                                       [complete]        │
│                                                            │            │
│                                                            ▼            │
│                                                       ┌──────────┐      │
│                                                       │  CLOSE   │      │
│                                                       └──────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Type | Action | Next States |
|------|------|--------|-------------|
| `start` | Entry | Initialize incident, call Event Correlator | `detect` |
| `detect` | Rule | Check flap detection, deduplicate | `assess`, `dampen` |
| `assess` | Rule | Call Service Impact Agent | `compute`, `close` |
| `compute` | Rule | Call Path Computation Agent | `provision`, `escalate` |
| `provision` | Rule | Call Tunnel Provisioning Agent | `steer`, `escalate` |
| `steer` | Rule | Activate traffic steering | `monitor`, `provision` |
| `monitor` | Rule | Call Restoration Monitor Agent | `restore`, `monitor` |
| `restore` | Rule | Execute cutover, remove tunnel | `close` |
| `dampen` | Rule | Apply exponential backoff | `detect` (after delay) |
| `escalate` | **LLM** | Analyze failure, recommend action | `close`, manual |
| `close` | Rule | Cleanup, notify, audit | END |

#### LLM Decision Points

The Orchestrator uses LLM reasoning only for edge cases:

```python
LLM_TRIGGERS = [
    "no_alternate_path",           # All paths exhausted
    "cascading_failure",           # Protection path also degraded
    "tunnel_provision_failed_3x",  # Max retries exceeded
    "conflicting_constraints",     # Service requirements conflict
    "unknown_te_type",             # Cannot auto-detect tunnel technology
]
```

#### Tools

```python
# Tool 1: Call Agent via A2A
class CallAgentInput(BaseModel):
    agent_name: str  # event_correlator, service_impact, path_computation, etc.
    task_type: str   # correlate_alert, assess_impact, compute_path, etc.
    payload: dict    # Task-specific data

class CallAgentOutput(BaseModel):
    success: bool
    result: dict
    error: Optional[str]

# Tool 2: Redis State Management
class UpdateIncidentInput(BaseModel):
    incident_id: str
    updates: dict  # Fields to update

class GetIncidentInput(BaseModel):
    incident_id: str

# Tool 3: LLM Reasoning (for edge cases)
class LLMReasonInput(BaseModel):
    context: str      # Current state summary
    question: str     # What decision is needed
    options: List[str]  # Available actions

class LLMReasonOutput(BaseModel):
    decision: str
    reasoning: str
    confidence: float
```

#### A2A Task Schema (Outbound)

```json
{
  "task_id": "uuid",
  "task_type": "assess_impact",
  "incident_id": "INC-2026-0001",
  "payload": {
    "degraded_links": ["link-001", "link-002"],
    "severity": "critical"
  },
  "callback_url": "http://orchestrator:8000/tasks/callback",
  "timeout_seconds": 30
}
```

---

### Agent 2: Event Correlator Agent

**Purpose**: Receives alerts from PCA and CNC, deduplicates, correlates related events, and detects link flapping to prevent alert storms.

#### LangGraph Nodes

```
┌─────────────────────────────────────────────────────────────┐
│                 EVENT CORRELATOR FLOW                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐           │
│   │  INGEST  │────▶│  DEDUP   │────▶│CORRELATE │           │
│   └──────────┘     └────┬─────┘     └────┬─────┘           │
│        ▲                │                │                  │
│        │           [duplicate]      [correlated]           │
│   PCA/CNC              │                │                  │
│   Webhooks             ▼                ▼                  │
│                   ┌─────────┐      ┌─────────┐             │
│                   │ DISCARD │      │  FLAP   │             │
│                   └─────────┘      │ DETECT  │             │
│                                    └────┬────┘             │
│                                         │                  │
│                              ┌──────────┼──────────┐       │
│                              │          │          │       │
│                         [stable]   [flapping]  [new]      │
│                              │          │          │       │
│                              ▼          ▼          ▼       │
│                         ┌────────┐ ┌────────┐ ┌────────┐  │
│                         │ EMIT   │ │SUPPRESS│ │ EMIT   │  │
│                         │INCIDENT│ │& DAMPEN│ │INCIDENT│  │
│                         └────────┘ └────────┘ └────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Action | Output |
|------|--------|--------|
| `ingest` | Parse PCA/CNC alert, normalize to internal format | Normalized alert |
| `dedup` | Check Redis for recent identical alerts (5-min window) | Pass/Discard |
| `correlate` | Group related alerts (same link, time window) | Correlated event |
| `flap_detect` | Check flap history, apply exponential backoff | Stable/Flapping |
| `emit_incident` | Create incident, notify Orchestrator | Incident created |
| `suppress` | Log suppression, update flap counter | Alert suppressed |

#### Alert Normalization Schema

```python
class NormalizedAlert(BaseModel):
    alert_id: str
    source: Literal["pca", "cnc", "proactive"]
    timestamp: datetime

    # Link identification
    link_id: str              # Topology link ID
    interface_a: str          # e.g., "PE1:GigE0/0/0/1"
    interface_z: str          # e.g., "P1:GigE0/0/0/2"

    # SLA metrics (from PCA)
    latency_ms: Optional[float]
    jitter_ms: Optional[float]
    packet_loss_pct: Optional[float]

    # Thresholds violated
    violated_thresholds: List[str]  # ["latency", "loss"]

    # Severity
    severity: Literal["critical", "major", "minor", "warning"]

    # Raw alert for audit
    raw_payload: dict
```

#### Flap Detection Algorithm

```python
class FlapDetector:
    """
    Exponential backoff for flapping links.

    State transitions within FLAP_WINDOW trigger damping.
    Damping time doubles each occurrence, up to MAX_DAMPEN.
    """
    FLAP_WINDOW = 300       # 5 minutes
    FLAP_THRESHOLD = 3      # 3 state changes = flapping
    INITIAL_DAMPEN = 60     # 1 minute initial suppression
    MAX_DAMPEN = 3600       # 1 hour max suppression

    def check_flapping(self, link_id: str) -> tuple[bool, int]:
        """Returns (is_flapping, dampen_seconds)"""
        history = redis.lrange(f"flap:{link_id}", 0, -1)
        recent = [h for h in history if within_window(h, self.FLAP_WINDOW)]

        if len(recent) >= self.FLAP_THRESHOLD:
            # Calculate exponential backoff
            flap_count = redis.incr(f"flap_count:{link_id}")
            dampen_time = min(
                self.INITIAL_DAMPEN * (2 ** (flap_count - 1)),
                self.MAX_DAMPEN
            )
            return True, dampen_time

        return False, 0
```

#### Correlation Rules

```python
CORRELATION_RULES = [
    {
        "name": "same_link_multiple_metrics",
        "description": "Multiple SLA violations on same link within 60s",
        "window_seconds": 60,
        "group_by": ["link_id"],
        "action": "merge_into_single_incident"
    },
    {
        "name": "adjacent_link_failures",
        "description": "Alerts on links sharing a node within 30s",
        "window_seconds": 30,
        "group_by": ["shared_node"],
        "action": "flag_potential_node_issue"
    },
    {
        "name": "path_correlation",
        "description": "Multiple links on same SR policy path",
        "window_seconds": 120,
        "group_by": ["policy_path"],
        "action": "identify_root_cause_link"
    }
]
```

#### Tools

```python
# Tool 1: PCA Webhook Handler
class PCAAlertInput(BaseModel):
    """Incoming PCA webhook payload"""
    alert_id: str
    probe_id: str
    metric_type: Literal["latency", "jitter", "loss"]
    current_value: float
    threshold_value: float
    source_ip: str
    dest_ip: str
    timestamp: str

# Tool 2: CNC Alarm Handler
class CNCAlarmInput(BaseModel):
    """Incoming CNC alarm payload"""
    alarm_id: str
    alarm_type: str
    device_name: str
    interface_name: str
    severity: str
    description: str
    timestamp: str

# Tool 3: Redis Dedup Check
class DedupCheckInput(BaseModel):
    alert_hash: str  # Hash of normalized alert
    window_seconds: int = 300

class DedupCheckOutput(BaseModel):
    is_duplicate: bool
    original_incident_id: Optional[str]

# Tool 4: Emit Incident to Orchestrator
class EmitIncidentInput(BaseModel):
    correlated_alerts: List[NormalizedAlert]
    severity: str
    degraded_links: List[str]
```

#### A2A Task Schema (Inbound from Orchestrator)

```json
{
  "task_type": "correlate_alert",
  "payload": {
    "alert_source": "pca",
    "raw_alert": { ... }
  }
}
```

#### A2A Task Schema (Outbound to Orchestrator)

```json
{
  "task_type": "incident_detected",
  "payload": {
    "incident_id": "INC-2026-0001",
    "degraded_links": ["link-001"],
    "severity": "critical",
    "alert_count": 3,
    "is_flapping": false,
    "correlated_alerts": [ ... ]
  }
}
```

---

### Agent 3: Service Impact Agent

**Purpose**: Queries CNC Service Health API to identify L3VPN/L2VPN services affected by degraded links, returning service details and SLA tiers.

#### LangGraph Nodes

```
┌─────────────────────────────────────────────────────────┐
│               SERVICE IMPACT FLOW                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐       │
│   │  QUERY   │────▶│ ANALYZE  │────▶│ ENRICH   │       │
│   │ SERVICES │     │  IMPACT  │     │   SLA    │       │
│   └──────────┘     └──────────┘     └────┬─────┘       │
│        │                                  │             │
│   CNC Service                        [services        │
│   Health API                          found]           │
│                                          │             │
│                                          ▼             │
│                                    ┌──────────┐        │
│                                    │  RETURN  │        │
│                                    │ AFFECTED │        │
│                                    └──────────┘        │
└─────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Action | Output |
|------|--------|--------|
| `query_services` | Call CNC Service Health API for services using degraded links | Service list |
| `analyze_impact` | Determine impact severity based on service type and redundancy | Impact assessment |
| `enrich_sla` | Lookup SLA tier from service metadata, determine priority | Enriched services |
| `return_affected` | Return sorted list (by SLA tier) to Orchestrator | Response |

#### CNC Service Health API Integration

```python
# CNC Service Health API Endpoint
CNC_SERVICE_HEALTH_URL = "https://{cnc_host}:30603/crosswork/nbi/servicehealth/v1"

class CNCServiceHealthClient:
    """Client for CNC Service Health API"""

    async def get_services_by_link(self, link_id: str) -> List[dict]:
        """
        Query services traversing a specific link.

        GET /services?filter=link_id={link_id}
        """
        response = await self.client.get(
            f"{self.base_url}/services",
            params={"filter": f"link_id={link_id}"},
            headers={"Authorization": f"Bearer {self.jwt_token}"}
        )
        return response.json()["services"]

    async def get_service_details(self, service_id: str) -> dict:
        """
        Get detailed service information including endpoints.

        GET /services/{service_id}
        """
        response = await self.client.get(
            f"{self.base_url}/services/{service_id}",
            headers={"Authorization": f"Bearer {self.jwt_token}"}
        )
        return response.json()
```

#### Service Impact Schema

```python
class AffectedService(BaseModel):
    service_id: str
    service_name: str
    service_type: Literal["l3vpn", "l2vpn", "evpn", "p2p"]

    # Endpoints
    endpoint_a: str  # PE router A
    endpoint_z: str  # PE router Z

    # Customer info
    customer_id: str
    customer_name: str

    # SLA tier (determines priority)
    sla_tier: Literal["platinum", "gold", "silver", "bronze"]

    # Current path info
    current_te_type: Literal["rsvp-te", "sr-mpls", "srv6", "igp"]
    current_path: List[str]  # List of node/link IDs

    # Impact assessment
    impact_level: Literal["full_outage", "degraded", "at_risk"]
    redundancy_available: bool

class ServiceImpactResponse(BaseModel):
    incident_id: str
    total_affected: int
    services_by_tier: dict[str, int]  # {"platinum": 5, "gold": 10, ...}
    affected_services: List[AffectedService]
```

#### SLA Tier Priority

```python
SLA_TIER_CONFIG = {
    "platinum": {
        "priority": 1,
        "hold_timer_seconds": 60,      # Short hold time
        "cutover_mode": "immediate",
        "notification_channels": ["webex", "servicenow", "email"],
    },
    "gold": {
        "priority": 2,
        "hold_timer_seconds": 300,     # 5 minutes
        "cutover_mode": "immediate",
        "notification_channels": ["webex", "email"],
    },
    "silver": {
        "priority": 3,
        "hold_timer_seconds": 600,     # 10 minutes
        "cutover_mode": "gradual",
        "notification_channels": ["email"],
    },
    "bronze": {
        "priority": 4,
        "hold_timer_seconds": 1800,    # 30 minutes
        "cutover_mode": "gradual",
        "notification_channels": ["email"],
    },
}
```

#### Tools

```python
# Tool 1: Query CNC Service Health
class QueryServicesInput(BaseModel):
    degraded_links: List[str]

class QueryServicesOutput(BaseModel):
    services: List[dict]
    query_time_ms: int

# Tool 2: Enrich with SLA Data
class EnrichSLAInput(BaseModel):
    service_id: str

class EnrichSLAOutput(BaseModel):
    sla_tier: str
    hold_timer_seconds: int
    cutover_mode: str
    notification_channels: List[str]
```

#### A2A Task Schema

```json
{
  "task_type": "assess_impact",
  "payload": {
    "incident_id": "INC-2026-0001",
    "degraded_links": ["link-001", "link-002"]
  }
}

// Response
{
  "task_type": "impact_assessed",
  "payload": {
    "incident_id": "INC-2026-0001",
    "total_affected": 15,
    "services_by_tier": {"platinum": 2, "gold": 5, "silver": 8},
    "affected_services": [ ... ]
  }
}
```

---

### Agent 4: Path Computation Agent

**Purpose**: Queries the Knowledge Graph Dijkstra API to compute alternate paths that avoid degraded links, respecting TE constraints.

#### LangGraph Nodes

```
┌─────────────────────────────────────────────────────────────┐
│                 PATH COMPUTATION FLOW                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐           │
│   │  BUILD   │────▶│  QUERY   │────▶│ VALIDATE │           │
│   │CONSTRAINT│     │    KG    │     │   PATH   │           │
│   └──────────┘     └────┬─────┘     └────┬─────┘           │
│                         │                 │                 │
│                    [no path]         [valid]                │
│                         │                 │                 │
│                         ▼                 ▼                 │
│                    ┌─────────┐      ┌─────────┐            │
│                    │ RELAX   │      │ RETURN  │            │
│                    │CONSTRAINT│     │  PATH   │            │
│                    └────┬────┘      └─────────┘            │
│                         │                                   │
│                    [retry]                                  │
│                         │                                   │
│                         ▼                                   │
│                    ┌─────────┐                              │
│                    │  QUERY  │                              │
│                    │   KG    │                              │
│                    └─────────┘                              │
└─────────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Action | Output |
|------|--------|--------|
| `build_constraints` | Build avoidance constraints (links, nodes, SRLGs) | Constraint object |
| `query_kg` | Call KG Dijkstra API with constraints | Path or null |
| `validate_path` | Check path meets SLA requirements (delay, BW) | Valid/Invalid |
| `relax_constraints` | Remove less critical constraints, retry | Relaxed constraints |
| `return_path` | Return computed path to Orchestrator | Path response |

#### Knowledge Graph Dijkstra API

```python
# KG Dijkstra API (existing infrastructure)
KG_DIJKSTRA_URL = "https://{kg_host}/api/v1/dijkstra"

class KGDijkstraClient:
    """Client for Knowledge Graph path computation"""

    async def compute_path(
        self,
        source: str,
        destination: str,
        constraints: PathConstraints
    ) -> Optional[ComputedPath]:
        """
        Compute shortest path with constraints.

        POST /dijkstra
        {
          "source": "PE1",
          "destination": "PE2",
          "avoid_links": ["link-001"],
          "avoid_nodes": [],
          "avoid_srlgs": [],
          "metric": "delay",  // or "igp", "te"
          "max_hops": 10
        }
        """
        payload = {
            "source": source,
            "destination": destination,
            "avoid_links": constraints.avoid_links,
            "avoid_nodes": constraints.avoid_nodes,
            "avoid_srlgs": constraints.avoid_srlgs,
            "metric": constraints.optimization_metric,
            "max_hops": constraints.max_hops,
        }
        response = await self.client.post(
            f"{self.base_url}/dijkstra",
            json=payload
        )
        if response.status_code == 200:
            return ComputedPath(**response.json())
        return None
```

#### Constraint Schema

```python
class PathConstraints(BaseModel):
    # Avoidance constraints
    avoid_links: List[str] = []      # Link IDs to avoid
    avoid_nodes: List[str] = []      # Node IDs to avoid
    avoid_srlgs: List[str] = []      # SRLG IDs to avoid

    # Optimization objective
    optimization_metric: Literal["igp", "te", "delay", "hop_count"] = "delay"

    # Affinity constraints (from CNC)
    include_affinities: int = 0      # Bitmask
    exclude_affinities: int = 0      # Bitmask

    # Limits
    max_hops: int = 10
    max_delay_ms: Optional[float] = None
    min_bandwidth_gbps: Optional[float] = None

    # Disjointness
    disjoint_from_path: Optional[List[str]] = None
    disjointness_type: Optional[Literal["node", "link", "srlg"]] = None

class ComputedPath(BaseModel):
    path_id: str
    source: str
    destination: str

    # Path details
    segments: List[str]           # Ordered list of node/link IDs
    segment_sids: List[int]       # Corresponding SIDs (for SR)
    total_hops: int

    # Metrics
    total_delay_ms: float
    total_igp_metric: int
    total_te_metric: int
    min_available_bandwidth_gbps: float

    # TE type recommendation
    recommended_te_type: Literal["sr-mpls", "srv6", "rsvp-te"]
```

#### Constraint Relaxation Strategy

```python
RELAXATION_ORDER = [
    "avoid_srlgs",         # First, allow same SRLG
    "max_hops",            # Then, allow more hops (increase by 5)
    "optimization_metric", # Then, switch from delay to igp
    "avoid_nodes",         # Last resort: allow same transit nodes
    # Never relax: avoid_links (the degraded links)
]

def relax_constraints(constraints: PathConstraints, level: int) -> PathConstraints:
    """Progressively relax constraints to find a path"""
    relaxed = constraints.copy()

    if level >= 1:
        relaxed.avoid_srlgs = []
    if level >= 2:
        relaxed.max_hops += 5
    if level >= 3:
        relaxed.optimization_metric = "igp"
    if level >= 4:
        relaxed.avoid_nodes = []

    return relaxed
```

#### Tools

```python
# Tool 1: Build Constraints
class BuildConstraintsInput(BaseModel):
    degraded_links: List[str]
    affected_service: AffectedService
    existing_policies: List[str]  # For disjointness

class BuildConstraintsOutput(BaseModel):
    constraints: PathConstraints

# Tool 2: Query Knowledge Graph
class QueryKGInput(BaseModel):
    source: str
    destination: str
    constraints: PathConstraints

class QueryKGOutput(BaseModel):
    path_found: bool
    path: Optional[ComputedPath]
    computation_time_ms: int

# Tool 3: Validate Path
class ValidatePathInput(BaseModel):
    path: ComputedPath
    required_sla: dict  # {max_delay_ms, min_bandwidth}

class ValidatePathOutput(BaseModel):
    is_valid: bool
    violations: List[str]
```

#### A2A Task Schema

```json
{
  "task_type": "compute_path",
  "payload": {
    "incident_id": "INC-2026-0001",
    "source_pe": "PE1",
    "destination_pe": "PE2",
    "degraded_links": ["link-001"],
    "service_sla_tier": "platinum",
    "current_te_type": "sr-mpls"
  }
}

// Response
{
  "task_type": "path_computed",
  "payload": {
    "incident_id": "INC-2026-0001",
    "path_found": true,
    "path": {
      "path_id": "path-001",
      "segments": ["PE1", "P2", "P3", "PE2"],
      "segment_sids": [16001, 16002, 16003, 16004],
      "total_delay_ms": 12.5,
      "recommended_te_type": "sr-mpls"
    }
  }
}
```

---

### Agent 5: Tunnel Provisioning Agent

**Purpose**: Creates protection tunnels (RSVP-TE, SR-MPLS, or SRv6) via CNC PCE APIs, auto-detecting the appropriate TE technology based on existing service configuration.

#### LangGraph Nodes

```
┌─────────────────────────────────────────────────────────────────┐
│                 TUNNEL PROVISIONING FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ DETECT   │────▶│  BUILD   │────▶│  CREATE  │               │
│   │ TE TYPE  │     │ PAYLOAD  │     │  TUNNEL  │               │
│   └──────────┘     └──────────┘     └────┬─────┘               │
│                                          │                      │
│                                   ┌──────┴──────┐              │
│                               [success]     [failure]           │
│                                   │             │               │
│                                   ▼             ▼               │
│                              ┌─────────┐  ┌─────────┐          │
│                              │ VERIFY  │  │  RETRY  │          │
│                              │ TUNNEL  │  │ (max 3) │          │
│                              └────┬────┘  └────┬────┘          │
│                                   │            │                │
│                              [verified]   [exhausted]           │
│                                   │            │                │
│                                   ▼            ▼                │
│                              ┌─────────┐  ┌─────────┐          │
│                              │ STEER   │  │ESCALATE │          │
│                              │ TRAFFIC │  └─────────┘          │
│                              └────┬────┘                        │
│                                   │                             │
│                              [steered]                          │
│                                   │                             │
│                                   ▼                             │
│                              ┌─────────┐                        │
│                              │ RETURN  │                        │
│                              │ SUCCESS │                        │
│                              └─────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Action | Output |
|------|--------|--------|
| `detect_te_type` | Determine TE type from existing service config | rsvp-te/sr-mpls/srv6 |
| `build_payload` | Construct CNC API payload for tunnel creation | JSON payload |
| `create_tunnel` | Call CNC tunnel provisioning API | Tunnel ID or error |
| `verify_tunnel` | Verify tunnel is UP via CNC API | Verified/Failed |
| `steer_traffic` | Activate traffic steering to new tunnel | Steered |
| `retry` | Exponential backoff retry (max 3 attempts) | Retry/Escalate |
| `return_success` | Return tunnel details to Orchestrator | Response |

#### TE Type Detection Logic

```python
class TETypeDetector:
    """Auto-detect appropriate TE technology based on service config"""

    def detect(self, service: AffectedService, path: ComputedPath) -> str:
        """
        Detection priority:
        1. Match existing service TE type (if known)
        2. Check head-end capabilities
        3. Default to SR-MPLS (most compatible)
        """
        # 1. Match existing
        if service.current_te_type in ["rsvp-te", "sr-mpls", "srv6"]:
            return service.current_te_type

        # 2. Check capabilities (query from KG)
        headend_caps = self.get_device_capabilities(service.endpoint_a)

        if "srv6" in headend_caps and self.is_srv6_enabled(path):
            return "srv6"
        elif "sr-mpls" in headend_caps:
            return "sr-mpls"
        elif "rsvp-te" in headend_caps:
            return "rsvp-te"

        # 3. Default
        return "sr-mpls"
```

#### CNC Tunnel Creation Payloads

```python
# SR-MPLS Policy Payload
class SRMPLSPolicyPayload(BaseModel):
    head_end: str              # "192.0.2.1"
    end_point: str             # "192.0.2.8"
    color: int                 # Policy color (auto-generated)
    path_name: str             # "protection-INC-2026-0001"
    binding_sid: Optional[int] # Auto-allocated if not specified
    description: str
    sr_policy_path: dict       # Dynamic or explicit path

# SRv6 Policy Payload (same structure, IPv6 addresses)
class SRv6PolicyPayload(BaseModel):
    head_end: str              # "2001:db8:0:1::1"
    end_point: str             # "2001:db8:0:5::1"
    color: int
    path_name: str
    description: str
    sr_policy_path: dict

# RSVP-TE Tunnel Payload
class RSVPTETunnelPayload(BaseModel):
    head_end: str
    end_point: str
    path_name: str
    signaled_bandwidth: int    # bps
    setup_priority: int = 7
    hold_priority: int = 7
    fast_re_route: str = "enable"
    rsvp_te_tunnel_path: dict  # Dynamic or explicit
```

#### MCP Tool Definitions

```python
# MCP Server provides these tools for CNC operations

# Tool: create_sr_policy
class CreateSRPolicyInput(BaseModel):
    te_type: Literal["sr-mpls", "srv6"]
    head_end: str
    end_point: str
    color: int
    path_name: str
    path_type: Literal["dynamic", "explicit"]

    # For dynamic path
    optimization_objective: Optional[str]  # delay, igp, te
    protected: bool = True
    affinities: Optional[dict] = None
    disjointness: Optional[dict] = None

    # For explicit path
    explicit_hops: Optional[List[dict]] = None

class CreateSRPolicyOutput(BaseModel):
    success: bool
    tunnel_id: Optional[str]
    binding_sid: Optional[int]
    state: Literal["success", "failure", "degraded"]
    message: str

# Tool: create_rsvp_tunnel
class CreateRSVPTunnelInput(BaseModel):
    head_end: str
    end_point: str
    path_name: str
    bandwidth_bps: int
    fast_reroute: bool = True
    optimization_objective: str = "te-metric"

    # For explicit path
    explicit_hops: Optional[List[dict]] = None

class CreateRSVPTunnelOutput(BaseModel):
    success: bool
    tunnel_id: Optional[str]
    binding_label: Optional[int]
    state: str
    message: str

# Tool: verify_tunnel_status
class VerifyTunnelInput(BaseModel):
    tunnel_type: Literal["sr-policy", "rsvp-te"]
    tunnel_id: str

class VerifyTunnelOutput(BaseModel):
    exists: bool
    operational_status: Literal["up", "down", "unknown"]
    admin_status: Literal["enabled", "disabled"]
    path_info: Optional[dict]

# Tool: delete_tunnel
class DeleteTunnelInput(BaseModel):
    tunnel_type: Literal["sr-policy", "rsvp-te"]
    tunnel_id: str

class DeleteTunnelOutput(BaseModel):
    success: bool
    message: str
```

#### BSID Allocation

```python
class BSIDAllocator:
    """
    Allocate Binding SIDs for SR policies.
    Uses Redis to track allocated BSIDs per head-end.
    """
    SR_MPLS_BSID_RANGE = (24000, 24999)  # SRLB range
    SRV6_BSID_PREFIX = "fc00:0:ffff::"  # SRv6 BSID locator

    def allocate_mpls_bsid(self, head_end: str) -> int:
        """Allocate next available MPLS BSID for head-end"""
        key = f"bsid:mpls:{head_end}"
        current = redis.get(key) or self.SR_MPLS_BSID_RANGE[0]
        next_bsid = int(current) + 1

        if next_bsid > self.SR_MPLS_BSID_RANGE[1]:
            raise BSIDExhausted(f"No more BSIDs for {head_end}")

        redis.set(key, next_bsid)
        return next_bsid

    def release_bsid(self, head_end: str, bsid: int):
        """Release BSID back to pool (on tunnel deletion)"""
        # Add to free list for reuse
        redis.sadd(f"bsid:free:{head_end}", bsid)
```

#### A2A Task Schema

```json
{
  "task_type": "provision_tunnel",
  "payload": {
    "incident_id": "INC-2026-0001",
    "service_id": "svc-001",
    "te_type": "sr-mpls",
    "head_end": "192.0.2.1",
    "end_point": "192.0.2.8",
    "computed_path": {
      "segments": ["PE1", "P2", "P3", "PE2"],
      "segment_sids": [16001, 16002, 16003, 16004]
    },
    "path_type": "explicit"
  }
}

// Response
{
  "task_type": "tunnel_provisioned",
  "payload": {
    "incident_id": "INC-2026-0001",
    "success": true,
    "tunnel_id": "sr-policy-001",
    "binding_sid": 24001,
    "te_type": "sr-mpls",
    "operational_status": "up"
  }
}
```

---

### Agent 6: Restoration Monitor Agent

**Purpose**: Monitors SLA recovery via PCA, manages hold timers, verifies stability, and orchestrates traffic cutover (immediate or gradual) back to the original path.

#### LangGraph Nodes

```
┌─────────────────────────────────────────────────────────────────────┐
│                   RESTORATION MONITOR FLOW                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐                   │
│   │  POLL    │────▶│  CHECK   │────▶│  START   │                   │
│   │   SLA    │     │ RECOVERY │     │  TIMER   │                   │
│   └────┬─────┘     └────┬─────┘     └────┬─────┘                   │
│        │                │                 │                         │
│   [degraded]       [not recovered]   [timer set]                   │
│        │                │                 │                         │
│        ▼                ▼                 ▼                         │
│   ┌─────────┐      ┌─────────┐      ┌─────────┐                    │
│   │  WAIT   │      │  WAIT   │      │  WAIT   │                    │
│   │(30 sec) │      │(30 sec) │      │  TIMER  │                    │
│   └─────────┘      └─────────┘      └────┬────┘                    │
│                                          │                          │
│                                     [timer done]                    │
│                                          │                          │
│                                          ▼                          │
│                                     ┌─────────┐                     │
│                                     │ VERIFY  │                     │
│                                     │STABILITY│                     │
│                                     └────┬────┘                     │
│                                          │                          │
│                              ┌───────────┴───────────┐             │
│                          [stable]              [unstable]          │
│                              │                       │              │
│                              ▼                       ▼              │
│                         ┌─────────┐           ┌─────────┐          │
│                         │ CUTOVER │           │  RESET  │          │
│                         │ TRAFFIC │           │  TIMER  │          │
│                         └────┬────┘           └─────────┘          │
│                              │                                      │
│                   ┌──────────┴──────────┐                          │
│              [immediate]           [gradual]                        │
│                   │                     │                           │
│                   ▼                     ▼                           │
│              ┌─────────┐          ┌─────────┐                       │
│              │  FULL   │          │ STAGED  │──▶ 75/25 ──▶ 50/50   │
│              │ CUTOVER │          │ CUTOVER │──▶ 25/75 ──▶ 0/100   │
│              └────┬────┘          └────┬────┘                       │
│                   │                    │                            │
│                   └────────┬───────────┘                           │
│                            │                                        │
│                            ▼                                        │
│                       ┌─────────┐                                   │
│                       │ CLEANUP │                                   │
│                       │ TUNNEL  │                                   │
│                       └────┬────┘                                   │
│                            │                                        │
│                            ▼                                        │
│                       ┌─────────┐                                   │
│                       │ RETURN  │                                   │
│                       │RESTORED │                                   │
│                       └─────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Action | Output |
|------|--------|--------|
| `poll_sla` | Query PCA for current SLA metrics on original path | Metrics |
| `check_recovery` | Compare metrics against SLA thresholds | Recovered/Degraded |
| `start_timer` | Set hold timer in Redis (per SLA tier) | Timer ID |
| `wait_timer` | Wait for hold timer expiration | Timer done |
| `verify_stability` | Confirm SLA stable for verification period | Stable/Unstable |
| `cutover_traffic` | Execute immediate or gradual cutover | Cutover status |
| `staged_cutover` | ECMP weight adjustment (75/25→50/50→25/75→0/100) | Stage complete |
| `cleanup_tunnel` | Delete protection tunnel, release BSID | Cleaned |
| `return_restored` | Notify Orchestrator restoration complete | Response |

#### Hold Timer Configuration

```python
class HoldTimerManager:
    """
    Manage hold timers per incident/service.
    Hold timer prevents premature cutover after SLA recovery.
    """

    def start_timer(
        self,
        incident_id: str,
        sla_tier: str,
        recovery_time: datetime
    ) -> str:
        """Start hold timer, return timer ID"""
        hold_seconds = SLA_TIER_CONFIG[sla_tier]["hold_timer_seconds"]
        expiry = recovery_time + timedelta(seconds=hold_seconds)

        timer_id = f"timer:{incident_id}"
        redis.zadd("restoration:timers", {timer_id: expiry.timestamp()})
        redis.hset(timer_id, mapping={
            "incident_id": incident_id,
            "sla_tier": sla_tier,
            "recovery_time": recovery_time.isoformat(),
            "expiry_time": expiry.isoformat(),
            "status": "waiting"
        })
        return timer_id

    def check_timer(self, timer_id: str) -> bool:
        """Check if hold timer has expired"""
        expiry = redis.hget(timer_id, "expiry_time")
        return datetime.now() >= datetime.fromisoformat(expiry)

    def cancel_timer(self, timer_id: str):
        """Cancel timer (SLA degraded again during hold)"""
        redis.hset(timer_id, "status", "cancelled")
        redis.zrem("restoration:timers", timer_id)
```

#### Gradual Cutover (Weighted ECMP)

```python
class GradualCutover:
    """
    Staged traffic migration using weighted ECMP.
    Protection tunnel weight decreases as original path weight increases.
    """

    STAGES = [
        {"protection": 75, "original": 25},
        {"protection": 50, "original": 50},
        {"protection": 25, "original": 75},
        {"protection": 0,  "original": 100},  # Final: all on original
    ]
    STAGE_INTERVAL_SECONDS = 60  # Wait between stages

    async def execute_gradual_cutover(
        self,
        incident_id: str,
        protection_tunnel_id: str,
        original_path_id: str
    ) -> bool:
        """Execute staged cutover with monitoring"""
        for stage_idx, weights in enumerate(self.STAGES):
            # Update ECMP weights via CNC
            await self.update_weights(
                protection_tunnel_id,
                original_path_id,
                weights
            )

            # Store stage progress
            redis.hset(f"cutover:{incident_id}", mapping={
                "stage": stage_idx,
                "protection_weight": weights["protection"],
                "original_weight": weights["original"],
                "updated_at": datetime.now().isoformat()
            })

            # Wait and verify SLA still good
            await asyncio.sleep(self.STAGE_INTERVAL_SECONDS)

            if not await self.verify_sla_ok(original_path_id):
                # Rollback to previous stage
                return False

        return True
```

#### PCA SLA Query

```python
class PCASLAClient:
    """Query PCA for SLA metrics on a path"""

    async def get_path_sla(self, path_endpoints: tuple) -> SLAMetrics:
        """
        Query current SLA metrics between endpoints.

        GET /api/v1/metrics?source={src}&dest={dst}&window=5m
        """
        src, dst = path_endpoints
        response = await self.client.get(
            f"{self.pca_url}/api/v1/metrics",
            params={
                "source": src,
                "dest": dst,
                "window": "5m",  # 5-minute average
                "metrics": "latency,jitter,loss"
            }
        )
        return SLAMetrics(**response.json())

class SLAMetrics(BaseModel):
    latency_ms: float
    jitter_ms: float
    packet_loss_pct: float
    measurement_time: datetime

    def meets_threshold(self, thresholds: dict) -> bool:
        """Check if metrics meet SLA thresholds"""
        return (
            self.latency_ms <= thresholds.get("max_latency_ms", float("inf"))
            and self.jitter_ms <= thresholds.get("max_jitter_ms", float("inf"))
            and self.packet_loss_pct <= thresholds.get("max_loss_pct", float("inf"))
        )
```

#### Tools

```python
# Tool 1: Poll SLA
class PollSLAInput(BaseModel):
    source_pe: str
    dest_pe: str
    path_type: Literal["original", "protection"]

class PollSLAOutput(BaseModel):
    metrics: SLAMetrics
    meets_sla: bool

# Tool 2: Manage Hold Timer
class StartTimerInput(BaseModel):
    incident_id: str
    sla_tier: str

class CheckTimerInput(BaseModel):
    timer_id: str

class CheckTimerOutput(BaseModel):
    expired: bool
    remaining_seconds: int

# Tool 3: Update ECMP Weights
class UpdateWeightsInput(BaseModel):
    protection_tunnel_id: str
    original_path_id: str
    protection_weight: int  # 0-100
    original_weight: int    # 0-100

class UpdateWeightsOutput(BaseModel):
    success: bool
    message: str

# Tool 4: Delete Tunnel
class DeleteTunnelInput(BaseModel):
    tunnel_id: str
    tunnel_type: Literal["sr-policy", "rsvp-te"]

class DeleteTunnelOutput(BaseModel):
    success: bool
    bsid_released: Optional[int]
```

#### A2A Task Schema

```json
{
  "task_type": "monitor_restoration",
  "payload": {
    "incident_id": "INC-2026-0001",
    "protection_tunnel_id": "sr-policy-001",
    "original_path": {"source": "PE1", "dest": "PE2"},
    "sla_tier": "platinum",
    "cutover_mode": "immediate"
  }
}

// Response
{
  "task_type": "restoration_complete",
  "payload": {
    "incident_id": "INC-2026-0001",
    "restored": true,
    "hold_timer_seconds": 60,
    "cutover_mode": "immediate",
    "tunnel_deleted": true,
    "total_protection_duration_seconds": 180
  }
}
```

---

### Agent 7: Traffic Analytics Agent

**Purpose**: Builds traffic demand matrices, predicts congestion, and generates proactive alerts BEFORE SLA degradation occurs.

#### LangGraph Nodes

```
┌─────────────────────────────────────────────────────────────────────┐
│                   TRAFFIC ANALYTICS FLOW                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐                   │
│   │ COLLECT  │────▶│  BUILD   │────▶│ PREDICT  │                   │
│   │TELEMETRY │     │  MATRIX  │     │CONGESTION│                   │
│   └──────────┘     └──────────┘     └────┬─────┘                   │
│        │                                  │                         │
│   SR-PM, MDT                       [threshold check]                │
│   NetFlow                                 │                         │
│                              ┌────────────┴────────────┐           │
│                          [< 70%]                   [≥ 70%]         │
│                              │                         │            │
│                              ▼                         ▼            │
│                         ┌─────────┐             ┌─────────┐        │
│                         │  STORE  │             │ ANALYZE │        │
│                         │ METRICS │             │  RISK   │        │
│                         └─────────┘             └────┬────┘        │
│                                                      │              │
│                                               [risk level]          │
│                                                      │              │
│                              ┌────────────┬──────────┴──────────┐  │
│                          [low]        [medium]              [high] │
│                              │            │                     │   │
│                              ▼            ▼                     ▼   │
│                         ┌────────┐  ┌─────────┐          ┌────────┐│
│                         │  LOG   │  │  WARN   │          │PROACTIVE││
│                         │        │  │         │          │ ALERT  ││
│                         └────────┘  └─────────┘          └────────┘│
│                                                               │     │
│                                                               ▼     │
│                                                          ┌────────┐│
│                                                          │  EMIT  ││
│                                                          │INCIDENT││
│                                                          └────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Action | Output |
|------|--------|--------|
| `collect_telemetry` | Gather data from SR-PM, MDT, NetFlow | Raw telemetry |
| `build_matrix` | Compute PE-to-PE traffic demand matrix | Demand matrix |
| `predict_congestion` | Analyze link utilization vs capacity | Risk assessment |
| `analyze_risk` | Determine risk level and affected services | Risk report |
| `emit_proactive_alert` | Send PROACTIVE_ALERT to Orchestrator | Alert emitted |
| `store_metrics` | Store historical data for trending | Stored |
| `warn` | Log warning, update dashboards | Warning logged |

#### Telemetry Collectors

```python
class TelemetryCollector:
    """Unified telemetry collection for all TE types"""

    async def collect_all(self) -> TelemetryData:
        """Collect from all sources in parallel"""
        sr_pm, mdt, netflow = await asyncio.gather(
            self.collect_sr_pm(),
            self.collect_mdt(),
            self.collect_netflow()
        )
        return TelemetryData(sr_pm=sr_pm, mdt=mdt, netflow=netflow)

    async def collect_sr_pm(self) -> List[SRPMMetric]:
        """
        Collect SR Performance Measurement data.
        Provides per-path delay, loss, jitter.
        """
        # Query via CNC telemetry API or direct device streaming
        response = await self.cnc_client.get(
            "/crosswork/telemetry/v1/sr-pm/metrics",
            params={"window": "5m"}
        )
        return [SRPMMetric(**m) for m in response.json()["metrics"]]

    async def collect_mdt(self) -> List[InterfaceCounter]:
        """
        Collect Model-Driven Telemetry (interface counters).
        Provides bytes/packets per interface.
        """
        # gRPC streaming from network devices
        counters = []
        async for update in self.mdt_stream.subscribe("interfaces"):
            counters.append(InterfaceCounter(**update))
        return counters

    async def collect_netflow(self) -> List[FlowRecord]:
        """
        Collect NetFlow/IPFIX records.
        Provides per-flow traffic volumes with SRv6 SIDs.
        """
        # Query NetFlow collector
        response = await self.netflow_collector.get(
            "/api/v1/flows",
            params={"window": "5m", "include_srv6": True}
        )
        return [FlowRecord(**f) for f in response.json()["flows"]]
```

#### Demand Matrix Builder

```python
class DemandMatrixBuilder:
    """
    Build PE-to-PE traffic demand matrix.
    Works with SRv6, SR-MPLS, and RSVP-TE.
    """

    def build_matrix(self, telemetry: TelemetryData) -> DemandMatrix:
        """
        Aggregate telemetry into PE-to-PE demand matrix.

        Matrix[src_pe][dst_pe] = total_traffic_gbps
        """
        matrix = defaultdict(lambda: defaultdict(float))

        # SRv6: Use SRv6 locator counters (best visibility)
        for metric in telemetry.sr_pm:
            if metric.srv6_locator:
                src_pe = self.locator_to_pe(metric.source_locator)
                dst_pe = self.locator_to_pe(metric.dest_locator)
                matrix[src_pe][dst_pe] += metric.traffic_gbps

        # SR-MPLS: Use policy/BSID counters
        for metric in telemetry.sr_pm:
            if metric.sr_policy_bsid:
                src_pe = metric.headend
                dst_pe = metric.endpoint
                matrix[src_pe][dst_pe] += metric.traffic_gbps

        # NetFlow: Aggregate by source/dest PE
        for flow in telemetry.netflow:
            src_pe = self.ip_to_pe(flow.src_ip)
            dst_pe = self.ip_to_pe(flow.dst_ip)
            matrix[src_pe][dst_pe] += flow.bytes / 1e9 / 300  # 5-min to Gbps

        return DemandMatrix(matrix=dict(matrix), timestamp=datetime.now())

class DemandMatrix(BaseModel):
    """PE-to-PE traffic demand matrix"""
    matrix: dict[str, dict[str, float]]  # {src_pe: {dst_pe: gbps}}
    timestamp: datetime

    def get_demand(self, src: str, dst: str) -> float:
        return self.matrix.get(src, {}).get(dst, 0.0)

    def get_total_demand_through_link(self, link_id: str, topology: dict) -> float:
        """Calculate total demand flowing through a specific link"""
        total = 0.0
        for src_pe, destinations in self.matrix.items():
            for dst_pe, demand in destinations.items():
                if link_id in topology.get_path(src_pe, dst_pe):
                    total += demand
        return total
```

#### Congestion Prediction

```python
class CongestionPredictor:
    """
    Predict congestion based on demand matrix and link capacities.
    """

    UTILIZATION_THRESHOLD = 0.70  # 70% = warning
    CRITICAL_THRESHOLD = 0.85     # 85% = proactive alert

    async def predict(
        self,
        demand_matrix: DemandMatrix,
        topology: NetworkTopology
    ) -> List[CongestionRisk]:
        """
        Analyze each link for congestion risk.
        """
        risks = []

        for link in topology.links:
            # Get current utilization
            current_util = link.current_traffic_gbps / link.capacity_gbps

            # Get projected demand (from matrix)
            projected_demand = demand_matrix.get_total_demand_through_link(
                link.link_id, topology
            )
            projected_util = projected_demand / link.capacity_gbps

            # Assess risk
            if projected_util >= self.CRITICAL_THRESHOLD:
                risk_level = "high"
            elif projected_util >= self.UTILIZATION_THRESHOLD:
                risk_level = "medium"
            else:
                risk_level = "low"

            if risk_level != "low":
                risks.append(CongestionRisk(
                    link_id=link.link_id,
                    current_utilization=current_util,
                    projected_utilization=projected_util,
                    capacity_gbps=link.capacity_gbps,
                    risk_level=risk_level,
                    affected_pe_pairs=self.get_affected_pairs(link, demand_matrix)
                ))

        return sorted(risks, key=lambda r: r.projected_utilization, reverse=True)

class CongestionRisk(BaseModel):
    link_id: str
    current_utilization: float
    projected_utilization: float
    capacity_gbps: float
    risk_level: Literal["low", "medium", "high"]
    affected_pe_pairs: List[tuple[str, str]]
```

#### Proactive Alert Schema

```python
class ProactiveAlert(BaseModel):
    """
    Alert generated BEFORE SLA degradation.
    Triggers same protection workflow as reactive alerts.
    """
    alert_type: Literal["proactive"] = "proactive"
    alert_id: str
    timestamp: datetime

    # Predicted congestion
    at_risk_links: List[str]
    predicted_utilization: float
    time_to_congestion_minutes: Optional[int]

    # Services that will be affected
    at_risk_services: List[str]
    highest_sla_tier: str

    # Recommendation
    recommended_action: Literal["pre_provision_tunnel", "load_balance", "alert_only"]
```

#### Tools

```python
# Tool 1: Collect Telemetry
class CollectTelemetryInput(BaseModel):
    sources: List[Literal["sr-pm", "mdt", "netflow"]]
    window_minutes: int = 5

class CollectTelemetryOutput(BaseModel):
    telemetry: TelemetryData
    collection_time_ms: int

# Tool 2: Build Demand Matrix
class BuildMatrixInput(BaseModel):
    telemetry: TelemetryData

class BuildMatrixOutput(BaseModel):
    matrix: DemandMatrix
    pe_count: int
    total_demand_gbps: float

# Tool 3: Predict Congestion
class PredictCongestionInput(BaseModel):
    demand_matrix: DemandMatrix

class PredictCongestionOutput(BaseModel):
    risks: List[CongestionRisk]
    high_risk_count: int
    medium_risk_count: int

# Tool 4: Emit Proactive Alert
class EmitProactiveAlertInput(BaseModel):
    risks: List[CongestionRisk]

class EmitProactiveAlertOutput(BaseModel):
    alert_id: str
    sent_to_orchestrator: bool
```

#### A2A Task Schema

```json
// Outbound to Orchestrator (proactive alert)
{
  "task_type": "proactive_alert",
  "payload": {
    "alert_id": "PROACTIVE-2026-0001",
    "at_risk_links": ["link-005"],
    "predicted_utilization": 0.82,
    "time_to_congestion_minutes": 15,
    "at_risk_services": ["svc-001", "svc-002"],
    "highest_sla_tier": "gold",
    "recommended_action": "pre_provision_tunnel"
  }
}
```

---

### Agent 8: Notification Agent

**Purpose**: Sends notifications to appropriate channels (Webex, ServiceNow, Email) based on incident severity and service SLA tier.

#### LangGraph Nodes

```
┌─────────────────────────────────────────────────────────┐
│               NOTIFICATION FLOW                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐       │
│   │  SELECT  │────▶│  FORMAT  │────▶│  SEND    │       │
│   │ CHANNELS │     │ MESSAGE  │     │ PARALLEL │       │
│   └──────────┘     └──────────┘     └────┬─────┘       │
│        │                                  │             │
│   Based on                          [per channel]      │
│   SLA tier                               │             │
│                              ┌───────────┼───────────┐ │
│                              │           │           │ │
│                              ▼           ▼           ▼ │
│                         ┌────────┐ ┌─────────┐ ┌──────┐│
│                         │ WEBEX  │ │ SNOW    │ │EMAIL ││
│                         └────────┘ └─────────┘ └──────┘│
│                              │           │           │ │
│                              └───────────┼───────────┘ │
│                                          │             │
│                                          ▼             │
│                                     ┌─────────┐        │
│                                     │  LOG    │        │
│                                     │ RESULTS │        │
│                                     └─────────┘        │
└─────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Action | Output |
|------|--------|--------|
| `select_channels` | Determine channels based on SLA tier | Channel list |
| `format_message` | Generate message from template | Formatted message |
| `send_parallel` | Send to all channels concurrently | Send results |
| `send_webex` | Post to Webex space | Success/Failure |
| `send_servicenow` | Create/update ServiceNow incident | Ticket ID |
| `send_email` | Send email via SMTP | Sent/Failed |
| `log_results` | Record notification outcomes | Logged |

#### Channel Selection Logic

```python
def select_channels(sla_tier: str, event_type: str) -> List[str]:
    """
    Select notification channels based on SLA tier and event type.
    """
    base_channels = SLA_TIER_CONFIG[sla_tier]["notification_channels"]

    # Add ServiceNow for incidents (not for info)
    if event_type in ["incident_detected", "escalation"]:
        if "servicenow" not in base_channels:
            base_channels.append("servicenow")

    return base_channels
```

#### Message Templates

```python
NOTIFICATION_TEMPLATES = {
    "incident_detected": {
        "subject": "[{severity}] SLA Degradation Detected - {incident_id}",
        "body": """
## Incident: {incident_id}

**Severity:** {severity}
**Time:** {timestamp}

### Affected Links
{degraded_links}

### Affected Services ({service_count} total)
| Service | Customer | SLA Tier |
|---------|----------|----------|
{service_table}

### Status
Protection workflow initiated. Monitoring for alternate path computation.

---
*Automated alert from Customer Experience Management System*
"""
    },

    "protection_active": {
        "subject": "[INFO] Protection Tunnel Active - {incident_id}",
        "body": """
## Protection Active: {incident_id}

**Tunnel ID:** {tunnel_id}
**Type:** {te_type}
**BSID:** {binding_sid}

### Protected Services
{protected_services}

Traffic is now flowing via protection path. Monitoring for SLA recovery.
"""
    },

    "restoration_complete": {
        "subject": "[RESOLVED] Service Restored - {incident_id}",
        "body": """
## Incident Resolved: {incident_id}

**Duration:** {duration_minutes} minutes
**Cutover Mode:** {cutover_mode}

All affected services have been restored to original paths.
Protection tunnel has been removed.

### Summary
- Services affected: {service_count}
- Protection tunnel: {tunnel_id} (deleted)
- Total protection time: {protection_duration}
"""
    },

    "escalation": {
        "subject": "[ESCALATION] Manual Intervention Required - {incident_id}",
        "body": """
## ESCALATION: {incident_id}

**Reason:** {escalation_reason}
**Time:** {timestamp}

### Context
{context}

### Recommended Actions
{recommendations}

**Immediate attention required.**
"""
    }
}
```

#### Channel Clients

```python
class WebexClient:
    """Webex Teams notification client"""

    async def send_message(
        self,
        space_id: str,
        message: str,
        markdown: bool = True
    ) -> bool:
        response = await self.client.post(
            "https://webexapis.com/v1/messages",
            headers={"Authorization": f"Bearer {self.token}"},
            json={
                "roomId": space_id,
                "markdown": message if markdown else None,
                "text": message if not markdown else None
            }
        )
        return response.status_code == 200

class ServiceNowClient:
    """ServiceNow incident management client"""

    async def create_incident(
        self,
        short_description: str,
        description: str,
        severity: int,  # 1=Critical, 2=High, 3=Medium
        assignment_group: str
    ) -> str:
        response = await self.client.post(
            f"{self.instance_url}/api/now/table/incident",
            auth=(self.username, self.password),
            json={
                "short_description": short_description,
                "description": description,
                "impact": severity,
                "urgency": severity,
                "assignment_group": assignment_group,
                "category": "Network",
                "subcategory": "Traffic Engineering"
            }
        )
        return response.json()["result"]["number"]  # INC0001234

    async def update_incident(
        self,
        incident_number: str,
        work_notes: str,
        state: Optional[int] = None  # 6=Resolved, 7=Closed
    ) -> bool:
        # Get sys_id from incident number
        # Update incident
        pass

class EmailClient:
    """Email notification client via SMTP"""

    async def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        html: bool = False
    ) -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(to)

        if html:
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))

        async with aiosmtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            await server.send_message(msg)
        return True
```

#### Tools

```python
# Tool 1: Send Webex
class SendWebexInput(BaseModel):
    space_id: str
    message: str
    markdown: bool = True

class SendWebexOutput(BaseModel):
    success: bool
    message_id: Optional[str]

# Tool 2: Create ServiceNow Incident
class CreateSNOWIncidentInput(BaseModel):
    short_description: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]
    assignment_group: str

class CreateSNOWIncidentOutput(BaseModel):
    success: bool
    incident_number: Optional[str]  # INC0001234

# Tool 3: Send Email
class SendEmailInput(BaseModel):
    recipients: List[str]
    subject: str
    body: str
    html: bool = False

class SendEmailOutput(BaseModel):
    success: bool
    sent_to: List[str]
```

#### A2A Task Schema

```json
{
  "task_type": "send_notification",
  "payload": {
    "incident_id": "INC-2026-0001",
    "event_type": "incident_detected",
    "severity": "critical",
    "sla_tier": "platinum",
    "data": {
      "degraded_links": ["link-001"],
      "service_count": 5,
      "affected_services": [ ... ]
    }
  }
}

// Response
{
  "task_type": "notification_sent",
  "payload": {
    "incident_id": "INC-2026-0001",
    "channels_attempted": ["webex", "servicenow", "email"],
    "channels_succeeded": ["webex", "servicenow", "email"],
    "servicenow_ticket": "INC0012345"
  }
}
```

---

### Agent 9: Audit Agent

**Purpose**: Captures all workflow events, decisions, and state changes for compliance logging and post-incident analysis.

#### LangGraph Nodes

```
┌─────────────────────────────────────────────────────────┐
│                    AUDIT FLOW                            │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐       │
│   │ CAPTURE  │────▶│  FORMAT  │────▶│  STORE   │       │
│   │  EVENT   │     │   LOG    │     │   DB     │       │
│   └──────────┘     └──────────┘     └────┬─────┘       │
│        │                                  │             │
│   From all                           PostgreSQL        │
│   agents                                  │             │
│                                          ▼             │
│                                     ┌─────────┐        │
│                                     │  INDEX  │        │
│                                     │ (async) │        │
│                                     └─────────┘        │
└─────────────────────────────────────────────────────────┘
```

#### Node Definitions

| Node | Action | Output |
|------|--------|--------|
| `capture_event` | Receive event from any agent | Raw event |
| `format_log` | Standardize into audit log format | Formatted log |
| `store_db` | Write to PostgreSQL (sync for durability) | Stored |
| `index_async` | Update search indices (Elasticsearch) | Indexed |

#### Audit Event Schema

```python
class AuditEvent(BaseModel):
    """Standard audit event for all workflow activities"""

    # Event identification
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Context
    incident_id: Optional[str]
    agent_name: str
    node_name: str

    # Event details
    event_type: Literal[
        "incident_created",
        "alert_correlated",
        "service_impact_assessed",
        "path_computed",
        "tunnel_provisioned",
        "traffic_steered",
        "sla_recovered",
        "restoration_complete",
        "escalation",
        "notification_sent",
        "error",
        "state_change"
    ]

    # Payload
    payload: dict  # Event-specific data

    # State change (if applicable)
    previous_state: Optional[str]
    new_state: Optional[str]

    # Decision tracking (for compliance)
    decision_type: Optional[Literal["rule_based", "llm_assisted", "human"]]
    decision_reasoning: Optional[str]

    # Actor
    actor: str = "system"  # or user ID for manual actions

class AuditLog(BaseModel):
    """Collection of audit events for an incident"""
    incident_id: str
    events: List[AuditEvent]
    started_at: datetime
    completed_at: Optional[datetime]
    final_status: Optional[str]
```

#### PostgreSQL Schema

```sql
-- Audit events table
CREATE TABLE audit_events (
    event_id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    incident_id VARCHAR(50),
    agent_name VARCHAR(50) NOT NULL,
    node_name VARCHAR(50),
    event_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    previous_state VARCHAR(50),
    new_state VARCHAR(50),
    decision_type VARCHAR(20),
    decision_reasoning TEXT,
    actor VARCHAR(100) DEFAULT 'system',

    -- Indexes for common queries
    CONSTRAINT fk_incident FOREIGN KEY (incident_id)
        REFERENCES incidents(incident_id)
);

CREATE INDEX idx_audit_incident ON audit_events(incident_id);
CREATE INDEX idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX idx_audit_event_type ON audit_events(event_type);
CREATE INDEX idx_audit_agent ON audit_events(agent_name);

-- Incidents summary table
CREATE TABLE incidents (
    incident_id VARCHAR(50) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL,
    severity VARCHAR(20),
    degraded_links JSONB,
    affected_services JSONB,
    protection_tunnel_id VARCHAR(100),
    total_duration_seconds INTEGER,
    final_outcome VARCHAR(50)
);

-- Compliance report view
CREATE VIEW compliance_report AS
SELECT
    i.incident_id,
    i.created_at,
    i.closed_at,
    i.severity,
    i.total_duration_seconds,
    i.final_outcome,
    COUNT(e.event_id) as event_count,
    COUNT(CASE WHEN e.decision_type = 'llm_assisted' THEN 1 END) as llm_decisions,
    COUNT(CASE WHEN e.event_type = 'error' THEN 1 END) as error_count
FROM incidents i
LEFT JOIN audit_events e ON i.incident_id = e.incident_id
GROUP BY i.incident_id;
```

#### Audit Client

```python
class AuditClient:
    """Client for writing audit events from any agent"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.db = PostgreSQLClient()

    async def log_event(
        self,
        event_type: str,
        payload: dict,
        incident_id: Optional[str] = None,
        node_name: Optional[str] = None,
        previous_state: Optional[str] = None,
        new_state: Optional[str] = None,
        decision_type: Optional[str] = None,
        decision_reasoning: Optional[str] = None
    ):
        """Log an audit event"""
        event = AuditEvent(
            incident_id=incident_id,
            agent_name=self.agent_name,
            node_name=node_name,
            event_type=event_type,
            payload=payload,
            previous_state=previous_state,
            new_state=new_state,
            decision_type=decision_type,
            decision_reasoning=decision_reasoning
        )

        # Write to PostgreSQL (sync for durability)
        await self.db.insert("audit_events", event.dict())

        # Async index to Elasticsearch (for search)
        asyncio.create_task(self.index_event(event))

        return event.event_id

    async def get_incident_timeline(self, incident_id: str) -> List[AuditEvent]:
        """Get chronological timeline of all events for an incident"""
        rows = await self.db.query(
            "SELECT * FROM audit_events WHERE incident_id = %s ORDER BY timestamp",
            [incident_id]
        )
        return [AuditEvent(**row) for row in rows]
```

#### Tools

```python
# Tool 1: Log Audit Event
class LogAuditEventInput(BaseModel):
    event_type: str
    payload: dict
    incident_id: Optional[str]
    previous_state: Optional[str]
    new_state: Optional[str]
    decision_type: Optional[str]
    decision_reasoning: Optional[str]

class LogAuditEventOutput(BaseModel):
    event_id: str
    stored: bool

# Tool 2: Get Incident Timeline
class GetTimelineInput(BaseModel):
    incident_id: str

class GetTimelineOutput(BaseModel):
    events: List[AuditEvent]
    event_count: int

# Tool 3: Generate Compliance Report
class GenerateReportInput(BaseModel):
    start_date: datetime
    end_date: datetime
    include_llm_decisions: bool = True

class GenerateReportOutput(BaseModel):
    report: dict
    incident_count: int
    avg_resolution_time_seconds: float
```

#### A2A Task Schema

```json
{
  "task_type": "log_event",
  "payload": {
    "incident_id": "INC-2026-0001",
    "event_type": "tunnel_provisioned",
    "data": {
      "tunnel_id": "sr-policy-001",
      "te_type": "sr-mpls",
      "binding_sid": 24001
    },
    "previous_state": "computing",
    "new_state": "provisioning"
  }
}

// Response
{
  "task_type": "event_logged",
  "payload": {
    "event_id": "evt-123-456",
    "stored": true
  }
}
```

---

## Research Sources

- [Cisco CNC DevNet](https://developer.cisco.com/docs/crosswork/)
- [CNC Service Health Guide](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/crosswork-network-controller/7-1/ServiceHealthGuide/)
- [Cisco PCA (Accedian)](https://www.cisco.com/c/en/us/products/collateral/cloud-systems-management/provider-connectivity-assurance/provider-connect-assurance-ds.html)
- [PCA API](https://api.accedian.io/)
- [A2A Protocol](https://github.com/a2aproject/A2A)
- [LangGraph Multi-Agent](https://docs.langchain.com/oss/python/langchain/multi-agent)
- [RFC 9603 - PCEP SRv6](https://www.rfc-editor.org/rfc/rfc9603.html)
