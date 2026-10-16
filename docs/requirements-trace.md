# Requirements trace

Every MUST in the requirements, where it is implemented, how it is proven.
Rule: write **Expected** before running the check. Fill **Actual** after. Status is `pass` only with evidence.

Status values: `todo`, `in progress`, `pass`, `fail`.

## Definition of Done (the live demo)

| ID | Check | Expected (write before running) | Actual | Evidence | Status |
|---|---|---|---|---|---|
| DOD-01 | Storefront: add product to cart, checkout with COD or dummy gateway | Kapardhi checked out in a browser at http://store.localhost/ on 2026-10-16 | Order 12 created, payment method `cod` (Cash on delivery), total 19.99 USD, line item `Demo Widget` x1 sku `DEMO-WIDGET-1` | `wc_get_orders()` via `kubectl exec` on the WordPress pod | pass |
| DOD-02 | Order from DOD-01 visible in WooCommerce admin | WooCommerce 11.2.1 admin | Order 12 status `processing`, created 2026-10-16T15:37:15Z. Admin URL `http://store.localhost/wp-admin/admin.php?page=wc-orders&action=edit&id=12`. Orders list route returns 302 to `wp-login.php` when unauthenticated, which confirms the route exists and is protected. Orders use WooCommerce legacy post storage, not HPOS; `wc_get_orders()` is storage-agnostic and was used for this check. | WP-CLI-equivalent PHP via `kubectl exec`, output in `docs/build-log.md` | pass |
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
| MCP Python SDK client vs old-only upstream | mcp 2.3.0 client, mcp 1.28.1 server | 2025-11-25 (fell back) | yes | yes | yes |

**Actual, 2026-10-16.** Three of four rows measured. Cursor is not installed on this machine. Claude Code connected, ran `server/discover`, `tools/list`, `prompts/list`, `resources/list` and `subscriptions/listen`, which is what the protocol columns record; its `tools/call` was not completed because a nested `claude -p` failed with an expired OAuth session, a harness limit rather than a protocol problem.

**Key result, client side (2026-10-16 follow-up).** The 2.3.0 client falls back to 2025-11-25 against an upstream running mcp 1.28.1: it probes `server/discover` on 2026-07-28, downgrades to the full `initialize` handshake, manages the session and sends `DELETE` to close it. Evidence: `spikes/d001-mcp-version/requests_old.jsonl`.

**Key result.** One SDK 2.3.0 server served both protocol versions at the same time with no special handling: stateless 2026-07-28 for Claude Code and the Python SDK, and an old-style session on 2025-11-25 for the Inspector. Evidence: `spikes/d001-mcp-version/requests.jsonl` and `spikes/d001-mcp-version/README.md`.

Facts from the SDK before running, `mcp==2.3.0`: `LATEST_PROTOCOL_VERSION = 2026-07-28`, `MODERN_PROTOCOL_VERSIONS = ('2026-07-28',)`, `DEFAULT_NEGOTIATED_VERSION = 2025-03-26`. Source: https://pypi.org/project/mcp/ and the installed package.

This spike does not decide D-001. It supplies the measurements.

## Store chart bring-up (DOD-01, DOD-02)

Pre-registered 2026-10-16, before `charts/store` was installed. Chart targets DOD-01 and DOD-02 on k3d.

| # | Check | Expected | Actual | Result |
|---|---|---|---|---|
| SC-1 | `helm lint charts/store` | clean, 0 failures | 0 chart(s) failed, local and prod values | pass |
| SC-2 | `scripts/check-charts.sh` | PASS portability, PASS prod leakage | both PASS, exit 0 | pass |
| SC-3 | `kubectl get pods` | all pods Ready | db 1/1, wp 1/1, bootstrap Completed | pass |
| SC-4 | `kubectl get pvc` | both PVCs Bound | `data-store-store-db-0`, `store-store-wp-content`, both Bound 2Gi local-path | pass |
| SC-5 | bootstrap Job | Completed | `Complete 1/1` in 2m10s; WooCommerce 11.2.1 active, product 11 created | pass |
| SC-6 | `curl -I http://store.localhost/` | HTTP 200 | `HTTP/1.1 200 OK`, Apache/2.4.68 | pass |
| SC-7 | re-run `helm upgrade` | Job Completed, no duplicate product | revision 2, Job `Complete 1/1`; every stateful step logged SKIP; still exactly 1 product (id 11) | pass |
| SC-8 | delete both pods | sample product still exists | both pods returned; product 11 `Demo Widget` sku `DEMO-WIDGET-1` price 19.99, count=1; storefront still 200 | pass |

Routing confirmed after SC-8: `/shop/` 200, `/cart/` 200, `/demo-widget/` 301 to the canonical `/product/demo-widget/` which returns 200, `/checkout/` 302 to cart (normal WooCommerce behaviour for an empty cart).

**Bug found and fixed during SC-5.** The first install failed with `database not reachable after 5 minutes` while MariaDB was healthy and `1/1 Running`. The `wordpress:cli` image ships wp-cli but not WordPress core, and the Job mounted only `wp-content`, so there was no `wp-config.php` and every `wp` command failed for want of configuration rather than connectivity. Fixed by giving the Job an `emptyDir` scratch root, `wp core download --skip-content` pinned to the serving image's 7.1.3, then `wp config create` with the database settings passed explicitly. `--skip-content` keeps the shared `wp-content` volume untouched.

DOD-01 (browser checkout) is Kapardhi's to run. DOD-02 (order visible) is verified with WP-CLI afterwards.

## VPS bring-up (K-02 prod half)

Pre-registered 2026-10-16, before k3s was installed. See D-016.

Host: GCP `gw-prod`, project `mcp-kb8`, zone `asia-south1-a`, e2-standard-2, 50 GB pd-balanced,
Ubuntu 24.04 LTS amd64, static IP `34.93.101.10`. SSH only through IAP TCP forwarding
(`35.235.240.0/20`, tag `k3s-prod`); no public SSH port and `default-allow-ssh` deleted.

| # | Check | Expected | Actual | Result |
|---|---|---|---|---|
| VPS-1 | `kubectl get nodes` | 1 node, Ready | `gw-prod.asia-south1-a.c.mcp-kb8.internal  Ready  control-plane  v1.35.5+k3s1` | pass |
| VPS-2 | k3s version | `v1.35.5+k3s1`, matching local k3d | `k3s version v1.35.5+k3s1 (6a4781ad)`; local k3d node also `v1.35.5+k3s1` | pass |
| VPS-3 | `kubectl get pods -n kube-system` | traefik Running | `traefik-9bcdbbd9-6bgqf 1/1 Running`, `svclb-traefik 2/2 Running`; ingressclass `traefik` present | pass |
| VPS-4 | `kubectl get storageclass` | `local-path` marked (default) | `local-path (default)  rancher.io/local-path` | pass |
| VPS-5 | kubeconfig at `~/.kube/gw-prod.yaml` | outside the repo, server over an SSH tunnel, not an open 6443 | file is `0600` outside the repo, `server: https://127.0.0.1:16443`; `kubectl get nodes` works through `gcloud compute ssh --tunnel-through-iap -- -N -L 16443:localhost:6443`; `curl https://34.93.101.10:6443` from the internet returns nothing | pass |

**Host verified.** `x86_64`, 2 CPUs, 7.7 GiB RAM, Ubuntu 24.04.5 LTS, 48 GB root. Local and prod now run the same k3s, `v1.35.5+k3s1`, which is what K-02 needs.

**To reopen the tunnel after a reboot:**

```
gcloud compute ssh gw-prod --project=mcp-kb8 --zone=asia-south1-a --tunnel-through-iap -- -N -L 16443:localhost:6443
KUBECONFIG=~/.kube/gw-prod.yaml kubectl get nodes
```

Ports 80 and 443 are not open yet. 6443 is never opened.

## Kubernetes and Helm

| ID | Requirement | Implemented in | Evidence | Status |
|---|---|---|---|---|
| K-01 | Runs on local Kubernetes (D-002) | k3d cluster `gw-local` on Colima (D-017) | 2026-10-15: node Ready, k3s `v1.35.5+k3s1`, Traefik Running, `local-path (default)`, `traefik` ingressclass. 2026-10-16: `charts/store` installed and serving at http://store.localhost/ (SC-1 to SC-8 all pass). Becomes `pass` when the gateway, Woo MCP server and dashboard also run. | in progress |
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
