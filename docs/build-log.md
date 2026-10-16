# Build log

How we work, session by session. Who proposed what, what Kapardhi decided and why (link D-number), what was built, how it was verified, and any AI errors caught.

Proposer tags: `K` = Kapardhi, `C-code` = Claude Code.

---

## 2026-10-14, session 1: project setup

**Goal.** Set up the working process before writing any code.

**Proposed.**
- K: log every decision and the reason. When Claude suggests something, Claude asks why Kapardhi chose it.
- K: process files (`PROJECT_INSTRUCTIONS.md`, `CLAUDE.md`, decision log, requirements trace, defense notes, review record).
- K: 16 open decisions (D-001 to D-016) with options and a recommendation each.

**Facts looked up before recommending** (sources are in the decision entries).
- Ingress NGINX retired in March 2026. Changed D-003 recommendation away from it.
- Bitnami free versioned images moved to `bitnamilegacy` without updates from 28 Aug 2025. Changed D-005 recommendation to own templates.
- MCP spec `2026-07-28` is stateless (no `initialize`, no `Mcp-Session-Id`). Made D-001 the first decision and turned it into a spike.

**Decided.** None yet. All decisions are open and wait for Kapardhi's choice and reason.

**Built.** Process files only.

**Verified.** n/a

**AI errors caught.** None this session.

**Next.** Kapardhi answers D-016, D-002, D-005, D-007 with reasons. Then the D-001 spike.

---

## 2026-10-15, session 2: local cluster bring-up

**Goal.** Choose the local Kubernetes stack, install it, and bring up an empty cluster. No chart and no application code.

**Proposed.**
- K: k3d for local Kubernetes (D-002), and Colima plus Helm 4.x as the local toolchain (D-017).
- C-code: version lookups, the install plan, and the pre-registered checks below.

**Facts looked up before recommending** (sources in the decision entries).
- Homebrew versions on 2026-10-15: k3d 5.9.0, kind 0.33.0, Minikube 1.39.0, kubectl 1.37.1, Helm 4.3.1, Colima 0.10.3, Lima 2.2.1, Docker CLI 29.9.1.
- Colima 0.10.3 defaults to the macOS Virtualization.framework VM type and virtiofs mounts, so both were passed explicitly for reproducibility.
- Oracle Always Free Ampere is now 2 OCPU and 12 GB, reduced from 4 and 24, and exists only in the tenancy home region. Source: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Oracle returns HTTP 429 `TooManyRequests` for API throttling and documents it as retryable with backoff. It is a different failure from `Out of host capacity`. Source: https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm

**Decided.** D-002 k3d, and D-017 the local toolchain (Colima 0.10.3, Helm 4.x). D-017 and the former D-018 were merged into one batched entry, so D-018 is free for the next decision. The reason fields are not yet filled, so both stay `open, awaiting reason`.

**Built.** Tooling and one empty cluster. No chart, no application code, no repo code.

**Pre-registered checks** (written before running).

| # | Check | Expected |
|---|---|---|
| 1 | `kubectl get nodes` | 1 node, Ready |
| 2 | `kubectl get pods -n kube-system` | traefik Running |
| 3 | `kubectl get storageclass` | `local-path` marked (default) |
| 4 | `kubectl get ingressclass` | `traefik` |
| 5 | `curl -sI http://localhost` | HTTP 404 from Traefik, no routes yet |
| 6 | After 5 minutes idle | Colima VM memory use and macOS swap use |

**Verified.** Commands run on 2026-10-15.

| # | Expected | Actual | Result |
|---|---|---|---|
| 1 | 1 node Ready | `k3d-gw-local-server-0  Ready  control-plane  v1.35.5+k3s1` | pass |
| 2 | traefik Running | `traefik-9bcdbbd9-r7n4j  1/1  Running` | pass |
| 3 | `local-path (default)` | `local-path (default)  rancher.io/local-path` | pass |
| 4 | `traefik` | `traefik  traefik.io/ingress-controller` | pass |
| 5 | 404 from Traefik | `HTTP/1.1 404 Not Found` | pass |
| 6 | measure | guest 1.0 GiB used of 4.8 GiB, no guest swap; host swap 7646 MB of 8192 MB | pass, with a warning |

Cluster created with: `k3d cluster create gw-local --servers 1 --agents 0 -p "80:80@loadbalancer" -p "443:443@loadbalancer"`.
Colima started with: `colima start --cpus 4 --memory 5 --disk 40 --vm-type vz --mount-type virtiofs --runtime docker`.
k3d pulled `docker.io/rancher/k3s:v1.35.5-k3s1`. Pin that tag on the VPS so both sides run the same k3s.

**Warning recorded.** With only an empty cluster running, macOS had 0.06 GB free, 3.47 GB compressed and 93% of swap in use. Headroom for WordPress, the store database, Postgres, the gateway, the dashboard and three MCP servers is thin. Resource requests and limits are required by K-08 and K-09 anyway.

**Oracle VPS (stretch goal, D-016).** Not obtained. Run 1 ran 17h 55m over 148 cycles. Run 2 is still going under a 2026-10-16 20:00 IST deadline, 32 cycles so far. Totals across both runs: 179 `Out of host capacity` rejections and 1 throttle. A1 quota is 41 cores and 277 GB available with 0 used, so the block is host capacity in ap-hyderabad-1, not quota or configuration. Network is built and idle at no cost.

**AI errors caught.**
- Planning chat assumed the laptop was x86 and recommended an x86 VPS. The hardware report showed an Apple M1 on arm64. The VPS target changed to Ampere A1 aarch64 and the local images to arm64.
- The first `git grep` searched tracked files only and reported a false clean result for the terms being removed. Caught by re-running with `--untracked`, which found eight hits.
- A retry script logged the OCI CLI's Python `SyntaxWarning` instead of the real API error, hiding an HTTP 429 behind truncated output. Caught by re-running the call with warnings suppressed.
- A `kubectl wait --for=condition=Ready pod --all` timed out on completed Job pods and looked like a cluster failure. Job pods finish `Completed` and never become `Ready`, so that condition can only time out.

**Protocol amended.** `PROJECT_INSTRUCTIONS.md` section 3 and the decision-log header now allow AI-drafted reasons for tooling choices, marked "AI-drafted, accepted by Kapardhi". Design choices the demo video must explain still need Kapardhi's own words: D-001, D-006, D-009, D-013, D-014 and any new entry in those areas. Kapardhi delegated the tooling reasons on 2026-10-16 under this amendment.

**Decided on 2026-10-16.** D-002 k3d. D-017 local toolchain (Colima 0.10.3, Helm 4.x). D-005 own templates on the official `wordpress`, `mariadb` and `wordpress:cli` images. D-007 Python with FastAPI and the official MCP Python SDK, React for the dashboard, revisit after the D-001 spike. D-018 was merged into D-017 and is free for the next decision.

**Verified before writing D-005.** `docker manifest inspect` against Docker Hub on 2026-10-16: `wordpress:latest`, `wordpress:cli` and `mariadb:latest` all publish `linux/amd64` and `linux/arm64/v8`. This was the gate on D-005 and it passed, so the choice covers both an Ampere A1 aarch64 VPS and an x86 VPS.

**Built.** `scripts/check-charts.sh`. Two guards on the charts: portability (no hardcoded k3s parts under `charts/*/templates/`) and prod leakage (rendering with `values-prod.yaml` must not emit `localhost`, a `.local` host, or `pullPolicy: Never`).

**Verified.** The script was proved in all three states on 2026-10-16, against a throwaway fixture outside the repo, which was then deleted.

| Fixture | Expected | Actual | Result |
|---|---|---|---|
| no `charts/` | SKIP, exit 0 | `SKIP  charts/ does not exist yet`, exit 0 | pass |
| one bad line per check | both FAIL, exit non-zero | both FAIL with line numbers, exit 1 | pass |
| clean chart | both PASS, exit 0 | both PASS, exit 0 | pass |

**AI errors caught.**
- The first K-02 check was written as a raw grep inside a markdown table. The pipe had to be escaped as `\|` to avoid breaking the table, and `grep -E` reads `\|` as a literal pipe, so anyone copying the command from the raw file would have run a check that silently matched nothing and always passed. Caught by C-code before any chart existed, and replaced with `scripts/check-charts.sh`.

**Next.** D-001 spike, which gates D-007. Then the first chart, with `scripts/check-charts.sh` run before it is called done.

---

## 2026-10-16, session 3: store chart, D-001 spike, Oracle closed

**Goal.** Get DOD-01 and DOD-02 passing on k3d, measure the MCP protocol question, and close out the VPS search.

**Proposed.**
- K: build the store chart, run the D-001 spike, close D-016 after the Oracle deadline.
- C-code: chart templates, spike server and clients, version lookups, the checks below.

**Decided.** D-003 Traefik. D-004 `*.localhost`. D-016 GCP trial x86 + k3s, after Oracle failed. D-019 opened and still needs Kapardhi's words; the chart is already built that way.

**Verified.**
- Store chart SC-1 to SC-8 all pass. Detail in `docs/requirements-trace.md`.
- DOD-01 pass: Kapardhi checked out in a browser. Order 12, `cod`, 19.99 USD, `Demo Widget` x1.
- DOD-02 pass: order 12 status `processing`, admin URL `http://store.localhost/wp-admin/admin.php?page=wc-orders&action=edit&id=12`, orders list route 302s to login when unauthenticated.
- D-001 spike: Claude Code 2.1.278 and the mcp 2.3.0 client send `2026-07-28` with no `initialize` and no session ID. MCP Inspector 2.11.0 sends `2025-11-25` with the full handshake and a session ID. One SDK 2.3.0 server served both at once. The 2.3.0 client also falls back to `2025-11-25` against an mcp 1.28.1 upstream. Measurements only; D-001 is still open.

**Oracle VPS, final.** 265 launch attempts across two runs over roughly 36 hours, 0 instances, about 290 `Out of host capacity` rejections and 8 throttles. Quota was never the limit: 41 A1 cores and 277 GB available, 0 used. Closed in D-016. Nothing deleted; the Oracle network costs nothing.

**AI errors caught.**
- The bootstrap Job reported `database not reachable after 5 minutes` while MariaDB was healthy and `1/1 Running`. The real cause was that `wordpress:cli` ships wp-cli but not WordPress core, so with only `wp-content` mounted there was no `wp-config.php` and every `wp` command failed for want of configuration, not connectivity. Fixed with an `emptyDir` scratch root, `wp core download --skip-content` pinned to the serving image's version, and an explicit `wp config create`. The failure path now prints the real `wp db check` output so the message cannot mislead again.
- `scripts/dev-secrets.sh` printed the base64 Secret values to stdout. Base64 is not encryption, and `CLAUDE.md` forbids logging secret material. Fixed to print key names only. **Not rotated on local**: this cluster is local-only and disposable, so the exposure has no consequence. The VPS gets fresh values from `scripts/dev-secrets.sh` run there, never copied from local.
- The first K-02 check was written as a raw grep inside a markdown table, where the escaped pipe `\|` would have made `grep -E` match nothing and pass forever. Caught before any chart existed and replaced with `scripts/check-charts.sh`, which is proved to fail on a bad fixture.
- A `kubectl wait --for=condition=Ready pod --all` timed out on completed Job pods and looked like a cluster failure. Job pods finish `Completed` and never become `Ready`.

**Note for D-006.** WooCommerce here uses legacy post storage, not HPOS. A direct database query against `wp_wc_orders` fails. `wc_get_orders()` is storage-agnostic. This is further evidence for the REST API option in D-006 over direct SQL.

**Next.** GCP VM for the VPS half of K-02. Then the Woo MCP server, which needs D-006 and D-001.
