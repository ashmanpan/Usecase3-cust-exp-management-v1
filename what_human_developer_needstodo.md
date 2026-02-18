# Human Developer Action Items

**Generated:** 2026-02-18
**Context:** AI agents completed 6-pass analysis (code review, architecture, security, completeness, IO integration, exploration) of all 9 LangGraph agents + shared agent_template.
**Priority Level:** Critical
**Estimated Effort:** ~2-3 weeks for a senior developer

---

## 🚨 Critical Actions (Do First)

These issues **prevent the system from starting or running correctly**. They were auto-fixed by Claude Code where possible (marked ✅), but need human verification.

### ✅ Auto-Fixed by Claude Code

| # | Issue | File | Fix Applied |
|---|-------|------|-------------|
| 1 | `check_dampen_complete` not exported | `orchestrator/nodes/__init__.py` | Added import and `__all__` entry |
| 2 | `record_state_change()` doesn't exist | `event_correlator/nodes/flap_detect_node.py:63` | Changed to `record_event()` |
| 3 | `get_flap_count()` doesn't exist | `event_correlator/nodes/flap_detect_node.py:69` | Added `get_flap_count()` method to `FlapDetector` |
| 4 | Tunnel retry routes to `return_success` | `tunnel_provisioning/workflow.py:47-48` | Added retry node with `check_can_retry` routing |
| 5 | `asyncio.run()` lifecycle bug | `agent_template/main.py:162-182` | Moved init into FastAPI lifespan context manager |
| 6 | Config model missing `agents` field | `agent_template/config_loader.py:113` | Added `agents: dict` field to `Config` |
| 7 | `.gitignore` nearly empty | `.gitignore` | Added comprehensive exclusions |
| 8 | 7 Dockerfiles run as root | All 7 agent Dockerfiles | Added `useradd` + `USER agent` |
| 9 | `verify=False` on HTTPS clients | `cnc_tunnel.py`, `kg_client.py`, `cnc_client.py` | Changed to `CA_CERT_PATH` env var |
| 10 | Simulated JWT token (hardcoded) | `cnc_tunnel.py:29-35` | Implemented real CNC SSO 2-step JWT flow |
| 11 | Simulated RSVP-TE tunnel creation | `cnc_tunnel.py:97-107` | Implemented real CNC RSVP-TE API call |
| 12 | Simulated tunnel verify/delete | `cnc_tunnel.py:109-115` | Implemented real CNC API calls |
| 13 | Fake success on tunnel creation error | `cnc_tunnel.py:84-95` | Returns failure on error instead of fake success |
| 14 | AgentRunner only registers PCA | `agent_template/main.py:94-96` | Builds registry from full `config.agents` section |
| 15 | ServiceEndpoints too rigid | `agent_template/config_loader.py:90-95` | Added `extra="allow"` for dynamic endpoints |
| 16 | Missing IO notifications (phases 5-7) | `steer_node.py`, `monitor_node.py`, `restore_node.py`, `escalate_node.py` | Added `notify_phase_change` calls |
| 17 | `notify_error()` never called | `steer_node.py`, `monitor_node.py` | Added error notifications in failure paths |
| 18 | Unbounded in-memory task storage | `agent_template/api/server.py` | Added eviction with 1000 task limit |
| 19 | Webex/ServiceNow fake success on errors | `webex_client.py`, `servicenow_client.py` | HTTP errors now return `success=False` |
| 20 | Uncontrolled simulation fallbacks | `telemetry_collector.py`, `kg_client.py` | Gated behind `SIMULATE_MODE` env var |
| 21 | TunnelConfig missing RSVP-TE fields | `tunnel_provisioning/schemas/tunnels.py` | Added `bandwidth_gbps`, `setup_priority`, `hold_priority` |
| 22 | No `.env.example` file | Root directory | Created with all required env vars documented |

### ⚠️ Human Verification Required

- [ ] **Verify all auto-fixes**: Run `git diff` and review every change
- [ ] **Test orchestrator startup**: `cd agents/orchestrator && python main.py` — should no longer crash with ImportError
- [ ] **Test event correlator**: Verify flap detection works with the corrected method names
- [ ] **Test tunnel provisioning retry**: Verify that failed tunnel creation retries up to 3 times before giving up
- [ ] **Test agent_template lifecycle**: Verify FastAPI lifespan initializes MCP/A2A clients correctly

---

## 📋 Task Checklist

### 1. Replace All Simulation Code with Real Integrations (47 stubs found)

**Why:** The system currently runs end-to-end while doing absolutely nothing real to the network. Every external integration either returns simulated data or silently degrades to `success=True` on failure.

**Priority: HIGH — This is the core functionality gap**

#### 1.1 Tunnel Provisioning (✅ All 5 stubs fixed by Claude Code)
- [x] ~~Implement real CNC JWT authentication~~ — ✅ 2-step SSO flow implemented
- [x] ~~Implement real `create_rsvp_tunnel()`~~ — ✅ Real CNC RSVP-TE API call implemented
- [x] ~~Implement real `verify_tunnel()`/`delete_tunnel()`~~ — ✅ Real CNC API calls implemented
- [ ] **Human verification needed:** Test JWT flow against actual CNC instance
- [x] ~~Implement real `verify_tunnel()`~~ — ✅ Fixed
- [x] ~~Implement real `delete_tunnel()`~~ — ✅ Fixed
- [x] ~~Remove simulated success fallback~~ — ✅ Returns failure on error

#### 1.2 Audit Agent — Database Integrations (9 stubs)
- [ ] **Uncomment and wire `asyncpg` PostgreSQL code**
  - **File:** `agents/audit/tools/postgresql_client.py` — lines 40-56, 93-112, 134-178, 202-238, 267-273
  - **How:** Uncomment all `await conn.execute(...)` code, add `asyncpg` to `pyproject.toml`
  - **Verification:** `INSERT INTO audit_events` actually persists data; `SELECT` queries return real rows
- [ ] **Create PostgreSQL schema migrations**
  - **How:** Create `migrations/` directory with SQL files for `audit_events` and `incidents` tables
  - **Verification:** Tables exist in PostgreSQL after migration
- [ ] **Uncomment and wire Elasticsearch async client**
  - **File:** `agents/audit/tools/elasticsearch_client.py` — lines 42-53, 106-117, 164-178, 200-227
  - **How:** Uncomment `await self._client.index(...)` code, add `elasticsearch` to dependencies
  - **Verification:** Events appear in Elasticsearch `audit-events-*` index

#### 1.3 Path Computation (✅ Fixed by Claude Code)
- [x] ~~Remove silent `_simulate_path()` fallback~~ — ✅ Returns `None` unless `SIMULATE_MODE=true`
- [x] ~~Gate simulation behind `SIMULATE_MODE` env var~~ — ✅ Done

#### 1.4 Restoration Monitor (6 stubs)
- [ ] **Replace random SLA simulation with real PCA API call**
  - **File:** `agents/restoration_monitor/tools/pca_client.py:95-139`
  - **How:** Return failure status when PCA is unavailable instead of `random.random()` coin flip
  - **Verification:** PCA down → SLA status = "unknown", not random pass/fail
- [ ] **Implement real tunnel deletion**
  - **File:** `agents/restoration_monitor/tools/tunnel_deleter.py:101-109`
  - **How:** Return `success=False` when CNC unavailable
- [ ] **Implement real ECMP weight updates**
  - **File:** `agents/restoration_monitor/tools/cutover.py:234-240`
  - **How:** Return `success=False` when CNC unavailable (silently pretending weights changed could blackhole traffic!)

#### 1.5 Traffic Analytics (partially fixed)
- [ ] **Implement real MDT telemetry collection via gRPC**
  - **File:** `agents/traffic_analytics/tools/telemetry_collector.py:117-126`
  - **How:** Implement gRPC dial-in/dial-out to MDT collector endpoint
- [x] ~~Gate simulation methods behind `SIMULATE_MODE`~~ — ✅ All 3 simulation methods gated
- [ ] **Add scheduler for proactive polling**
  - **File:** `agents/traffic_analytics/main.py`
  - **How:** Add `APScheduler` with `AsyncIOScheduler`, trigger every 5 minutes
  - **Verification:** Agent runs autonomously, not just on-demand

#### 1.6 Notification Agent (partially fixed)
- [x] ~~Webex client: return `success=False` on HTTP errors~~ — ✅ Fixed
- [x] ~~ServiceNow client: return `success=False` on HTTP errors~~ — ✅ Fixed (both create and update)
- [ ] **Email client: return `success=False` on failure paths**
  - **File:** `agents/notification/tools/email_client.py`
  - **How:** Check exception handlers return `success=False` not `success=True`
- Note: Missing-credential handlers still return `success=True` (acceptable for graceful degradation when service not configured)

#### 1.7 Service Impact (3 stubs)
- [ ] **Return error on CNC API failure instead of empty list**
  - **File:** `agents/service_impact/tools/cnc_client.py:161-168`
  - **How:** Raise exception or return sentinel value indicating failure
  - **Verification:** Orchestrator doesn't interpret API failure as "zero services affected"

---

### 2. Security Hardening (28 findings, 3 critical)

**Why:** Zero authentication + plaintext HTTP means anyone on the network can trigger tunnel provisioning. This is a network management system — security is non-negotiable.

#### 2.1 Immediate (CRITICAL)
- [x] ~~Add authentication to all A2A endpoints~~ — ✅ `X-Agent-Token` header validation added to `/a2a/tasks` and `/a2a/tasks/async`, gated on `A2A_SHARED_SECRET` env var
- [ ] **Enable TLS for inter-agent communication**
  - **Files:** All `config.yaml` files (orchestrator, service_impact, etc.)
  - **How:** Change all `http://` URLs to `https://`, configure TLS certificates on uvicorn, or deploy behind Istio service mesh
  - **Verification:** `tcpdump` shows encrypted traffic between agents
- [x] ~~Remove hardcoded JWT token~~ — ✅ Replaced with real CNC SSO flow

#### 2.2 Short-term (HIGH)
- [ ] **Fix empty password defaults** — fail fast if `POSTGRES_PASSWORD`, `ES_PASSWORD`, `CNC_PASSWORD` env vars not set
- [ ] **Fix TLS verification** — change `verify=False` to `verify=os.getenv("CA_CERT_PATH", True)` in `cnc_tunnel.py`, `cnc_client.py`, `kg_client.py`
- [ ] **Add request size limits** — configure uvicorn `--limit-max-request-size` or add FastAPI middleware
- [ ] **Add rate limiting** — install `slowapi`, configure per-IP limits on all endpoints
- [ ] **Sanitize error responses** — change `HTTPException(500, detail=str(e))` to generic message in `server.py:249`
- [ ] **Redact PII from logs** — add structlog processor to filter email addresses, credentials
- [ ] **Validate callback_url** — block RFC 1918 addresses, cloud metadata endpoints (SSRF prevention)
- [ ] **Add CORS middleware** — configure `CORSMiddleware` with explicit allowed origins

#### 2.3 Medium-term (MEDIUM)
- [ ] **Enable Redis AUTH** — use `redis://:${REDIS_PASSWORD}@redis:6379` in all configs
- [ ] **Implement audit trail integrity** — hash chains or append-only PostgreSQL tables
- [ ] **Validate webhook payloads** — create Pydantic models for PCA/CNC webhook payloads
- [ ] **Add `.dockerignore` files** — exclude `.env`, `.git`, `__pycache__`, `tests/`
- [ ] **Pin Docker base image digests** — `FROM python:3.11-slim@sha256:<digest>`

---

### 3. Architecture Fixes

**Why:** Critical design issues that cause timeouts, resource leaks, and incorrect behavior.

- [ ] **Refactor Restoration Monitor to use async A2A**
  - **Problem:** `asyncio.sleep(30)` × 100 iterations = 50 minutes blocking a single worker
  - **File:** `agents/restoration_monitor/workflow.py:33`
  - **How:** Orchestrator should call `POST /a2a/tasks/async` with `callback_url`. Restoration monitor runs in background, POSTs result back when done.
  - **Verification:** Orchestrator worker is free during monitoring, restoration monitor runs independently

- [ ] **Fix LangGraph list state mutation pattern**
  - **Problem:** `state.get("list", []).append(x)` is not safe with LangGraph reducers
  - **Where:** All 9 agent state schemas
  - **How:** Add `Annotated[list, operator.add]` to all list fields in TypedDicts. Change nodes to return only new items: `return {"nodes_executed": ["new_node"]}` instead of `state.get("nodes_executed", []) + ["new_node"]`

- [ ] **Add circuit breaker for external APIs**
  - **Why:** If CNC is down during a major event, all agents hammer it simultaneously
  - **How:** Install `pybreaker` library, wrap CNC/KG/PCA clients with circuit breaker (trip after 5 failures, half-open after 60s)

- [ ] **Wire `max_retries` config to tenacity decorator**
  - **File:** `agent_template/tools/a2a_client/client.py:97`
  - **Problem:** Hardcoded `stop_after_attempt(3)` ignores config

- [ ] **Fix Redis/HTTP connection lifecycle**
  - **Problem:** Singleton tool clients (`StateManagerTool`, `FlapDetector`, `BSIDAllocator`) create Redis connections that are never closed
  - **How:** Wire `close()` into FastAPI shutdown handler

---

### 4. IO Agent Integration Gaps

**Why:** The human operator UI only sees 4 of 11 orchestrator phases. Critical events (steering, monitoring, restoration, escalation) are invisible.

- [ ] **Add IO notifications to steer_node** (Phase 5: Traffic steered to protection tunnel)
- [ ] **Add IO notifications to monitor_node** (Phase 6: Monitoring progress, SLA recovery)
- [ ] **Add IO notifications to restore_node** (Phase 7: Cutover progress 25→50→75→100%)
- [ ] **Add IO notifications to escalate_node** (LLM reasoning and recommended action)
- [ ] **Add IO notifications on provisioning failures** (retry attempts, max-retries-exceeded)
- [ ] **Wire `notify_error()`** — defined in `io_notifier.py:87-133` but has ZERO callers
- [ ] **Design human-in-the-loop mechanism** — currently no way for operators to approve/reject actions

---

### 5. Testing (Zero Tests Exist)

**Why:** Bugs like ImportError and wrong method names exist precisely because there are no tests.

- [ ] **Unit tests for all 8 conditional edge functions**
  - **File to create:** `agents/orchestrator/tests/test_conditions.py`
  - **How:** Test each function with various state dicts, verify correct routing
- [ ] **Unit tests for all tool classes**
  - **Files to create:** Tests for `FlapDetector`, `BSIDAllocator`, `DedupChecker`, `PCASLAClient`, `KGDijkstraClient`, `CNCTunnelClient`
  - **How:** Mock Redis/HTTP, test business logic
- [ ] **Integration tests for all 9 workflows**
  - **How:** Mock A2A calls, run each workflow with test state, verify final state
- [ ] **Test the config loader env var substitution**
  - **File to create:** `agent_template/tests/test_config_loader.py`

---

### 6. Deployment Infrastructure

**Why:** No way to run the 9-agent system locally or in production.

- [ ] **Create `docker-compose.yaml`**
  - **Services:** All 9 agents + Redis + PostgreSQL + optional Elasticsearch + OTEL collector
  - **Network aliases:** Must match URL defaults in configs (`event-correlator`, `service-impact`, etc.)
  - **Secrets:** Inject via `.env` file or Docker secrets
  - **Verification:** `docker-compose up` starts all services, health checks pass
- [ ] **Create Kubernetes manifests**
  - **Resources per agent:** Deployment, Service, ConfigMap, Secret
  - **Add NetworkPolicy** to restrict inter-agent communication to defined paths
- [ ] **Build `agent_template` as proper Python wheel**
  - **Problem:** Currently installed as editable (`pip install -e .`) which depends on source at exact path
  - **How:** `python -m build` → install wheel in Dockerfile
- [ ] **Create `requirements.lock`**
  - **How:** `pip-compile pyproject.toml -o requirements.lock` for reproducible builds
- [ ] **Wire OpenTelemetry instrumentation**
  - **Problem:** Config says `otel.enabled: true` but zero instrumentation code exists
  - **How:** Add `opentelemetry-instrumentation-httpx` and `opentelemetry-instrumentation-fastapi` auto-instrumentation

---

### 7. Documentation Discrepancies

- [ ] **Reconcile hold timer values**: `config.yaml` says platinum=60s, `WORKFLOW.md` says platinum=30s
- [ ] **Clarify Event Correlator entry point**: WORKFLOW.md says it's the entry point, but code has Orchestrator calling it
- [ ] **Add Audit Agent to all phase transitions**: DESIGN.md says log every transition, but only `close_node` calls Audit

---

## 📁 Files Changed by Claude Code (Reference)

| File | Change Type |
|------|------------|
| `agents/orchestrator/nodes/__init__.py` | Added `check_dampen_complete` export |
| `agents/orchestrator/nodes/conditions.py` | Already had the function (no change) |
| `agents/event_correlator/nodes/flap_detect_node.py` | Fixed method names |
| `agents/event_correlator/tools/flap_detector.py` | Added `get_flap_count()` method |
| `agents/tunnel_provisioning/workflow.py` | Added retry node with `check_can_retry` |
| `agent_template/main.py` | Replaced `asyncio.run()` with FastAPI lifespan |
| `agent_template/config_loader.py` | Added `agents` field to `Config` model |
| `.gitignore` | Added comprehensive exclusions |
| `agents/event_correlator/Dockerfile` | Added non-root user |
| `agents/service_impact/Dockerfile` | Added non-root user |
| `agents/path_computation/Dockerfile` | Added non-root user |
| `agents/tunnel_provisioning/Dockerfile` | Added non-root user |
| `agents/restoration_monitor/Dockerfile` | Added non-root user |
| `agents/traffic_analytics/Dockerfile` | Added non-root user |
| `agents/notification/Dockerfile` | Added non-root user |
| `agents/audit/Dockerfile` | Added non-root user |

## ⚠️ Known Risks & Considerations

1. **Simulation code removal must be coordinated** — don't remove simulations until real API integrations are tested. Consider gating behind `SIMULATE_MODE=true`.
2. **asyncio lifecycle fix changes startup order** — all agents now initialize inside FastAPI lifespan instead of before uvicorn. Test each agent individually.
3. **Tunnel retry fix changes graph topology** — new `retry_gate` node added between `create_tunnel` failure and retry/give-up decision.
4. **Redis connections** — ensure Redis is running and accessible before starting agents.

## 📞 If Issues Arise

1. **Rollback auto-fixes:** `git checkout -- <file>` to revert any individual fix
2. **ImportError on startup:** Check `__init__.py` exports match `workflow.py` imports
3. **Redis connection failures:** Verify `REDIS_URL` env var and Redis service availability
4. **CNC API failures:** Ensure `CNC_BASE_URL`, `CNC_USERNAME`, `CNC_PASSWORD` are set correctly
