# Human Developer Action Items

**Generated:** 2026-02-18 (Updated after code verification)
**Context:** AI agents completed 6-pass analysis (code review, architecture, security, completeness, IO integration, exploration) of all 9 LangGraph agents + shared agent_template, then applied 22 fixes. This document has been verified against the CURRENT state of the code.
**Priority Level:** Critical
**Estimated Effort:** ~2-3 weeks for a senior developer

---

## Auto-Fixed Items (Verified Complete)

All 22 auto-fixes have been verified as correctly applied in the current codebase:

| # | Issue | Status |
|---|-------|--------|
| 1 | `check_dampen_complete` not exported in `orchestrator/nodes/__init__.py` | DONE - import and `__all__` entry present |
| 2 | `record_state_change()` -> `record_event()` in `flap_detect_node.py` | DONE - line 63 |
| 3 | `get_flap_count()` added to `FlapDetector` | DONE - called at line 69 |
| 4 | Tunnel retry routes to `return_success` via `retry_gate` | DONE - `workflow.py` lines 53-56 |
| 5 | `asyncio.run()` lifecycle bug fixed | DONE - FastAPI lifespan in `main.py` lines 172-183 |
| 6 | Config model missing `agents` field | DONE - `config_loader.py` line 126 |
| 7 | `.gitignore` comprehensive | DONE - 58 lines of exclusions |
| 8 | Dockerfiles run as non-root | DONE - `useradd` + `USER agent` in all Dockerfiles |
| 9 | `verify=False` removed | DONE - All 3 clients use `CA_CERT_PATH` env var |
| 10 | Simulated JWT token replaced | DONE - Real 2-step CNC SSO flow in `cnc_tunnel.py` |
| 11 | Real RSVP-TE tunnel creation | DONE - `cnc_tunnel.py` lines 120-160 |
| 12 | Real tunnel verify/delete | DONE - `cnc_tunnel.py` lines 162-198 |
| 13 | Fake success on tunnel creation removed | DONE - returns `TunnelResult(success=False, ...)` |
| 14 | AgentRunner builds full registry | DONE - `main.py` lines 94-100 |
| 15 | ServiceEndpoints `extra="allow"` | DONE - `config_loader.py` line 92 |
| 16 | IO notifications added to phases 5-7 | DONE - see below |
| 17 | `notify_error()` called in failure paths | DONE - see below |
| 18 | Bounded task storage (1000 limit) | DONE - `_evict_old_tasks()` in `server.py` lines 390-400 |
| 19 | Webex/ServiceNow return `success=False` on errors | DONE |
| 20 | Simulation gated behind `SIMULATE_MODE` | DONE - `telemetry_collector.py`, `kg_client.py`, `pca_client.py`, `cutover.py` |
| 21 | TunnelConfig RSVP-TE fields added | DONE |
| 22 | `.env.example` created | DONE - 73 lines covering all env vars |

### IO Notification Verification (Items 16-17)

| Node | `notify_phase_change` | `notify_error` |
|------|----------------------|----------------|
| `steer_node.py` | DONE (line 47) | DONE (line 59) |
| `monitor_node.py` | DONE (line 47) | DONE (line 134) |
| `restore_node.py` | DONE (line 47) | Not needed (non-critical failures logged) |
| `escalate_node.py` | DONE (line 87) | Not needed (escalation IS the error path) |
| `provision_node.py` | DONE (line 115) | NOT DONE - see Section 4 |

---

## OPEN Task Checklist

### 1. Replace Remaining Simulation Code with Real Integrations

**Priority: HIGH**

#### 1.1 Audit Agent - Database Integrations (STILL OPEN - All simulated)
- [ ] **Uncomment and wire `asyncpg` PostgreSQL code**
  - **File:** `agents/audit/tools/postgresql_client.py`
  - **Lines:** 40-56 (connect), 93-112 (insert), 134-178 (timeline query), 202-238 (compliance report), 267-273 (upsert)
  - All methods currently log "simulated" and return fake data
  - **How:** Uncomment `asyncpg` code, add `asyncpg` to `pyproject.toml`
  - **Verification:** `INSERT INTO audit_events` actually persists; `SELECT` queries return real rows

- [ ] **Create PostgreSQL schema migrations**
  - No `migrations/` directory exists
  - **How:** Create SQL files for `audit_events` and `incidents` tables matching the commented-out schemas
  - **Verification:** Tables exist in PostgreSQL after migration

- [ ] **Uncomment and wire Elasticsearch async client**
  - **File:** `agents/audit/tools/elasticsearch_client.py`
  - **Lines:** 42-53 (connect), 106-117 (index), 164-178 (search), 200-227 (aggregation)
  - All methods currently log "simulated" and return empty/fake data
  - **How:** Uncomment `AsyncElasticsearch` code, add `elasticsearch` to dependencies

#### 1.2 Restoration Monitor - Tunnel Deleter (STILL OPEN)
- [ ] **Fix tunnel_deleter.py fake success on CNC HTTP errors**
  - **File:** `agents/restoration_monitor/tools/tunnel_deleter.py` lines 101-109
  - **Problem:** On `httpx.HTTPError`, returns `DeleteTunnelOutput(success=True, bsid_released=...)` with a fake BSID
  - **Not gated behind `SIMULATE_MODE`** unlike other simulation code
  - **How:** Gate behind `SIMULATE_MODE` or return `success=False`
  - **Risk:** Silently pretending a tunnel was deleted when it was not

#### 1.3 Traffic Analytics - MDT gRPC (STILL OPEN)
- [ ] **Implement real MDT telemetry collection via gRPC**
  - **File:** `agents/traffic_analytics/tools/telemetry_collector.py` lines 120-131
  - `collect_mdt()` currently returns empty list (or simulation if `SIMULATE_MODE=true`)
  - **How:** Implement gRPC dial-in/dial-out to MDT collector endpoint

- [ ] **Add scheduler for proactive polling**
  - **File:** `agents/traffic_analytics/main.py`
  - No scheduler exists - agent only responds to on-demand A2A requests
  - **How:** Add `APScheduler` with `AsyncIOScheduler`, trigger every 5 minutes

#### 1.4 Email Client Error Handling (VERIFIED DONE)
- [x] ~~Email client: return `success=False` on failure~~ - DONE at line 109 of `email_client.py`
- Note: Missing-credential handler returns `success=True` at line 56 (acceptable for graceful degradation)

#### 1.5 Service Impact - CNC API Failure (STILL OPEN)
- [ ] **Return error on CNC API failure instead of empty list**
  - **File:** `agents/service_impact/tools/cnc_client.py` line 168
  - **Problem:** `except Exception` returns `return []` - the orchestrator interprets this as "zero services affected" and closes the incident
  - **How:** Raise exception or return sentinel value distinguishing "no services" from "API failure"

---

### 2. Security Hardening

**Priority: HIGH**

#### 2.1 Verified DONE
- [x] ~~A2A token authentication~~ - DONE: `X-Agent-Token` header validation in `server.py` lines 117-123
- [x] ~~Remove hardcoded JWT token~~ - DONE: Real CNC SSO flow
- [x] ~~Fix `verify=False`~~ - DONE: All 3 clients (`cnc_tunnel.py`, `cnc_client.py`, `kg_client.py`) use `CA_CERT_PATH` pattern

#### 2.2 STILL OPEN
- [ ] **Enable TLS for inter-agent communication**
  - All `config.yaml` files use `http://` URLs
  - **How:** Change to `https://`, configure TLS on uvicorn, or deploy behind Istio/sidecar proxy
  - **Verification:** `tcpdump` shows encrypted traffic between agents

- [ ] **Fix empty password defaults** - fail fast if `POSTGRES_PASSWORD`, `ES_PASSWORD`, `CNC_PASSWORD` env vars are empty strings
  - `postgresql_client.py` line 33: `os.getenv("POSTGRES_PASSWORD", "")` silently connects with no password
  - `cnc_tunnel.py` line 39: `os.getenv("CNC_PASSWORD", "")` silently authenticates with empty password

- [ ] **Sanitize error responses** - `server.py` line 266: `HTTPException(status_code=500, detail=str(e))` leaks internal error details to callers

- [ ] **Add request size limits** - no uvicorn `--limit-max-request-size` or FastAPI middleware

- [ ] **Add rate limiting** - no `slowapi` or equivalent configured

- [ ] **Validate callback_url** - no SSRF protection on `_send_callback()` in `server.py` line 402; accepts any URL

- [ ] **Redact PII from logs** - no structlog processor to filter credentials/email addresses

- [ ] **Add CORS middleware** - no `CORSMiddleware` configured on FastAPI app

#### 2.3 Medium-term (STILL OPEN)
- [ ] **Enable Redis AUTH** - all configs use `redis://redis:6379` without password
- [ ] **Implement audit trail integrity** - no hash chains or append-only enforcement
- [ ] **Validate webhook payloads** - no Pydantic models for PCA/CNC webhook payloads
- [ ] **Add `.dockerignore` files** - no `.dockerignore` files exist anywhere in repo
- [ ] **Pin Docker base image digests** - all Dockerfiles use `FROM python:3.11-slim` without digest

---

### 3. Architecture Fixes

**Priority: MEDIUM**

- [ ] **Refactor Restoration Monitor to use async A2A**
  - **Problem:** `asyncio.sleep(30)` in `wait_poll_node` (line 34 of `workflow.py`) x 100 max iterations = 50 minutes blocking a worker
  - **How:** Orchestrator calls `POST /a2a/tasks/async` with `callback_url`; restoration monitor runs independently

- [ ] **Fix LangGraph list state mutation pattern**
  - **Problem:** All 9 agents use `state.get("nodes_executed", []) + ["new_node"]` pattern
  - **Where:** Verified in `flap_detect_node.py`, `steer_node.py`, `monitor_node.py`, `restore_node.py`, `provision_node.py`, and more
  - **How:** Add `Annotated[list, operator.add]` to list fields in state TypedDicts; change nodes to return only new items: `{"nodes_executed": ["new_node"]}`
  - **State schema lacking this:** `OrchestratorState` (`orchestrator/schemas/state.py`) has plain `List[str]` and `List[dict]` without reducers

- [ ] **Add circuit breaker for external APIs**
  - No `pybreaker` or equivalent exists
  - **How:** Wrap CNC/KG/PCA clients with circuit breaker (trip after 5 failures, half-open after 60s)

- [ ] **Wire `max_retries` config to tenacity decorator**
  - **File:** `agent_template/tools/a2a_client/client.py` lines 98 and 132
  - **Problem:** `stop=stop_after_attempt(3)` is hardcoded, ignores any config value

- [ ] **Fix Redis/HTTP connection lifecycle**
  - Singleton clients (`FlapDetector`, `BSIDAllocator`, `PCASLAClient`, `TunnelDeleter`, `GradualCutover`) create connections never closed
  - FastAPI lifespan in `main.py` only closes `_mcp_client` (line 179), not these tool singletons
  - **How:** Wire singleton `.close()` methods into FastAPI shutdown handler

---

### 4. IO Agent Integration Gaps

**Priority: MEDIUM**

#### Verified DONE
- [x] ~~IO notifications in steer_node (Phase 5)~~ - DONE
- [x] ~~IO notifications in monitor_node (Phase 6)~~ - DONE
- [x] ~~IO notifications in restore_node (Phase 7)~~ - DONE
- [x] ~~IO notifications in escalate_node~~ - DONE
- [x] ~~Wire `notify_error()`~~ - DONE: Called in `steer_node.py` (line 59) and `monitor_node.py` (line 134)

#### STILL OPEN
- [ ] **Add IO error notifications to provision_node on failure**
  - `provision_node.py` calls `notify_phase_change` on success (line 115) but does NOT call `notify_error` when provisioning fails or when max retries exceeded
  - **How:** Add `notify_error()` calls at lines 132 (max retries) and 163 (A2A call failed)

- [ ] **Design human-in-the-loop mechanism**
  - Currently no way for operators to approve/reject actions
  - Escalation node recommends actions but cannot receive operator input
  - **How:** Add approval endpoint, integrate with escalate_node to wait for human decision

---

### 5. Testing

**Priority: HIGH**

#### Current State
- 1 test file exists: `agent_template/tests/test_workflow.py` (128 lines) - tests BaseWorkflow, iteration check, checklist check, error check
- No tests for any of the 9 agent workflows
- No tests for conditional edge functions
- No tests for tool classes
- No integration tests

#### STILL OPEN
- [ ] **Unit tests for all 9 conditional edge functions** (`agents/orchestrator/nodes/conditions.py` - 9 functions, 0 tests)
- [ ] **Unit tests for tool classes** - `FlapDetector`, `BSIDAllocator`, `DedupChecker`, `PCASLAClient`, `KGDijkstraClient`, `CNCTunnelClient`, `TunnelDeleter`, `GradualCutover`
- [ ] **Integration tests for all 9 workflows** - mock A2A calls, run each workflow with test state
- [ ] **Test config loader env var substitution** - `_substitute_env_vars()` function
- [ ] **End-to-end test** - run orchestrator with mocked downstream agents
- [ ] **Test A2A authentication** - verify `_verify_a2a_token` rejects bad tokens

---

### 6. Deployment Infrastructure

**Priority: HIGH**

#### Current State
- No `docker-compose.yaml` exists
- No Kubernetes manifests exist
- No `.dockerignore` files exist
- No `requirements.lock` files exist
- `agent_template` installed as editable (`pip install -e .`)

#### STILL OPEN
- [ ] **Create `docker-compose.yaml`**
  - Services: All 9 agents + Redis + PostgreSQL + optional Elasticsearch + OTEL collector
  - Network aliases must match URL defaults (e.g., `event-correlator:8001`, `service-impact:8002`)
  - Inject secrets via `.env` file or Docker secrets
  - **Verification:** `docker-compose up` starts all services, health checks pass

- [ ] **Create Kubernetes manifests**
  - Deployment, Service, ConfigMap, Secret per agent
  - NetworkPolicy to restrict inter-agent communication

- [ ] **Build `agent_template` as proper Python wheel**
  - Currently installed as editable (`pip install -e .`) which depends on source at exact path
  - **How:** `python -m build` then install wheel in Dockerfile

- [ ] **Create `requirements.lock`** for reproducible builds
  - **How:** `pip-compile pyproject.toml -o requirements.lock`

- [ ] **Wire OpenTelemetry instrumentation**
  - Config says `otel.enabled: true` but zero instrumentation code exists
  - **How:** Add `opentelemetry-instrumentation-httpx` and `opentelemetry-instrumentation-fastapi` auto-instrumentation

---

### 7. Documentation Discrepancies

**Priority: LOW**

- [ ] **Reconcile hold timer values**: `agents/orchestrator/config.yaml` says `platinum: 60` (seconds), `WORKFLOW.md` says `platinum: 30 seconds`
- [ ] **Clarify Event Correlator entry point**: WORKFLOW.md says it's the entry point, but code has Orchestrator calling it via A2A
- [ ] **Add Audit Agent to all phase transitions**: DESIGN.md says log every transition, but only `steer_node`, `restore_node`, and `close_node` call Audit

---

## Summary of Changes from Previous Version

### Items Updated to DONE (were previously OPEN)
1. **Email client error handling** (Section 1.6) - Verified `success=False` returned on exception at line 109
2. **IO notifications in steer/monitor/restore/escalate** (Section 4) - All verified as implemented
3. **`notify_error()` wired** (Section 4) - Called in steer_node and monitor_node failure paths
4. **TLS verification fix** (Section 2.2) - Moved to verified DONE; all 3 clients correctly use `CA_CERT_PATH`

### NEW Items Identified
1. **`provision_node.py` missing `notify_error()`** - calls `notify_phase_change` on success but not `notify_error` on failure or max retries
2. **Tunnel deleter NOT gated behind `SIMULATE_MODE`** - unlike cutover.py and pca_client.py, the tunnel_deleter.py returns fake success on HTTP errors without checking `SIMULATE_MODE`
3. **FastAPI shutdown handler incomplete** - only closes `_mcp_client`, not Redis/HTTP singletons in tool classes
4. **Audit Agent not called from most nodes** - only steer, restore, and close nodes call audit; detect, assess, compute, and escalate nodes also call it but monitor and provision do not

### Items Confirmed STILL OPEN
- All simulation stubs in audit agent (PostgreSQL + Elasticsearch)
- All security hardening items except auth, JWT, and TLS verification
- All architecture fixes
- All testing items (1 test file exists but only for base workflow)
- All deployment infrastructure items (no docker-compose, no k8s, no wheel build)
- All documentation discrepancies

---

## Known Risks

1. **Simulation code removal must be coordinated** - don't remove simulations until real API integrations are tested. Use `SIMULATE_MODE=true` for development.
2. **Tunnel deleter can silently fake success** - unlike other tools, not gated behind `SIMULATE_MODE`. Could lead to orphaned tunnels.
3. **Service impact empty-list-on-error** - CNC API failure returns `[]`, causing orchestrator to close incidents as "no services affected."
4. **50-minute blocking worker** - Restoration monitor `asyncio.sleep(30) * 100` blocks the orchestrator worker thread.
5. **LangGraph list mutation** - Without `Annotated[list, operator.add]`, list state updates may be silently dropped by LangGraph reducers.
