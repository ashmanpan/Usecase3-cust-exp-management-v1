# Tomorrow's Tasks - Agent Node & Tool Design

## Date: 2026-01-09
## Session Goal: Design detailed nodes, tools, and API calls for each agent

---

## Work Completed Today (2026-01-08)

- [x] Requirements gathering and clarification
- [x] Technology research (CNC, PCA, A2A, LangGraph, SR-TE)
- [x] Defined 8 agents and their responsibilities
- [x] Designed 7-phase workflow (SLA degradation → restoration)
- [x] Selected orchestration pattern (Supervisor + Hybrid logic)
- [x] Designed Redis state schema
- [x] Designed edge case handling
- [x] Created project structure
- [x] Documented deployment architecture (Kubernetes microservices)

---

## Tomorrow's Detailed Design Tasks

For each of the 8 agents, we need to design:

### 1. Orchestrator Agent
- [ ] Define LangGraph nodes (state machine states)
- [ ] Define transitions between nodes
- [ ] Identify where LLM is used vs rule-based logic
- [ ] Define tools for calling other agents (A2A)
- [ ] Define Redis state management tools

### 2. Event Correlator Agent
- [ ] Define LangGraph nodes:
  - Alert ingestion node
  - Deduplication node
  - Correlation node
  - Flap detection node
- [ ] Define tools:
  - PCA API client tool (webhook/poll)
  - CNC Alarm API tool
  - Redis dedup lookup tool
- [ ] Determine if LLM is needed (probably not - rule-based)
- [ ] Define API schemas for PCA/CNC alerts

### 3. Service Impact Agent
- [ ] Define LangGraph nodes:
  - Service query node
  - Impact analysis node
- [ ] Define tools:
  - CNC Service Health API tool
  - MCP tool for service queries
- [ ] Determine if LLM/RAG is needed
- [ ] Define API schemas for service health response

### 4. Path Computation Agent
- [ ] Define LangGraph nodes:
  - Path request node
  - Constraint building node
  - Path validation node
- [ ] Define tools:
  - Knowledge Graph Dijkstra API tool
  - Constraint builder tool (link/node avoidance)
- [ ] Determine if LLM is needed (probably not)
- [ ] Define KG API schemas (request/response)

### 5. Tunnel Provisioning Agent
- [ ] Define LangGraph nodes:
  - TE type detection node
  - Tunnel creation node
  - Traffic steering node
  - Verification node
- [ ] Define tools:
  - MCP Server tool for CNC tunnel provisioning
  - TE type detector tool
  - Tunnel status verification tool
- [ ] Define MCP tool schemas for:
  - RSVP-TE tunnel creation
  - SR-MPLS policy creation
  - SRv6 policy creation
- [ ] Determine if LLM is needed

### 6. Restoration Monitor Agent
- [ ] Define LangGraph nodes:
  - SLA monitoring node (polling)
  - Hold timer management node
  - Stability verification node
  - Cutover decision node
  - Gradual cutover execution node
- [ ] Define tools:
  - PCA SLA query tool
  - Hold timer tool (Redis)
  - MCP tool for weight adjustment (gradual cutover)
- [ ] Determine if LLM is needed

### 7. Notification Agent
- [ ] Define LangGraph nodes:
  - Channel selection node
  - Message formatting node
  - Delivery node
- [ ] Define tools:
  - Webex API tool
  - ServiceNow API tool
  - Email tool
- [ ] Define notification templates per event type

### 8. Audit Agent
- [ ] Define LangGraph nodes:
  - Event capture node
  - Log formatting node
  - Storage node
- [ ] Define tools:
  - PostgreSQL write tool
  - Log aggregation tool
- [ ] Define audit event schema

---

## API Documentation Needed

| System | API Details Needed |
|--------|-------------------|
| PCA | Alert webhook format, SLA query endpoint |
| CNC Service Health | Service list endpoint, affected services query |
| CNC Tunnel/SR-TE | Tunnel create/delete/modify endpoints |
| Knowledge Graph | Dijkstra path query, constraint format |
| MCP Server | Existing tool definitions |
| Service Registry | Registration/discovery API |

---

## Questions to Answer Tomorrow

1. For each agent: How many LangGraph nodes?
2. For each node: What action is taken?
3. For each tool: What is the input/output schema?
4. Where does LLM reasoning happen vs deterministic logic?
5. Which nodes call external APIs (KG, MCP, PCA, CNC)?
6. What is the A2A task schema between Orchestrator and each agent?

---

## Deliverables for Tomorrow

1. Detailed node diagram for each agent
2. Tool definitions (name, description, input/output schema)
3. API specifications for external integrations
4. A2A task schemas for inter-agent communication
5. Updated design document with all details

---

## Reference Files

- Design Document: `/home/kpanse/.claude/plans/swift-bouncing-robin.md`
- This Task File: `/home/kpanse/wsl-myprojects/Usecase3-cust-exp-management-v1/tomorrow_tasks.md`
