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

## Research Sources

- [Cisco CNC DevNet](https://developer.cisco.com/docs/crosswork/)
- [CNC Service Health Guide](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/crosswork-network-controller/7-1/ServiceHealthGuide/)
- [Cisco PCA (Accedian)](https://www.cisco.com/c/en/us/products/collateral/cloud-systems-management/provider-connectivity-assurance/provider-connect-assurance-ds.html)
- [PCA API](https://api.accedian.io/)
- [A2A Protocol](https://github.com/a2aproject/A2A)
- [LangGraph Multi-Agent](https://docs.langchain.com/oss/python/langchain/multi-agent)
- [RFC 9603 - PCEP SRv6](https://www.rfc-editor.org/rfc/rfc9603.html)
