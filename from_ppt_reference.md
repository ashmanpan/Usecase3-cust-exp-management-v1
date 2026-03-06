# Reference PPT — Key Technical Concepts & Gap Analysis

> Extracted from 3 PPTs in `refrence PPT/` and compared against CEM agent codebase.
> Date: 2026-03-06

---

## Source PPTs

| File | Topic |
|------|-------|
| `SR-PM-Strategy.pptx` | SR Performance Measurement — delay/loss/liveness probes, MDT/EDT telemetry |
| `SR-SRv6-TDM.pptx` | SR/SRv6 Traffic Demand Matrix — BGP-LS, SID types, color steering |
| `SR-PCE and SR-TE in Multi-AS.pptx` | SR-PCE path computation — ODN, Flex-Algo, PCEP, multi-domain |

---

## Part 1: Key Concepts from PPTs

### SR Performance Measurement (SR-PM)

#### Probe Types & Standards
- **STAMP** (RFC 9503) — standard probe format with Alternate Marking
- **TWAMP-lite** (RFC 5357) — baseline two-way probe encoding
- **Alternate Marking** (RFC 9341) — flow-label-based absolute loss detection (not approximation)
- **One-way delay** — requires PTP timing; eliminates return-path exposure
- **Two-way / Loopback** — no PTP needed; probe returns via SRv6 BSID or SID list

#### Metrics & Statistical Measures
- Min / Max / Avg / Median latency
- **28-bin latency histogram** — full distribution per probe (not just averages)
- **EMA Loss** (Exponential Moving Average)
- **EMA Latency** (Exponential Moving Average)
- Delay-Anomaly / Loss-Anomaly — named flag states
- Packet counters (TX/RX per probe session)
- Rolling-average-delay

#### Configurable Intervals
| Parameter | Default | Range |
|-----------|---------|-------|
| computation-interval | 30s | 1-3600s |
| burst-interval | 3s | 30-15000ms |
| advertisement-interval | 120s | 30-3600s |
| advertisement-threshold | 10% | 0-100% |
| accelerated-threshold | 20% | 0-100% -- fast re-adv on significant change |
| minimum-change | 500us | 0-100000us |

#### Scale & Performance (Silicon One)
- **14 Million Probes Per Second** — per device, per direction
- **1 measurement every millisecond** — per ECMP path
- **ECMP path discovery** — all equal-cost paths measured independently
- **Bundle member visibility** — per-link inside LAG (roadmap 1HCY26)
- HW timestamping — measures optical distance

#### Liveness Detection Timings
| Scope | Detection Time |
|-------|---------------|
| SR Policy endpoint (complete) | < 10ms |
| SR Policy path (partial) | ~10ms |
| All atomic paths | ~300ms |
| HW offload | ~3ms |

#### MDT Telemetry Sensor Path
```
Cisco-IOS-XR-perf-meas-oper:performance-measurement/nodes/node/
  ipm-receivers/ipm-receiver-metrics/ipm-receiver-metric
```
Fields: session-id, SA, DA, VRF, SP, DP, timestamp, EMA loss/latency,
**28-bin histogram array** with min/max latency per bin.

---

### SR-PCE / SR-TE

#### SR Policy Tuple
- **(Head-End, Color, End-Point)** — uniquely identifies an SR Policy
- **Color** — numeric, from RFC 5512 / RFC 9012 BGP Color Extended-Community
- **Binding SID (BSID)** — label for policy forwarding
- **Preference** — candidate path priority (0-4294967295)

#### Path Computation Types
| Type | Description |
|------|-------------|
| Distributed | Head-end computes locally (CSPF) |
| Centralized (PCE) | Delegated via PCEP (TCP 4189) |
| ODN | Auto-triggered by BGP route arrival |
| Flex-Algo | RFC 9350 constraint-based (metric + affinity) |

#### ODN (On-Demand Next-Hop)
- Single SR Policy covers all endpoints of a service class
- Auto-instantiated when BGP route with matching color arrives
- Works with: IPv4 BGP, 6PE, VPNv4, VPNv6, EVPN

#### Flex-Algo (RFC 9350)
- Instance IDs: 128-255 (user-defined)
- Minimize IGP metric while avoiding links with specific affinity
- Per-link colors flooded in IGP

#### PCEP Details
- TCP port 4189
- PCC (head-end) to PCE (compute engine)
- Multiple PCE -- precedence-based failover (e.g., precedence 100, 102)

#### SRLG and Constraints
- SRLG (Shared Risk Link Group) -- links sharing physical risk
- Disjoint paths -- node-disjoint / link-disjoint / SRLG-disjoint
- Link affinity -- per-link color bits (encrypted/reliable/unreliable)

#### BGP Steering Priority (Color)
1. Exact (endpoint, color) SR Policy match
2. Dynamic path + constraints for (endpoint, color)
3. Flex-Algo prefix-SID of BGP next-hop
4. IGP shortest path to BGP next-hop

---

### Traffic Demand Matrix (TDM)

#### Data Sources for TDM
- **BGP RIB** — all service routes with color extended-communities
- **IGP topology** — node/link metrics
- **BGP-LS** (afi=16388, safi=71) — distributed link-state database
  - Only one BGP-LS speaker required per domain
  - Carries IS-IS / OSPF topology to PCE
  - Instance-id per domain (e.g., 32 = domain 1, 33 = domain 2)

#### SID Types
| SID Type | Description |
|----------|-------------|
| Prefix-SID | IGP loopback -- SRGB-base + index (e.g., index 65 -> label 16065) |
| Node-SID | Prefix-SID on loopback (BGP next-hop) |
| Adjacency-SID | Per-link, local significance, protected/unprotected pair |
| uSID (micro-SID) | Compressed SRv6 SID |
| End Function SID | SRv6 IPv6 prefix (e.g., fcbb:bb00:5::1) |

#### SRGB (Segment Routing Global Block)
- Single SRGB shared across all IGP instances + BGP
- Prefix-SID index unique domain-wide
- Mapping Server -- advertises SIDs on behalf of non-SR nodes

#### Color Extended-Community (RFC 5512 / RFC 9012)
- Standard BGP attribute on service routes
- Numeric color value maps to SR Policy intent
- If multiple colors on route -> use numerically highest

---

### Telemetry & Data Sources

| Source | Protocol | Data |
|--------|----------|------|
| MDT | gRPC / GNMI | Histogram, min/max/avg/variance delay/loss (periodic) |
| EDT | gRPC / GNMI | Anomaly-triggered alerts (threshold breach) |
| NetFlow / IPFIX | UDP | Flow records with SRv6 SID |
| BGP-LS | BGP | Link-state topology database |
| IOAM | In-packet | Hop-by-hop telemetry in packet headers |
| Path Tracing (MCD) | In-packet | Midpoint Compressed Data -- actual path taken |

#### EDT (Event-Driven Telemetry)
- Fires when threshold breached (delay-anomaly, loss-anomaly, liveness-loss)
- Push-based -- no polling needed

---

### Multi-Domain / Multi-AS

#### Topology Distribution
- Each domain advertises BGP-LS with unique instance-id
- Route Reflector aggregates all domain BGP-LS into PCE TED
- Full multi-domain topology visible at PCE

#### Inter-Domain Boundaries
- ABR (Area Border Router) -- OSPF area boundary
- ASBR (AS Border Router) -- BGP AS boundary
- SID values per-domain -- cross-domain needs SID stitching

---

## Part 2: Gap Analysis vs Codebase

### IMPLEMENTED

| Concept | File | Notes |
|---------|------|-------|
| Platinum 30ms / Gold 60ms SLA | restoration_monitor/tools/pca_client.py | Exact values from PPT |
| Silver 100ms / Bronze 150ms | same | |
| SRLG avoidance in path computation | path_computation/tools/constraint_builder.py | In relaxation order |
| Disjoint paths (node/link/SRLG) | path_computation/schemas/paths.py | Fully modelled |
| Binding SID allocation | tunnel_provisioning/tools/bsid_allocator.py | Redis-backed lifecycle |
| SR Policy color field in schema | tunnel_provisioning/schemas/tunnels.py | Field exists |
| PE-to-PE demand matrix | traffic_analytics/tools/demand_matrix_builder.py | NetFlow + SRPM sources |
| CNC SSE notifications (alt to EDT) | event_correlator/tools/cnc_notification_subscriber.py | Push-based, functional |
| CNC Topology API (alt to BGP-LS) | path_computation/tools/cnc_topology_client.py | Live IGP data |
| NetFlow / IPFIX collection | traffic_analytics/tools/telemetry_collector.py | SRv6 SID extraction |
| SRPM client stub | path_computation/tools/srpm_client.py | Enable via SRPM_ENABLED=true |

---

### PARTIAL / STUB

| Concept | File | What's Missing |
|---------|------|---------------|
| MDT gRPC streaming | traffic_analytics/tools/telemetry_collector.py | Stub only -- no gRPC client, no sensor path |
| GNMI subscription | traffic_analytics/config.yaml | Config placeholder only, no client code |
| SRPM per-link metrics | path_computation/tools/srpm_client.py | Gated by SRPM_ENABLED; SR not live until Sept 2026 |
| Color steering enforcement | tunnel_provisioning/schemas/tunnels.py | Field in schema but not applied to BGP steering logic |

---

### MISSING -- Not in Codebase

#### SR Performance Measurement
| Gap | Impact | Priority |
|-----|--------|----------|
| STAMP/TWAMP-lite probe parsing (RFC 9503/5357) | Relies on PCA pre-aggregation -- cannot parse raw IOS XR probe data | MEDIUM |
| 28-bin latency histogram processing | Only scalar metrics (latency_ms, jitter_ms) -- no distribution | MEDIUM |
| EMA for loss/latency | No smoothed trending -- single spike can trigger false remediation | MEDIUM |
| delay-anomaly / loss-anomaly state flags | No named anomaly states from IOS XR | LOW |
| computation-interval / burst-interval config | No adaptive probe frequency | LOW |
| Accelerated advertisement (20% change) | No fast re-advertisement on significant metric change | LOW |
| Liveness detection < 10ms | No sub-10ms liveness probing | LOW |
| EDT native subscription | Using CNC SSE instead -- functional but not native IOS XR EDT | LOW |

#### SR-TE / SR-PCE
| Gap | Impact | Priority |
|-----|--------|----------|
| ODN -- auto policy from BGP route | Manual policy config required; no automated service-triggered provisioning | HIGH |
| Color extended-community enforcement in steering | Color in schema but not applied to BGP route steering decisions | HIGH |
| Flex-Algo (RFC 9350) in path computation | Cannot request delay-optimized or affinity-constrained algorithm paths | HIGH |
| PCEP protocol (TCP 4189) | No native PCE/PCC communication -- using REST/HTTP only | MEDIUM |
| Multiple PCE failover | Single KG endpoint -- no redundancy | MEDIUM |
| ECMP path enumeration | No multi-path tracking -- only primary path | MEDIUM |

#### Traffic Demand Matrix
| Gap | Impact | Priority |
|-----|--------|----------|
| BGP-LS (afi=16388, safi=71) native | Using CNC Topology API instead -- functional but abstracted | MEDIUM |
| SID type classification | Generic segment_sids: List[int] -- no type metadata | LOW |
| SRGB discovery / label validation | Hard-coded BSID ranges only | LOW |
| Mapping Server support | Non-SR nodes invisible to demand matrix | LOW |

#### Multi-Domain / Multi-AS (Future)
| Gap | Impact | Priority |
|-----|--------|----------|
| BGP-LS instance-id per domain | No domain-aware topology separation | HIGH (future) |
| ABR / ASBR boundary handling | No cross-domain path computation | HIGH (future) |
| Cross-domain SID stitching | Cannot build multi-domain SID paths | HIGH (future) |
| Multi-domain PCE with state-sync | Single PCE/KG only | HIGH (future) |

---

## Part 3: Recommended Next Actions

### Immediate (Current Jio/Geo RSVP-TE)
1. Wire Color extended-community into service steering (color field exists in tunnels.py but not applied)
2. Add EMA smoothing to SLA metrics (prevents false positive remediation from single spike)
3. MDT gRPC client -- replace simulation stub with real Cisco-IOS-XR-perf-meas-oper GNMI subscription

### Short-Term (Before SR Migration -- Sept 2026)
4. ODN color to SR Policy auto-mapping -- auto-create policy when BGP route with matching color arrives
5. Flex-Algo support -- add algorithm ID to constraint_builder.py
6. ECMP path enumeration -- enumerate all equal-cost paths

### SR Phase (Sept 2026)
7. Enable SRPM via SRPM_ENABLED=true -- already stubbed
8. 28-bin histogram ingestion from MDT
9. Multi-domain readiness -- BGP-LS instance-id, ABR/ASBR handling, SID stitching

---

## Summary Count

| Status | Count |
|--------|-------|
| Implemented | 11 |
| Partial / Stub | 4 |
| Missing -- near-term | 14 |
| Missing -- multi-domain / future | 4 |
| Total concepts reviewed | 33 |

---

## Part 4: Crosswork API Inventory (from developer.cisco.com)

All available Crosswork Network Controller 7.1 APIs reviewed against codebase.

### Crosswork Active Topology APIs

| API | Status | Code Location |
|-----|--------|---------------|
| Service Inventory API | ADDED | `service_impact/tools/cnc_client.py` — 7 new RPC methods |
| IETF L3VPN Service Operational Data | ADDED | `cnc_client.py` — `get_l3vpn_service()` via RESTCONF |
| IETF L3VPN Service Config | ADDED | `cnc_client.py` — GET/PUT/PATCH/DELETE RESTCONF |
| Cisco SR-TE Policy Service Config | ADDED | `tunnel_provisioning/tools/cnc_srte_config_client.py` — NEW |
| IETF TE (RSVP-TE) Service Config | PARTIAL | `cnc_tunnel.py` covers create/delete; full RESTCONF CRUD pending |
| IETF L2VPN Service Operational Data | MISSING | Not implemented |
| IETF L2VPN Service Config | MISSING | Not implemented |
| Cisco Circuit-Style SR-TE Policy | MISSING | Not implemented |
| IETF Network Slice Service Config | MISSING | Not implemented |
| CAT NSO Connector API | PARTIAL | `cnc_tunnel.py` uses NSO REST directly |
| CAT FP Deployment Manager | MISSING | Not implemented |

### Crosswork Optimization Engine APIs

| API | Status | Code Location |
|-----|--------|---------------|
| SR Policy Operations API | PARTIAL | `cnc_tunnel.py` — PCE REST for SR policy create/delete |
| RSVP-TE Tunnel Operations API | PARTIAL | `cnc_tunnel.py` — NSO-initiated create/delete |
| Performance Metrics API | MISSING | Not implemented — needed for traffic_analytics agent |
| SR P2MP Policy Operations | MISSING | Not in scope |
| LCM / OAM / OPM Operations | MISSING | Not in scope |

### Crosswork Service Health APIs

| API | Status | Code Location |
|-----|--------|---------------|
| Probe Manager API | MISSING | PCA used instead via `restoration_monitor/tools/pca_client.py` |
| Historical Data API | MISSING | Not implemented |
| Assurance Graph API | MISSING | Not implemented — useful for graph-based SLA view |
| Heuristic Packages API | MISSING | Not in scope |

### New Files Added (2026-03-06)

| File | Purpose |
|------|---------|
| `agents/tunnel_provisioning/tools/cnc_srte_config_client.py` | SR-TE Policy RESTCONF CRUD (Crosswork Active Topology) |

### Updated Files (2026-03-06)

| File | Changes |
|------|---------|
| `agents/service_impact/tools/cnc_client.py` | Added Service Inventory API (7 RPCs), L3VPN RESTCONF, sub-service methods |
| `agents/tunnel_provisioning/tools/__init__.py` | Exported CNCSRTEConfigClient |

### Key Gaps Still Remaining After This Update

1. **Performance Metrics API** (Optimization Engine) — needed for `traffic_analytics` link utilization data
2. **Assurance Graph API** (Service Health) — graph-based SLA topology view
3. **Historical Data API** (Service Health) — trend analysis for SLA data
4. **L2VPN Service APIs** — L2VPN services not queried (only L3VPN)
5. **IETF TE RSVP-TE Service Config** — full RESTCONF CRUD missing (create via NSO, not RESTCONF)
