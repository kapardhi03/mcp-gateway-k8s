# Requirements trace

Every MUST in the requirements, where it is implemented, how it is proven.
Rule: write **Expected** before running the check. Fill **Actual** after. Status is `pass` only with evidence.

Status values: `todo`, `in progress`, `pass`, `fail`.

## Definition of Done (the live demo)

| ID | Check | Expected (write before running) | Actual | Evidence | Status |
|---|---|---|---|---|---|
| DOD-01 | Storefront: add product to cart, checkout with COD or dummy gateway | | | | todo |
| DOD-02 | Order from DOD-01 visible in WooCommerce admin | | | | todo |
| DOD-03 | User A, chat agent: create product with name and price, it appears on storefront | | | | todo |
| DOD-04 | User A: place order by hand, ask agent "what orders came in today", it returns that order | | | | todo |
| DOD-05 | User B: external client connects with only gateway URL + B's key, sees tools of every enabled server | | | | todo |
| DOD-06 | User B: same orders question succeeds | | | | todo |
| DOD-07 | User B: one prompt uses tools from two different upstream servers | | | | todo |
| DOD-08 | Revoke B's key, next call rejected | | | | todo |
| DOD-09 | Disable one upstream, its tools disappear from chat agent and external client | | | | todo |
| DOD-10 | Kill one upstream pod, others keep working, dashboard shows it Unreachable | | | | todo |
| DOD-11 | Every call above in audit log, attributed to the right user | | | | todo |

## D-001 spike: which MCP protocol version do real clients send?

Pre-registered 2026-10-16, before the spike ran. Spike lives in `spikes/d001-mcp-version/`.

**Expected.** Each client completes `echo`. Recorded per client: protocol version, initialize yes/no, session ID yes/no.

| Client | Client version | Protocol version | initialize | Session ID | echo worked |
|---|---|---|---|---|---|
| Claude Code | 2.1.278 | 2026-07-28 | no | no | not measured, nested auth failed |
| MCP Inspector (CLI) | 2.11.0 | 2025-11-25 | yes | yes | yes |
| Cursor | not installed | n/a | n/a | n/a | skipped |
| MCP Python SDK client | mcp 2.3.0 | 2026-07-28 | no | no | yes |

**Actual, 2026-10-16.** Three of four rows measured. Cursor is not installed on this machine. Claude Code connected, ran `server/discover`, `tools/list`, `prompts/list`, `resources/list` and `subscriptions/listen`, which is what the protocol columns record; its `tools/call` was not completed because a nested `claude -p` failed with an expired OAuth session, a harness limit rather than a protocol problem.

**Key result.** One SDK 2.3.0 server served both protocol versions at the same time with no special handling: stateless 2026-07-28 for Claude Code and the Python SDK, and an old-style session on 2025-11-25 for the Inspector. Evidence: `spikes/d001-mcp-version/requests.jsonl` and `spikes/d001-mcp-version/README.md`.

Facts from the SDK before running, `mcp==2.3.0`: `LATEST_PROTOCOL_VERSION = 2026-07-28`, `MODERN_PROTOCOL_VERSIONS = ('2026-07-28',)`, `DEFAULT_NEGOTIATED_VERSION = 2025-03-26`. Source: https://pypi.org/project/mcp/ and the installed package.

This spike does not decide D-001. It supplies the measurements.

## Kubernetes and Helm

| ID | Requirement | Implemented in | Evidence | Status |
|---|---|---|---|---|
| K-01 | Runs on local Kubernetes (D-002) | k3d cluster `gw-local` on Colima (D-017) | 2026-10-15: node `k3d-gw-local-server-0` Ready, k3s `v1.35.5+k3s1`. Traefik pod Running. `local-path (default)` storageclass. `traefik` ingressclass. `curl -sI http://localhost` returns 404 from Traefik. Full results in `docs/build-log.md`. Becomes `pass` only when the full stack runs on it. | in progress |
| K-02 | Same charts deploy to k3s VPS, values-only differences | | Pre-registered (2026-10-16), before charts exist: run `scripts/check-charts.sh`. Expected: both checks PASS (portability, prod leakage). Script verified on 2026-10-16 to FAIL on a bad fixture, PASS on a clean one, and SKIP with no charts. See D-002. | todo |
| K-03 | Helm only, `values-local.yaml` and `values-prod.yaml` | | | todo |
| K-04 | Everything in cluster: store, DB, Woo MCP, gateway, dashboard | | | todo |
| K-05 | Persistent storage for store DB and WordPress content | | | todo |
| K-06 | Storefront and dashboard via Ingress, stable URLs (D-003) | | | todo |
| K-07 | Local domain approach documented (D-004) | | | todo |
| K-08 | Readiness and liveness probes on every workload | | | todo |
| K-09 | Requests and limits on every workload | | | todo |
| K-10 | No hardcoded secrets, credentials in Kubernetes Secrets | | | todo |

## WooCommerce MCP server

| ID | Requirement | Implemented in | Evidence | Status |
|---|---|---|---|---|
| W-01 | Written by me, no existing Woo MCP server or plugin | | | todo |
| W-02 | Streamable HTTP (D-001) | | | todo |
| W-03 | Tool: list products | | | todo |
| W-04 | Tool: create product | | | todo |
| W-05 | Tool: list orders | | | todo |
| W-06 | Tool: get order | | | todo |
| W-07 | Tool: update order status | | | todo |
| W-08 | Not reachable from outside the cluster | | | todo |
| W-09 | Store access method documented with reason (D-006) | | | todo |

## Gateway

| ID | Requirement | Implemented in | Evidence | Status |
|---|---|---|---|---|
| G-01 | Admin add, edit, disable, remove upstreams with optional static credential | | | todo |
| G-02 | One MCP endpoint, list returns tools of all enabled servers | | | todo |
| G-03 | Calls routed to the right server | | | todo |
| G-04 | Name collision scheme documented (D-009) | | | todo |
| G-05 | Slow or dead upstream does not break listing or other calls | | | todo |
| G-06 | Call timeouts with a clear error | | | todo |
| G-07 | Upstream credentials never sent to browser or MCP client | | | todo |
| G-08 | At least three upstreams connected (D-010) | | | todo |
| G-09 | Server status shown: Connected / Unreachable / Disabled, with tools | | | todo |
| G-10 | Woo MCP server pre-registered as first server | | | todo |

## Team and access

| ID | Requirement | Implemented in | Evidence | Status |
|---|---|---|---|---|
| T-01 | Roles: admin and member | | | todo |
| T-02 | Admin invites members (D-012) | | | todo |
| T-03 | Per-user API key, member can generate own | | | todo |
| T-04 | Keys revocable and stored hashed (D-013) | | | todo |
| T-05 | Audit log: user, server, tool, timestamp, duration, outcome | | | todo |
| T-06 | Audit log visible in dashboard | | | todo |

## Chat agent

| ID | Requirement | Implemented in | Evidence | Status |
|---|---|---|---|---|
| C-01 | Uses an LLM to call tools through the gateway (D-011) | | | todo |
| C-02 | Shows which tools it called | | | todo |
| C-03 | Acts as logged-in user, audited under that user (D-014) | | | todo |
| C-04 | LLM key in a Secret | | | todo |

## Release deliverables

| ID | Deliverable | Location | Status |
|---|---|---|---|
| S-00 | Repo set to public before the form is submitted (D-018) | GitHub `kapardhi03/mcp-gateway-k8s` | todo |
| S-01 | README: local setup | | todo |
| S-02 | README: VPS / k3s setup | | todo |
| S-03 | README: place an order, connect external client, use chat agent | | todo |
| S-04 | Source: dashboard, gateway, Woo MCP server, chat agent | | todo |
| S-05 | Helm charts + values-local + values-prod | | todo |
| S-06 | System design and tradeoffs note | `docs/design-and-tradeoffs.md` | todo |
| S-07 | Threat model note (4 required topics) | `docs/threat-model.md` | todo |
| S-08 | List of stretch goals attempted | | todo |
| S-09 | Demo video covering all 6 required sections | | todo |
| S-10 | Released: repo public, demo video posted | | todo |
