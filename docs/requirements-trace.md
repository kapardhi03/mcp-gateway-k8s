# Requirements trace

Every MUST in the requirements, where it is implemented, how it is proven.
Rule: write **Expected** before running the check. Fill **Actual** after. Status is `pass` only with evidence.

Status values: `todo`, `in progress`, `pass`, `fail`.

**Rule for Job checks.** A Kubernetes Job row is `pass` only when `status.failed == 0`, verified
with `scripts/check-cluster.sh`. `Complete` on its own is not evidence: a Job with a `backoffLimit`
reports `Complete` as soon as one pod succeeds, no matter how many failed first. This caught a real
bug on 2026-10-17, where the store bootstrap Job reported `Complete 1/1` while its first pod had
died on `wp option update gmt_offset`.

## Definition of Done (the live demo)

| ID | Check | Expected (write before running) | Actual | Evidence | Status |
|---|---|---|---|---|---|
| DOD-01 | Storefront: add product to cart, checkout with COD or dummy gateway | Kapardhi checked out in a browser at http://store.localhost/ on 2026-10-16 | Order 12 created, payment method `cod` (Cash on delivery), total 19.99 USD, line item `Demo Widget` x1 sku `DEMO-WIDGET-1` | `wc_get_orders()` via `kubectl exec` on the WordPress pod | pass |
| DOD-02 | Order from DOD-01 visible in WooCommerce admin | WooCommerce 11.2.1 admin | Order 12 status `processing`, created 2026-10-16T15:37:15Z. Admin URL `http://store.localhost/wp-admin/admin.php?page=wc-orders&action=edit&id=12`. Orders list route returns 302 to `wp-login.php` when unauthenticated, which confirms the route exists and is protected. Orders use WooCommerce legacy post storage, not HPOS; `wc_get_orders()` is storage-agnostic and was used for this check. | WP-CLI-equivalent PHP via `kubectl exec`, output in `docs/build-log.md` | pass |
| DOD-03 | User A, chat agent: create product with name and price, it appears on storefront | Pre-registered 2026-10-18. User A, signed in to the dashboard in a browser, types one sentence asking for a product with a given name and price. The chat agent calls `woo__create_product` **through the gateway**, shows which tool it called, and the product is then reachable on the storefront at its permalink with that name and price. The browser never calls a tool directly. | | | todo |
| DOD-04 | User A: place order by hand, ask agent "what orders came in today", it returns that order | Pre-registered 2026-10-18. An order placed in the storefront today, then User A asks the agent in plain English. The agent calls `woo__list_orders` with the date resolved in the **store's** timezone (Asia/Kolkata) and returns that order. An order from a previous day is not returned. | | | todo |
| DOD-05 | User B: external client connects with only gateway URL + B's key, sees tools of every enabled server | Pre-registered 2026-10-18. User B is a second, non-admin account that generated **its own** key in the dashboard. An external MCP client configured with only the gateway URL and that key lists all seven tools. No upstream URL and no upstream credential appear in B's client config. B's key is distinct from A's and from the bootstrap key. | | | todo |
| DOD-06 | User B: same orders question succeeds | Pre-registered 2026-10-18. The same orders question answered through B's key returns the same order as DOD-04, and the audit rows for it are attributed to **B**, not A and not bootstrap-admin. | | | todo |
| DOD-07 | User B: one prompt uses tools from two different upstream servers | Pre-registered 2026-10-18. One natural-language prompt from B causes calls to both `woo__*` and `fx__*` in the same answer, with the model choosing both unaided. Already evidenced for a bootstrap key in GW-4; this repeats it as user B. | | | todo |
| DOD-08 | Revoke B's key, next call rejected | Pre-registered 2026-10-18. An admin revokes B's key in the dashboard. B's very next call returns 401 and reaches no upstream. The rejection is audited. A's key keeps working, so revocation is per-key and not a global break. | | | todo |
| DOD-09 | Disable one upstream, its tools disappear from chat agent and external client | Pre-registered 2026-10-18. An admin disables fx in the dashboard. Its tools vanish from both the external client's `tools/list` and the chat agent's tool set, within the refresh window. The fx pod keeps running: this is a registry flag, not a scaling action. Re-enabling restores them. | | | todo |
| DOD-10 | Kill one upstream pod, others keep working, dashboard shows it Unreachable | Pre-registered 2026-10-18. `kubectl delete pod` on woo-mcp. `tools/list` still returns the fx tools within the per-upstream timeout, the chat agent still answers an fx question, and the dashboard's Servers page shows woo as `Unreachable` with a reason. Recovery is automatic once the pod is back. | | | todo |
| DOD-11 | Every call above in audit log, attributed to the right user | Pre-registered 2026-10-18. Every call made in DOD-03 to DOD-10 has an audit row carrying user, server, tool, timestamp, duration_ms and outcome, visible on the dashboard's Audit page. A's calls say A, B's say B. Chat turns additionally carry input and output token counts. Failures and rejections appear with failure outcomes, not silently. | | | todo |

## Security checks (SEC)

Pre-registered 2026-10-18, **before the team features, dashboard or chat agent existed**. These
cover threat-model ground the Definition of Done does not exercise directly.

| # | Check | Expected (written before the code exists) | Actual | Result |
|---|---|---|---|---|
| SEC-1 | Password storage | A dashboard password is stored as an argon2 hash. The stored value starts `$argon2`, differs for two users who choose the SAME password (so it is salted), and the plaintext appears nowhere in the database or any log. See D-012, D-013. | | todo |
| SEC-2 | Session cookie flags | The session cookie is `HttpOnly` and `SameSite=Lax` or stricter, so script cannot read it and a cross-site form post does not carry it. `Secure` is asserted as "set when the request is HTTPS" rather than unconditionally: local runs on plain HTTP, and an unconditional assertion would be either a false failure or a lie. | | todo |
| SEC-3 | Origin check | A state-changing POST carrying a foreign `Origin` header is rejected even with a valid session cookie. The same request with the correct Origin succeeds. This is the CSRF defence. | | todo |
| SEC-4 | Role enforcement | A `member` session is refused every admin-only action: inviting, revoking another user's key, enabling or disabling an upstream. Refusal is server-side, not merely a hidden button. | | todo |
| SEC-5 | Key isolation | User B cannot see, use or revoke user A's API key. A user sees only their own keys, and a raw key is shown exactly once, at creation, never again. | | todo |
| SEC-6 | Invite tokens | An invite token is single-use and expires. Re-using a consumed token fails, as does an expired one. The token is high-entropy and is not derived from the email address. | | todo |
| SEC-7 | Credentials never reach the browser | An upstream credential value appears in no dashboard response, no chat answer and no page source. Repeats GW-8's canary grep across the browser-facing surface. | | todo |
| SEC-8 | Secrets never logged | Grep every pod log for the LLM API key, the gateway bootstrap key, a user password and an upstream credential. Expected 0 hits for all four. | | todo |

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

**Updated 2026-10-17.** Ports 80 and 443 are now open, via firewall rule `allow-http-https`: `tcp:80,tcp:443` from `0.0.0.0/0` to target tag `k3s-prod` only, priority 1000. 22 is unchanged and still IAP-only (`allow-ssh-iap`, source `35.235.240.0/20`). 6443 is never opened.

## Store smoke deploy to the VPS (K-02 evidence)

Pre-registered 2026-10-17, before the prod host was set and before `helm install` ran on the VPS.
Same chart as local, values-only differences. Prod host `store.34.93.101.10.sslip.io` (see D-004 addendum).

| # | Check | Expected (written before running) | Actual | Result |
|---|---|---|---|---|
| SP-1 | `scripts/check-charts.sh` | PASS portability, PASS prod leakage, exit 0 | `PASS portability`, `PASS prod leakage`, exit 0 | pass |
| SP-2 | `git diff --no-index charts/store/values-local.yaml charts/store/values-prod.yaml` | The only differences are the header comment, `ingress.host`, and the prod-only `database.resources` and `wordpress.resources` blocks. No change under `charts/store/templates/`. Diff saved as evidence. | Exactly those three differences and nothing else. `git status` and `git diff HEAD` on `charts/store/templates/` are both empty, so no template changed. Diff saved at `docs/evidence/k02-values-diff.txt`. | pass |
| SP-3 | `helm install store charts/store -f charts/store/values-prod.yaml` on the VPS | All pods Ready, both PVCs Bound, bootstrap Job Completed | revision 1, STATUS deployed. `store-store-db-0` 1/1, `store-store-wp-fd6dc7997-gzvkt` 1/1, `store-store-bootstrap-4ghbm` Completed. PVCs `data-store-store-db-0` and `store-store-wp-content` both Bound 2Gi `local-path`. Job `Complete 1/1` in 2m55s; WooCommerce 11.2.1 active, product 11 `Demo Widget` created. Ingress `store-store` class `traefik` host `store.34.93.101.10.sslip.io`. | pass |
| SP-4 | `curl -I http://store.34.93.101.10.sslip.io/` from the laptop over the public internet | `HTTP/1.1 200 OK` | `HTTP/1.1 200 OK`, Apache/2.4.68 (Debian), PHP/8.3.35. sslip.io resolved the host to `34.93.101.10`. Port posture re-checked after the firewall change: `https://34.93.101.10:6443` returns nothing, TCP 22 is not reachable publicly. | pass |

K-02 is marked `pass` only if SP-1 to SP-4 all pass.

**Prod storefront checkout, 2026-10-17.** Not in the pre-registered table above. The expectation
came from the morning instruction ("I check out in the browser myself, you verify the order with
WP-CLI") rather than being written into this file before running, so it is recorded here as a
note rather than as an SP row. Kapardhi checked out at http://store.34.93.101.10.sslip.io/ with
Cash on delivery. Verified on pod `store-store-wp-fd6dc7997-gzvkt`:

| Field | Value |
|---|---|
| order | 13 |
| status | `processing` |
| total | 19.99 USD |
| payment method | `cod` (Cash on delivery) |
| created | 2026-10-17T02:22:46+00:00 |
| line item | `Demo Widget` x1, sku `DEMO-WIDGET-1`, subtotal 19.99 |
| WooCommerce | 11.2.1 |

Order 13, not 12, because prod is a separate database from local. The serving image has no `wp`
binary, so this used the same WP-CLI-equivalent PHP through `wp-load.php` as DOD-02, with
`wc_get_orders()`, which is storage-agnostic across HPOS and legacy post storage.

## Woo MCP server (W-01 to W-09, G-10 groundwork)

Pre-registered 2026-10-17, **before any `services/woo-mcp` code exists** and before
`charts/woo-mcp` exists. Local k3d only. The VPS run comes after all eight pass.

| # | Check | Expected (written before the code exists) | Actual | Result |
|---|---|---|---|---|
| WM-1 | `pytest` on `services/woo-mcp`, and `scripts/check-charts.sh` | All unit tests pass, 0 failures. check-charts prints PASS portability and PASS prod leakage, exit 0. Includes the OAuth-trap regression test below. | 24 passed, 0 failed. check-charts `PASS portability`, `PASS prod leakage`, exit 0. The OAuth-trap test is proved: with `home_url` swapped for `service_url` in `WooClient` the suite fails with "signature is not over home_url"; restored, 24 pass. | pass |
| WM-2 | `tools/list` from a Python MCP SDK client in a pod labelled `app.kubernetes.io/name=gateway` | Exactly 5 tools, no more and no fewer: `list_products`, `create_product`, `list_orders`, `get_order`, `update_order_status`. Each has a strict input schema. | `{"count": 5, "tools": ["create_product","get_order","list_orders","list_products","update_order_status"]}`. Exactly the five. | pass |
| WM-3 | `create_product(name, regular_price)` then fetch the storefront | Tool returns the new product id. The product is then visible on `http://store.localhost/` (or its own permalink) with the name and price given. | Tool returned id 13, `MCP Test Widget`, sku `MCP-TEST-1`, price 4.50, permalink `http://store.localhost/product/mcp-test-widget/`. That permalink returns `HTTP 200` from the laptop. | pass |
| WM-4 | `list_orders(date=today)` | **Corrected from the original wording.** Order 12 was created `2026-10-16T15:37:15+00:00`, so "today" (2026-10-17) cannot return it. Instead: place a fresh order today, then `list_orders(date=today)` returns that order and **does not** return order 12. Order 12 is the negative control that proves the date filter is real and not a no-op. | Order 14 placed 2026-10-17T03:05:39+00:00. Three-way proof: `date=today` returned `[14]` only; no date filter returned `[14, 12]`; `date=2026-10-16` returned `[12]` only. The filter selects, excludes, and is not a no-op. | pass |
| WM-5 | `update_order_status(12, "completed")` | Order 12 moves from `processing` to `completed`. Confirmed by `wc_get_orders()` on the pod and visible at the wp-admin order URL. | Before: `processing`. Tool returned `status: completed`. Independent check on the WordPress pod: `status=completed`. Admin URL `http://store.localhost/wp-admin/admin.php?page=wc-orders&action=edit&id=12`. | pass |
| WM-6 | NetworkPolicy | A pod labelled `app.kubernetes.io/name=gateway` reaches the woo-mcp Service. An unlabelled pod in the same namespace times out rather than being refused. Both measured, with the timeout bounded so a hang is distinguishable from a pass. | Isolation enforced, **but the predicted failure shape was wrong.** Gateway-labelled pod to woo-mcp: CONNECTED. Unlabelled pod to woo-mcp: **REFUSED**, not TIMEOUT. Control proves the policy is the cause: the same unlabelled pod reaches `store-store-wp.store:80` (no policy) but is refused by `woo-woo-mcp.store:8000`, and is still refused going direct to the pod IP `10.42.0.27:8000`, bypassing the Service. The requirement (only the gateway can reach woo-mcp) is met; the expectation that a denied connection would hang was an incorrect prediction about k3s's NetworkPolicy backend, which sends a TCP reset rather than dropping. | pass |
| WM-7 | No route from outside | `kubectl get ingress -A` shows no Ingress object selecting woo-mcp. From the laptop there is no path to it: the only published hosts are the storefront ones, and the woo-mcp Service is ClusterIP. | `helm template` renders Deployment, Service and NetworkPolicy and zero Ingress objects. The only Ingress in the cluster is `store/store-store`, host `store.localhost`, backend `store-store-wp`; ingress backends naming woo-mcp: 0. All three Services are ClusterIP, none NodePort or LoadBalancer. From the laptop: `store.localhost/mcp` returns 301 to `/product/mcp-test-widget/` served by Apache, so that path reaches WordPress and not woo-mcp; `store.localhost:8000` and the ClusterIP `10.43.77.205:8000` both fail to connect. | pass |
| WM-8 | Upstream failure is handled | `kubectl scale deploy/<wp> --replicas=0`, then call a tool. The call returns an MCP tool error with a clear message within the configured timeout, the process does not crash or hang, and the woo-mcp pod stays `Ready` throughout. Then scale back to 1 and the same tool succeeds. | **Failed on first run, then fixed.** First run returned only `"Error executing tool list_products"`: the MCP SDK surfaces a message to the model only when a tool raises its own `ToolError`, and treats anything else as a crash with the text withheld. `WooError` was a plain `RuntimeError`, so the useful message was swallowed. Fixed with a `@surfaced` decorator converting `WooError` to `ToolError` at the MCP boundary, keeping `woo.py` free of any SDK import, plus two regression tests covering all five tools. Re-run: `"could not reach the store at http://store-store-wp.store (GET /wp-json/wc/v3/products): ConnectError"` in 1s against a 10s timeout, pod `Ready`, 0 restarts. Scaled back to 1: the same tool returned both products. 0 restarts across the whole outage. | pass |

**OAuth-trap regression test (part of WM-1).** WooCommerce builds its signature base string from
`get_home_url()`, not the Host header (D-006). woo-mcp therefore connects to one URL and signs
another. A unit test asserts the signature is computed over `store.homeUrl`; it fails if the
implementation ever signs `store.serviceUrl` instead. Without it, the trap can come back silently
because a wrong signature looks exactly like a credentials problem.

**Open question, does not block the build: the store's timezone is UTC.** The requirement is that
"today" means the store's timezone, not UTC. Measured 2026-10-17: `timezone_string` is empty and
`gmt_offset` is 0, so the store is UTC and the two answers are identical. woo-mcp will read the
timezone from WooCommerce settings as specified, which is correct either way, but on a UTC store
the behaviour is not actually exercised. Setting the store timezone to a non-UTC zone would make
WM-4 meaningful. That is a store configuration change and therefore Kapardhi's call, not an
implementation detail.

## Woo MCP server on the VPS (W-08 prod half)

Pre-registered 2026-10-17, **before** the GHCR pull secret, the prod Woo API key or
`charts/woo-mcp` existed on the VPS. Re-runs the four checks whose result could plausibly differ
between k3d and k3s on a real host: protocol surface, timezone-dependent filtering, NetworkPolicy
enforcement, and failure handling. WM-1, WM-3, WM-5 and WM-7 are environment-independent or already
covered by the prod chart render, so they are not repeated.

| # | Check | Expected (written before running) | Actual | Result |
|---|---|---|---|---|
| VWM-2 | `tools/list` from a gateway-labelled pod on the VPS | Exactly the same 5 tools as local: `create_product`, `get_order`, `list_orders`, `list_products`, `update_order_status`. | `{"count": 5}` and the same five names. Identical to local. | pass |
| VWM-4 | `list_orders(date=today)` on the VPS | The prod store has order 13, placed 2026-10-17T02:22:46Z, which is 07:52 on the 17th in Asia/Kolkata. With the store timezone set, `date=today` returns order 13. `date=2026-10-16` returns nothing, since prod has no orders from the 16th. | `date=today` returned `[13]`; `date=2026-10-16` returned none; no filter returned `[13]`. The API now renders the timestamp as `2026-10-17T07:52:46` rather than `02:22:46Z`, so the store timezone is visibly in effect through the REST layer. | pass |
| VWM-6 | NetworkPolicy on k3s | Gateway-labelled pod connects. Unlabelled pod is blocked. On k3d the block showed as REFUSED rather than TIMEOUT; the same backend is in use here, so REFUSED is expected again. The check is that the unlabelled pod cannot connect while reaching WordPress fine. | Gateway pod: WordPress CONNECTED, woo-mcp CONNECTED. Unlabelled pod: WordPress CONNECTED, woo-mcp REFUSED. Same shape as k3d, prediction correct this time. | pass |
| VWM-8 | Upstream failure on the VPS | Scale the prod WordPress deployment to 0, call a tool: an MCP tool error naming the unreachable store, within the 10s timeout, woo-mcp stays Ready with 0 restarts. Scale back to 1 and the same tool succeeds. | `"could not reach the store at http://store-store-wp.store (GET /wp-json/wc/v3/products): ConnectError"` in 3s against a 10s timeout. Pod Ready, 0 restarts. Scaled back to 1: the same tool returned Demo Widget with the prod permalink. 0 restarts across the outage. | pass |

Image for prod is pulled from GHCR, not imported: `ghcr.io/kapardhi03/woo-mcp:0.1.1`, multi-arch
`linux/arm64` + `linux/amd64`, 57.2 MB and 57.0 MB compressed respectively.

Confirmed pulled, not imported: kubelet logged `Successfully pulled image
"ghcr.io/kapardhi03/woo-mcp:0.1.1" in 9.878s. Image size: 59729890 bytes`.

**GHCR storage, 2026-10-17.** Total 114.1 MB of the 500 MB free-plan allowance, 385.9 MB headroom.
Actions artifacts, which share that allowance, are at 0. **Nothing was pruned, deliberately.** The
package shows 5 versions, 1 tagged and 4 untagged, and the obvious move is to delete the untagged
ones. That would have broken the image: all four are referenced by the tagged manifest list, two as
the `linux/arm64` and `linux/amd64` manifests and two as attestation manifests. Verified by
comparing each version's digest against the manifest list before touching anything. There is
nothing safe to prune until a second tag exists.

## Gateway phase 1 (GW-1 to GW-9)

Pre-registered 2026-10-17, **before `services/gateway`, `services/fx-mcp`, `charts/gateway` or
`charts/fx-mcp` existed**. Local k3d only. Builds on D-008 Postgres, D-009 prefixing and D-010
in-cluster upstreams, all of which stay open awaiting Kapardhi's words.

| # | Check | Expected (written before the code exists) | Actual | Result |
|---|---|---|---|---|
| GW-1 | `pytest` on `services/gateway` and `services/fx-mcp`, plus `scripts/check-charts.sh` and `scripts/check-cluster.sh` | All unit tests pass, 0 failures. check-charts PASS portability and PASS prod leakage, exit 0. check-cluster PASS with every Job at `failed == 0`. | gateway 31 passed, fx-mcp 15 passed, woo-mcp 25 passed, 0 failures. check-charts `PASS portability` / `PASS prod leakage`, exit 0 across all four charts. check-cluster PASS, no Job with a failed pod. | pass |
| GW-2 | Claude Code on the laptop, given only the gateway URL and the bootstrap API key | Connects to `http://gateway.localhost/mcp`. `tools/list` shows the five `woo__*` tools and the `fx__*` tools, and nothing else. No upstream URL or upstream credential is configured on the client. | Kapardhi ran it. Claude Code connected with only the gateway URL and the bootstrap key, no upstream URL or credential anywhere in its config. Asked "What orders came in today?" it returned order 14, 19.99 USD, `cod`, Demo Widget, dated 2026-10-17 08:35:39 **store time**, and confirmed the store-timezone bounds excluded yesterday's order 12. | pass |
| GW-3 | MCP Inspector on the old protocol (2025-11-25) through the gateway | Same tool set as GW-2, proving the gateway serves both protocol versions (D-001 option C). `woo__list_orders` returns the local orders. | `count: 7`, exactly the same names as GW-2. `tools/call woo__list_orders date=today` returned order 14 with `isError: false`. The gateway logged `Created new transport with session ID`, so the Inspector used the session-based 2025-11-25 path while Claude Code used the stateless 2026-07-28 one. **The pair is what proves D-001 option C: one gateway served both versions concurrently with no special handling.** | pass |
| GW-4 | One prompt using both upstreams | Today's order total from `woo__list_orders` converted to EUR with `fx__convert`. The answer cites both tools, so the cross-server requirement is met by a natural question rather than a contrived one. | **Fully met, including the prompt half.** First proven as a tool sequence, then properly during GW-2: Kapardhi asked Claude Code one natural-language question, "What's today's order total in EUR?", and it answered EUR 17.76 from order 14 at 19.99 USD, choosing `woo__list_orders` and `fx__convert` unaided through the single gateway endpoint. A model picking two tools from two different upstreams is exactly what the requirement asks for. Note this was Claude Code as the external client, not the dashboard chat agent (C-01), which still does not exist; DOD-07 is about the external client and is now evidenced. | pass |
| GW-5 | Kill the woo-mcp pod, then `tools/list` | The list still returns within the per-upstream timeout and still contains the `fx__*` tools. The `woo__*` tools are absent, and woo-mcp's status reads `Unreachable`. A dead upstream must not break the list or delay it past the timeout. | woo scaled to 0: `tools/list` returned `["fx__convert","fx__rates"]` in under 1s against an 8s timeout; woo `Unreachable`. Scaled back: all 7 tools returned. **One defect found and fixed here.** The status first read `last_error=ExceptionGroup`, which tells an operator nothing: anyio wraps transport failures in a group. `_reason()` now unwraps to the first real cause and the field reads `ConnectError`. It stays type-only on purpose, because a transport error's text can quote request headers. Regression-tested. | pass |
| GW-6 | Disable fx in the registry | `fx__*` tools disappear from `tools/list`. `woo__*` remain. No pod is deleted; this is a registry flag, not a scaling action. | `UPDATE upstreams SET enabled=false WHERE slug='fx'`: `tools/list` returned only the five `woo__*`, status `Disabled`, and the fx pod stayed `1/1 Running` throughout. Re-enabled: all 7 returned. | pass |
| GW-7 | Audit rows | Every call made in GW-2 to GW-6 has a row: user, server, tool, timestamp, duration_ms, outcome. Outcomes match what happened, including the failures from GW-5. Durations are non-zero and plausible. | Rows present with all six fields. Successes: `bootstrap-admin / woo / list_orders / 2269ms / ok` and `bootstrap-admin / fx / convert / 752ms / ok`. Rejections: `anonymous / - / - / 0ms / rejected`. Durations are plausible and distinguish a local upstream from one making an internet call. | pass |
| GW-8 | No credential leakage | Take an upstream credential's literal value from the registry and grep for it across every tool response captured in GW-2 to GW-6 and across the full logs of the gateway and both upstream pods. Expected: **0 hits**. | A 30-char canary credential was encrypted with the gateway's own key and stored against the woo upstream, then exercised by a `tools/list` and two `tools/call`. Grepped 5 captured responses and the full logs of the gateway, Postgres, woo-mcp and fx-mcp: **0 hits in all 9 places**. The admin endpoint reported `has_credential=true` and never the value. Sanity check proves the test is not vacuous: the stored blob decrypts back to the exact canary. Canary removed afterwards. | pass |
| GW-9 | Bad auth is rejected and audited | A request with no API key and a request with a wrong API key are both rejected. Each rejection produces an audit row with a failure outcome. A rejected call must not reach any upstream. | Three cases, all `HTTP 401`: no key, a well-formed but wrong key, and a malformed key. Each produced an audit row with outcome `rejected` and user `anonymous`. Auth runs in ASGI middleware ahead of the MCP app, so a rejected request is returned before any upstream is contacted. | pass |

GW-2 and GW-3 need Kapardhi to drive a client in his own terminal. Everything else passed first,
so the two client checks are the only outstanding work in phase 1.

**GW-3's first run failed, and the cause is worth recording.** The command was run with
`Bearer $KEY` where `$KEY` was unset in that shell, so an empty bearer reached the gateway. The
gateway correctly returned 401, but MCP Inspector responded by attempting OAuth Dynamic Client
Registration and reported `auth_required: Dynamic Client Registration rejected (HTTP 401)`, which
names OAuth and hides the real cause. Reproduced exactly: empty bearer gives 401, the real key
gives a working session. **Contributing gap on our side:** the 401 carries no `WWW-Authenticate`
header, so a client has nothing to tell it that a static bearer is expected and is free to guess
OAuth. Adding that header would make the failure self-explaining. Not done yet, and it moves no
pre-registered row, so it is recorded rather than built.

**Three observations from the live clients, none of them gateway bugs.**

1. *A list tool's result arrives as one content block per element, not a JSON array.* Claude Code
   noticed this and checked it carefully before reporting a count: a one-element result is a single
   bare object, which on its own does not distinguish "one order" from "a list flattened to its
   first element". It confirmed by calling with no filter and getting two separate blocks. This is
   how the SDK serialises a `list[dict]` return, not a defect in `list_orders`, but it is worth a
   line in the demo script because a reader will wonder.

2. *`fx__convert` reports `date: 2026-10-16` when asked for today's rate.* Frankfurter serves ECB
   reference rates, which publish on business days, so "latest" is the most recent published rate
   rather than one dated today. Correct behaviour for the data source, and worth stating out loud
   rather than letting a reviewer catch it.

3. *Tool schemas carry no parameter descriptions and no enum for `status`.* Checked rather than
   assumed: the gateway's served schema is byte-identical to woo-mcp's own, so the gateway is a
   faithful proxy and the flattening happens in woo-mcp, whose tools use plain `str` annotations.
   The consequence is that a model learns the eight valid order statuses only by guessing and
   being rejected. Using `Literal[...]` for `status` would put the enum in the schema. It moves no
   pre-registered row, so it is flagged here rather than done.

**Two bugs found during bring-up, both recorded because neither was obvious from the symptom.**

1. `DATABASE_URL` referenced `$(PGPASSWORD)` but was declared before it. Kubernetes expands
   `$(VAR)` only against variables defined earlier in the same list, so the literal string
   `$(PGPASSWORD)` was sent and Postgres answered `password authentication failed`, which reads
   like a wrong password rather than an unexpanded variable.

2. Mounting the SDK's Streamable HTTP app inside FastAPI does not run that app's lifespan, so the
   session manager's task group never started and every MCP request died with `Task group is not
   initialized`. The FastAPI lifespan now enters `session_manager.run()` explicitly.

## Kubernetes and Helm

| ID | Requirement | Implemented in | Evidence | Status |
|---|---|---|---|---|
| K-01 | Runs on local Kubernetes (D-002) | k3d cluster `gw-local` on Colima (D-017) | 2026-10-15: node Ready, k3s `v1.35.5+k3s1`, Traefik Running, `local-path (default)`, `traefik` ingressclass. 2026-10-16: `charts/store` installed and serving at http://store.localhost/ (SC-1 to SC-8 all pass). Becomes `pass` when the gateway, Woo MCP server and dashboard also run. | in progress |
| K-02 | Same charts deploy to k3s VPS, values-only differences | `charts/store`, `values-local.yaml` and `values-prod.yaml` | 2026-10-17: SP-1 to SP-4 all pass. The same chart installed on local k3d and on the k3s VPS with no template change; the only differences are in the values files (`docs/evidence/k02-values-diff.txt`). Storefront serves `HTTP/1.1 200 OK` over the public internet at http://store.34.93.101.10.sslip.io/. See the store smoke deploy section above. | pass |
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
