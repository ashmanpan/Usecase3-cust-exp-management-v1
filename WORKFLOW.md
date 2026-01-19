# Customer Experience Management - Workflow Documentation

## Overview

This document describes the end-to-end ticket/incident flow through the multi-agent system, including IO Agent notifications for human UI updates.

---

## System Architecture

```
                              ┌─────────────────────────────────────┐
                              │           IO AGENT (8009)           │
                              │         Human UI Interface          │
                              │  • Displays tickets & updates       │
                              │  • Real-time status notifications   │
                              └─────────────────┬───────────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
            ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
            │ new_ticket   │           │status_update │           │ticket_closed │
            └──────────────┘           └──────────────┘           └──────────────┘
                    ▲                           ▲                           ▲
                    │                           │                           │
┌───────────────────┴───────────────────────────┴───────────────────────────┴───┐
│                                                                                │
│                         AGENT ECOSYSTEM                                        │
│                                                                                │
│   ┌─────────────────────────────────────────────────────────────────────────┐ │
│   │                      ORCHESTRATOR (8000)                                 │ │
│   │                    Supervisor / State Machine                            │ │
│   └─────────────────────────────────┬───────────────────────────────────────┘ │
│                                     │                                          │
│     ┌───────────┬───────────┬───────┼───────┬───────────┬───────────┐        │
│     ▼           ▼           ▼       ▼       ▼           ▼           ▼        │
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐│
│ │ Event  │ │Service │ │  Path  │ │ Tunnel │ │Restore │ │Traffic │ │ Audit  ││
│ │Correlate│ │Impact │ │Compute │ │Provision│ │Monitor │ │Analytics│ │        ││
│ │ (8001) │ │ (8002) │ │ (8003) │ │ (8004) │ │ (8005) │ │ (8006) │ │ (8008) ││
│ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘│
│                                                                                │
│                           ┌────────┐                                          │
│                           │Notify  │                                          │
│                           │ (8007) │                                          │
│                           └────────┘                                          │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Port Assignments

| Port | Agent | Responsibility |
|------|-------|----------------|
| 8000 | Orchestrator | Supervisor, state machine, workflow coordination |
| 8001 | Event Correlator | Alert correlation, dedup, flap detection |
| 8002 | Service Impact | CNC Service Health, affected services |
| 8003 | Path Computation | Knowledge Graph Dijkstra, constraint routing |
| 8004 | Tunnel Provisioning | CNC PCE, SR-MPLS/SRv6/RSVP-TE tunnels |
| 8005 | Restoration Monitor | SLA recovery, hold timers, gradual cutover |
| 8006 | Traffic Analytics | Demand matrix, congestion prediction |
| 8007 | Notification | Webex, ServiceNow, Email channels |
| 8008 | Audit | PostgreSQL logging, compliance reports |
| 8009 | IO Agent | Human UI interface (external) |

---

## Complete Ticket Flow

### Phase 0: Alert Ingestion

```
┌─────────────────────────────────────────────────────────────────┐
│                     ALERT SOURCES                                │
│                                                                  │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │    PCA Alert     │              │    CNC Alarm     │         │
│  │  (latency/loss)  │              │   (threshold)    │         │
│  └────────┬─────────┘              └────────┬─────────┘         │
│           │                                  │                   │
│           └──────────────┬───────────────────┘                   │
│                          │                                       │
│                          ▼                                       │
│                   Webhook / API                                  │
└──────────────────────────┼───────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  EVENT CORRELATOR      │
              │      (Port 8001)       │
              └────────────────────────┘
```

**Trigger Sources:**
- **PCA (Performance Collection Agent)**: Detects latency, jitter, packet loss exceeding thresholds
- **CNC (Crosswork Network Controller)**: Alarm when SLA metrics degrade
- **Traffic Analytics (Proactive)**: Predicts congestion before SLA degrades

---

### Phase 1: Event Correlation & Ticket Creation

```
┌─────────────────────────────────────────────────────────────────┐
│                  EVENT CORRELATOR (8001)                         │
│                                                                  │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐                │
│  │  INGEST  │────▶│  DEDUP   │────▶│CORRELATE │                │
│  │  ALERT   │     │  CHECK   │     │  ALERTS  │                │
│  └──────────┘     └──────────┘     └────┬─────┘                │
│                                         │                       │
│                        ┌────────────────┼────────────────┐      │
│                        ▼                ▼                ▼      │
│                 ┌──────────┐     ┌──────────┐     ┌──────────┐ │
│                 │   FLAP   │     │ SUPPRESS │     │  DISCARD │ │
│                 │  DETECT  │     │          │     │          │ │
│                 └────┬─────┘     └──────────┘     └──────────┘ │
│                      │                                          │
│                      ▼                                          │
│                ┌───────────┐                                    │
│                │   EMIT    │────────────────────────────────────┼──▶ IO Agent
│                │ INCIDENT  │                                    │    new_ticket
│                └─────┬─────┘                                    │
└──────────────────────┼──────────────────────────────────────────┘
                       │
                       ▼
              ┌────────────────────┐
              │    ORCHESTRATOR    │
              │     (Port 8000)    │
              └────────────────────┘
```

**IO Agent Notification: `new_ticket`**
```json
{
  "task_type": "new_ticket",
  "payload": {
    "incident_id": "INC-2026-0001",
    "severity": "high",
    "summary": "SLA degradation detected on pe1-pe2, pe2-pe3",
    "degraded_links": ["pe1-pe2", "pe2-pe3"],
    "affected_services": [],
    "source_agent": "event_correlator",
    "created_at": "2026-01-19T10:30:00Z",
    "status": "new"
  }
}
```

---

### Phase 2: Service Impact Assessment

```
┌─────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (8000)                            │
│                                                                  │
│  ┌──────────┐                                                   │
│  │  DETECT  │──────────────────────────────────────────────────┼──▶ IO Agent
│  │  NODE    │                                                   │    status_update
│  └────┬─────┘                                                   │    "Phase 1"
│       │                                                         │
│       ▼                                                         │
│  ┌──────────┐     A2A Call      ┌──────────────────────────┐   │
│  │  ASSESS  │─────────────────▶│   SERVICE IMPACT (8002)   │   │
│  │  NODE    │                   │                           │   │
│  └────┬─────┘◀──────────────────│  • Query CNC Service API  │   │
│       │         Response        │  • Find affected VPNs     │   │
│       │                         │  • Get SLA tiers          │   │
│       │                         └──────────────────────────┘   │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Result: affected_services[], services_by_tier          │───┼──▶ IO Agent
│  └─────────────────────────────────────────────────────────┘   │    status_update
│                                                                  │    "Phase 2"
└──────────────────────────────────────────────────────────────────┘
```

**IO Agent Notification: `status_update`**
```json
{
  "task_type": "status_update",
  "payload": {
    "incident_id": "INC-2026-0001",
    "status": "assessing",
    "phase": "2",
    "message": "15 services affected, computing alternate path",
    "details": {
      "total_affected": 15,
      "services_by_tier": {"platinum": 2, "gold": 5, "silver": 8}
    },
    "source_agent": "orchestrator",
    "updated_at": "2026-01-19T10:30:15Z"
  }
}
```

---

### Phase 3: Alternate Path Computation

```
┌─────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (8000)                            │
│                                                                  │
│  ┌──────────┐     A2A Call      ┌──────────────────────────┐   │
│  │ COMPUTE  │─────────────────▶│  PATH COMPUTATION (8003)  │   │
│  │  NODE    │                   │                           │   │
│  └────┬─────┘◀──────────────────│  • Query Knowledge Graph  │   │
│       │         Response        │  • Dijkstra with avoid    │   │
│       │                         │  • Return alternate path  │   │
│       │                         └──────────────────────────┘   │
│       │                                                         │
│       ├─── Path Found ──────────────────────────────────────────┼──▶ IO Agent
│       │                                                         │    status_update
│       │                                                         │    "Phase 3"
│       │                                                         │
│       └─── No Path ─────────────────────────────────────────────┼──▶ IO Agent
│                                                                  │    status_update
│                                                                  │    "Escalated"
└──────────────────────────────────────────────────────────────────┘
```

**IO Agent Notification: `status_update` (Path Found)**
```json
{
  "task_type": "status_update",
  "payload": {
    "incident_id": "INC-2026-0001",
    "status": "computing",
    "phase": "3",
    "message": "Alternate path found (sr-mpls), provisioning tunnel",
    "details": {
      "path_type": "sr-mpls",
      "hop_count": 4
    },
    "source_agent": "orchestrator",
    "updated_at": "2026-01-19T10:30:30Z"
  }
}
```

---

### Phase 4: Protection Tunnel Provisioning

```
┌─────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (8000)                            │
│                                                                  │
│  ┌──────────┐     A2A Call      ┌──────────────────────────┐   │
│  │PROVISION │─────────────────▶│ TUNNEL PROVISIONING (8004)│   │
│  │  NODE    │                   │                           │   │
│  └────┬─────┘◀──────────────────│  • Auto-detect TE type    │   │
│       │         Response        │  • Call CNC PCE API       │   │
│       │                         │  • Allocate Binding SID   │   │
│       │                         │  • Create SR Policy       │   │
│       │                         └──────────────────────────┘   │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Result: tunnel_id, binding_sid, te_type                │───┼──▶ IO Agent
│  └─────────────────────────────────────────────────────────┘   │    status_update
│                                                                  │    "Phase 4"
└──────────────────────────────────────────────────────────────────┘
```

**IO Agent Notification: `status_update`**
```json
{
  "task_type": "status_update",
  "payload": {
    "incident_id": "INC-2026-0001",
    "status": "provisioning",
    "phase": "4",
    "message": "Protection tunnel created (sr-mpls), steering traffic",
    "details": {
      "tunnel_id": "sr-policy-pe1-pe4-protect-001",
      "binding_sid": 24001,
      "te_type": "sr-mpls"
    },
    "source_agent": "orchestrator",
    "updated_at": "2026-01-19T10:30:45Z"
  }
}
```

---

### Phase 5: Traffic Steering

```
┌─────────────────────────────────────────────────────────────────┐
│                TUNNEL PROVISIONING (8004)                        │
│                                                                  │
│  ┌──────────┐                                                   │
│  │  STEER   │  • Apply SR Policy to head-end                    │
│  │ TRAFFIC  │  • Traffic flows through protection tunnel        │
│  │  NODE    │  • Original path still exists (for fallback)      │
│  └────┬─────┘                                                   │
│       │                                                         │
│       ▼                                                         │
│  Result: traffic_steered = true                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

### Phase 6: Continuous Monitoring

```
┌─────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (8000)                            │
│                                                                  │
│  ┌──────────┐     A2A Call      ┌──────────────────────────┐   │
│  │ MONITOR  │─────────────────▶│ RESTORATION MONITOR (8005)│   │
│  │  NODE    │                   │                           │   │
│  └────┬─────┘◀──────────────────│  • Poll PCA for SLA      │   │
│       │         Response        │  • Check recovery status  │   │
│       │                         │  • Manage hold timers     │   │
│       │                         └──────────────────────────┘   │
│       │                                                         │
│       ├─── SLA Recovered ───────────────────────────────────────┼──▶ IO Agent
│       │    (Hold Timer)                                         │    status_update
│       │                                                         │    "Phase 6"
│       │                                                         │
│       └─── Still Degraded ──▶ Continue Polling                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Hold Timer by SLA Tier:**
| Tier | Hold Time | Description |
|------|-----------|-------------|
| Platinum | 30 seconds | Fastest recovery |
| Gold | 60 seconds | Standard |
| Silver | 120 seconds | Extended |
| Bronze | 300 seconds | Maximum |

---

### Phase 7: Restoration & Cleanup

```
┌─────────────────────────────────────────────────────────────────┐
│               RESTORATION MONITOR (8005)                         │
│                                                                  │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐                │
│  │  VERIFY  │────▶│ CUTOVER  │────▶│ CLEANUP  │                │
│  │ STABILITY│     │ TRAFFIC  │     │  TUNNEL  │                │
│  └──────────┘     └────┬─────┘     └──────────┘                │
│                        │                                        │
│                        ▼                                        │
│           ┌────────────────────────┐                           │
│           │   Gradual Cutover      │                           │
│           │   75/25 → 50/50 →      │                           │
│           │   25/75 → 0/100        │                           │
│           └────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (8000)                            │
│                                                                  │
│  ┌──────────┐                                                   │
│  │  CLOSE   │───────────────────────────────────────────────────┼──▶ IO Agent
│  │  NODE    │                                                   │    ticket_closed
│  └──────────┘                                                   │
│       │                                                         │
│       ├──▶ Notification Agent (8007): Send closure alerts       │
│       └──▶ Audit Agent (8008): Log final event                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**IO Agent Notification: `ticket_closed`**
```json
{
  "task_type": "ticket_closed",
  "payload": {
    "incident_id": "INC-2026-0001",
    "resolution": "resolved",
    "duration_seconds": 245,
    "summary": "Incident resolved: SLA recovered on original path",
    "details": {
      "final_status": "resolved",
      "close_reason": "sla_recovered",
      "degraded_links": ["pe1-pe2", "pe2-pe3"],
      "affected_services_count": 15,
      "tunnel_id": "sr-policy-pe1-pe4-protect-001",
      "nodes_executed": ["start", "detect", "assess", "compute", "provision", "steer", "monitor", "restore", "close"]
    },
    "source_agent": "orchestrator",
    "closed_at": "2026-01-19T10:34:05Z"
  }
}
```

---

## IO Agent Integration

### Task Types

| Task Type | When Sent | Source Agent |
|-----------|-----------|--------------|
| `new_ticket` | New incident created | Event Correlator |
| `status_update` | Each phase transition | Orchestrator |
| `ticket_closed` | Incident resolved | Orchestrator |
| `error` | Error during workflow | Any Agent |

### Configuration

```bash
# Environment variables
export IO_AGENT_URL=http://io-agent:8009
export IO_AGENT_ENABLED=true
```

### A2A Endpoints

The IO Agent should expose:

```
POST /a2a/tasks          # Receive task (new_ticket, status_update, ticket_closed)
GET  /health             # Health check
GET  /.well-known/agent.json  # Agent card (capabilities)
```

---

## State Diagram

```
                                    ┌─────────────────┐
                                    │                 │
                                    │    DETECTING    │◀─── Alert Received
                                    │    (Phase 1)    │
                                    │                 │
                                    └────────┬────────┘
                                             │
                           ┌─────────────────┼─────────────────┐
                           │                 │                 │
                           ▼                 ▼                 ▼
                    ┌──────────┐      ┌──────────┐      ┌──────────┐
                    │DAMPENING │      │ASSESSING │      │  CLOSED  │
                    │  (Flap)  │      │(Phase 2) │      │(No Impact)│
                    └────┬─────┘      └────┬─────┘      └──────────┘
                         │                 │
                         │                 ▼
                         │          ┌──────────┐
                         │          │COMPUTING │
                         │          │(Phase 3) │
                         │          └────┬─────┘
                         │               │
                         │    ┌──────────┼──────────┐
                         │    │          │          │
                         │    ▼          ▼          ▼
                         │ ┌──────┐ ┌──────────┐ ┌──────────┐
                         │ │ESCAL-│ │PROVISION-│ │  CLOSED  │
                         │ │ATED  │ │ING (P4)  │ │(No Path) │
                         │ └──────┘ └────┬─────┘ └──────────┘
                         │               │
                         │               ▼
                         │        ┌──────────┐
                         │        │ STEERING │
                         │        │(Phase 5) │
                         │        └────┬─────┘
                         │               │
                         │               ▼
                         │        ┌──────────┐
                         └───────▶│MONITORING│
                                  │(Phase 6) │
                                  └────┬─────┘
                                       │
                                       ▼
                                ┌──────────┐
                                │RESTORING │
                                │(Phase 7) │
                                └────┬─────┘
                                     │
                                     ▼
                                ┌──────────┐
                                │  CLOSED  │
                                │(Resolved)│
                                └──────────┘
```

---

## Proactive vs Reactive Flow

### Reactive Flow (Default)
```
PCA Alert ──▶ SLA Already Degraded ──▶ Find Alternate ──▶ Provision Tunnel
```
- Triggered **after** SLA degradation occurs
- Customer may experience brief service impact

### Proactive Flow (Traffic Analytics)
```
Traffic Analytics ──▶ Predict Congestion (70%+) ──▶ Pre-provision ──▶ Shift Traffic
```
- Triggered **before** SLA degrades
- Zero customer impact
- Enabled by Traffic Analytics Agent (8006)

---

## Error Handling

| Scenario | Action | IO Agent Update |
|----------|--------|-----------------|
| No alternate path | Escalate to operator | `status_update` (Escalated) |
| Tunnel provision failed (3x) | Escalate to operator | `error` notification |
| Flapping link | Dampen with exponential backoff | `status_update` (Dampening) |
| Service Impact API failed | Escalate | `error` notification |
| Hold timer expired | Re-verify SLA | `status_update` |

---

## Notification Channels (Phase Close)

| Severity | Webex | ServiceNow | Email |
|----------|-------|------------|-------|
| Critical/Platinum | ✅ | ✅ | ✅ |
| High/Gold | ✅ | ✅ | ✅ |
| Medium/Silver | ✅ | ❌ | ✅ |
| Low/Bronze | ❌ | ❌ | ✅ |

---

## Audit Trail

All events are logged to:
- **PostgreSQL** (sync, durable): Primary audit storage
- **Elasticsearch** (async, optional): Search and analytics

Event types logged:
- `incident_created`
- `alert_correlated`
- `service_impact_assessed`
- `path_computed`
- `tunnel_provisioned`
- `traffic_steered`
- `sla_recovered`
- `restoration_complete`
- `escalation`
- `notification_sent`
- `error`
- `state_change`
