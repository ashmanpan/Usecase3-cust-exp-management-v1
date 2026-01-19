# Agent Node & Tool Design - Implementation Plan

## Date: 2026-01-19
## Session Goal: Complete detailed LangGraph node and tool designs for all 9 agents

---

## Work Completed Previously

- [x] Requirements gathering and clarification
- [x] Technology research (CNC, PCA, A2A, LangGraph, SR-TE)
- [x] Defined 9 agents and their responsibilities
- [x] Designed 7-phase workflow (SLA degradation → restoration)
- [x] Selected orchestration pattern (Supervisor + Hybrid logic)
- [x] Designed Redis state schema
- [x] Designed edge case handling
- [x] Created project structure
- [x] Documented deployment architecture (Kubernetes microservices)
- [x] Added Traffic Analytics Agent for proactive SRv6 demand matrix
- [x] **Added reference documentation to Git** (SR-MPLS/SRv6, CNC 7.1 PCE)
- [x] **Updated DESIGN.md with CNC API details, JWT auth, BSID strategy, traffic matrix sources**

---

## Today's Detailed Design Tasks

### Phase 1: Core Workflow Agents

#### 1. Orchestrator Agent
- [x] Define LangGraph state schema
- [x] Define state machine nodes and transitions
- [x] Identify LLM vs rule-based decision points
- [x] Define A2A tools for calling other agents
- [x] Define Redis state management tools

#### 2. Event Correlator Agent
- [x] Define LangGraph nodes (ingest, dedup, correlate, flap-detect)
- [x] Define tools (PCA webhook, CNC alarm API, Redis dedup)
- [x] Define alert correlation rules
- [x] Define flap detection algorithm

#### 3. Service Impact Agent
- [x] Define LangGraph nodes (query, analyze)
- [x] Define CNC Service Health API tool
- [x] Define service-to-link mapping logic

#### 4. Path Computation Agent
- [x] Define LangGraph nodes (request, constraints, validate)
- [x] Define Knowledge Graph Dijkstra API tool
- [x] Define constraint builder (link/node/SRLG avoidance)

#### 5. Tunnel Provisioning Agent
- [x] Define LangGraph nodes (detect-TE, create, steer, verify)
- [x] Define MCP tools for CNC tunnel APIs
- [x] Define RSVP-TE, SR-MPLS, SRv6 payload schemas
- [x] Define BSID allocation strategy

#### 6. Restoration Monitor Agent
- [x] Define LangGraph nodes (monitor, hold-timer, stability, cutover)
- [x] Define PCA SLA query tool
- [x] Define gradual cutover weights

### Phase 2: Supporting Agents

#### 7. Traffic Analytics Agent
- [x] Define LangGraph nodes (collect, compute-matrix, predict, alert)
- [x] Define telemetry collectors (SR-PM, MDT, NetFlow)
- [x] Define demand matrix computation for SRv6/SR-MPLS/RSVP-TE
- [x] Define congestion threshold logic

#### 8. Notification Agent
- [x] Define LangGraph nodes (select-channel, format, deliver)
- [x] Define channel tools (Webex, ServiceNow, Email)
- [x] Define notification templates

#### 9. Audit Agent
- [x] Define LangGraph nodes (capture, format, store)
- [x] Define PostgreSQL write tool
- [x] Define audit event schema

---

## API Documentation Incorporated

| System | Status |
|--------|--------|
| CNC JWT Authentication | ✅ Documented in DESIGN.md |
| CNC SR Policy Create API | ✅ Full schema in DESIGN.md |
| CNC RSVP-TE Tunnel API | ✅ Endpoint documented |
| PCEP Protocol | ✅ Message types documented |
| BGP-LS Topology | ✅ Integration with KG documented |
| Traffic Matrix Sources | ✅ All 3 TE types documented |

---

## Deliverables

1. ✅ Updated DESIGN.md with CNC integration details
2. [ ] Detailed node diagrams for each agent (in DESIGN.md)
3. [ ] Tool definitions with input/output Pydantic schemas
4. [ ] A2A task schemas for inter-agent communication
5. [ ] Commit all changes to GitHub

---

## Reference Files

- Design Document: `DESIGN.md`
- SR-MPLS/SRv6 Guide: `Segment Routing (SR-MPLS & SRv6) Architecture...docx`
- CNC 7.1 PCE Guide: `Segment Routing PCE in Cisco Crosswork Network Controller 7.1.docx`
