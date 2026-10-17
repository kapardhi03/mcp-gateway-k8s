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

**AI error caught (2026-10-16, GCP planning).** C-code proposed the first VM create command with `--no-address`, arguing it removed the public SSH attack surface entirely. It flagged only the egress consequence, that the VM could not reach the internet to install k3s without Cloud NAT. It missed the larger problem: the VPS must accept **public inbound HTTP** for Ingress, which is requirement K-06 and the whole point of the prod deployment. A VM with no external IP would have made the prod store unreachable. Caught by Kapardhi before anything was created. The corrected plan reserves a static external IP so the prod hostname can be `store.<IP>.sslip.io` and stays stable, while SSH still goes only through IAP TCP forwarding from `35.235.240.0/20` with no public SSH port.

**Next.** GCP VM for the VPS half of K-02. Then the Woo MCP server, which needs D-006 and D-001.

---

## 2026-10-17, session 4: store on the VPS, K-02 pass

**Goal.** Deploy the store chart to the k3s VPS with values-only differences, and prove it.

**Proposed.**
- K: reopen the IAP tunnel, open 80 and 443 to tag `k3s-prod` only, fresh prod secrets, prod host on sslip.io, pre-register the checks, then stop for a browser checkout.
- C-code: the firewall rule text, the D-004 addendum wording, the pre-registration, and the checks.

**Decided.** No new D-number. The prod host is recorded as a D-004 addendum: prod uses
`store.34.93.101.10.sslip.io` because there is no paid domain, local stays `*.localhost`.
This is the option C that D-004 rejected for local, accepted for prod only, with the reason
written down. It records a fact and does not change the D-004 choice.

**Built.**
- GCP firewall `allow-http-https`: `tcp:80,443` from `0.0.0.0/0` to target tag `k3s-prod`, priority 1000. No existing rule touched.
- Fresh Secrets on the VPS from `scripts/dev-secrets.sh`. The `store` namespace did not exist, so both were created new. Nothing copied from local.
- `charts/store/values-prod.yaml`: `ingress.host` set to the sslip.io name, replacing the `store.example.com` placeholder.

**Verified.** SP-1 to SP-4 pre-registered before running, all pass. Detail in `docs/requirements-trace.md`.
- SP-1 `scripts/check-charts.sh`: PASS portability, PASS prod leakage, exit 0.
- SP-2 values diff: only the header comment, `ingress.host` and the prod-only resources blocks differ. `git diff HEAD` on `charts/store/templates/` empty. Saved at `docs/evidence/k02-values-diff.txt`.
- SP-3 `helm install` on the VPS: db 1/1, wp 1/1, bootstrap Completed, both PVCs Bound 2Gi `local-path`, Job `Complete 1/1` in 2m55s.
- SP-4 `curl -I` from the laptop over the public internet: `HTTP/1.1 200 OK`.
- Port posture re-checked after the firewall change: 6443 returns nothing from the internet, TCP 22 not publicly reachable.
- Prod checkout: order 13, `processing`, 19.99 USD, `cod`, `Demo Widget` x1 sku `DEMO-WIDGET-1`.

K-02 marked `pass`.

**AI errors caught.**
- Process slip, by C-code. The prod checkout verification was run without its expected result being written into `docs/requirements-trace.md` first, which is the rule this project runs on. The expectation existed in Kapardhi's instruction, so the result is not in doubt, but it was not pre-registered. Recorded as a note under the smoke deploy section rather than promoted to an SP row, so the table keeps its meaning.
- No incorrect technical claims found this session. State was re-read from the repo at the start rather than carried over from the previous session's context, which is what caught that the VPS is GCP and that charts and scripts already existed.

**Open risk.** The storefront is now publicly reachable, and the WordPress admin password was
printed into a chat transcript while retrieving it for the browser login. Low consequence for a
demo box, but it should be rotated before the repo goes public (D-018). Rotation needs a
`wp user update admin --user_pass=...` on the pod plus a Secret update; deleting the Secret alone
does not change the WordPress user.

**Next.** The Woo MCP server, which needs D-006 and D-001. D-019 still needs Kapardhi's words.

---

## 2026-10-17, session 5: Woo MCP server, store timezone

**Goal.** Build the WooCommerce MCP server and its chart, and prove them against
pre-registered checks.

**Proposed.**
- K: D-020 GHCR multi-arch; pre-generate the Woo API pair outside the cluster; woo-mcp with five
  tools; a chart with a NetworkPolicy and no Ingress; pre-register all eight checks first.
- C-code: the GHCR limit research, the WooCommerce source reading, the implementation and the checks.

**Decided.** D-020, GHCR multi-arch, private until submission. D-001 and D-006 stay open; both now
record that the build proceeds on the recommendation, pending Kapardhi's words.

**Built.** `scripts/rotate-admin.sh`; the WooCommerce REST credential path; `services/woo-mcp`;
`charts/woo-mcp`; store timezone set to Asia/Kolkata.

**Verified.** WM-1 to WM-8 all pass on k3d. Detail in `docs/requirements-trace.md`.

**AI errors caught.**
- **Planning chat wrongly stated order 12 was placed "today".** WM-4 as briefed was
  "list_orders(date=today) returns local order 12". Order 12 was created 2026-10-16T15:37:15Z and
  the check ran on 2026-10-17, so as written it could only fail. Caught by C-code at
  pre-registration, before any code existed, by reading the order's real timestamp rather than
  trusting the brief. Rewritten to place a fresh order and keep order 12 as a negative control,
  which made the check stronger: it now proves the date filter both selects and excludes.
- **WM-8 found a real defect.** The MCP SDK surfaces a message to the model only when a tool raises
  its own `ToolError`; anything else is a crash with the text withheld. `WooError` was a plain
  `RuntimeError`, so with WordPress at 0 replicas the client saw only "Error executing tool
  list_products". Fixed with a `@surfaced` decorator at the MCP boundary, regression-tested across
  all five tools.
- **WM-6's predicted failure shape was wrong.** C-code expected a denied connection to time out.
  k3s's NetworkPolicy backend sends a TCP reset, so it is refused. Isolation is genuinely enforced
  and was proved with controls, including direct to the pod IP. The prediction was wrong and is
  recorded as such rather than quietly rewritten.
- **Latent SIGPIPE bug in `scripts/dev-secrets.sh`.** `tr ... | head -c 32` dies under
  `set -o pipefail` once head closes the pipe. A race, so it passed for two sessions before failing
  during the first run of `rotate-admin.sh`. Fixed in both scripts and proved over 10 runs.
- **`scripts/check-charts.sh` false positive.** Its leakage regex `\.local[^a-zA-Z0-9]` matches a
  legitimate `svc.cluster.local` FQDN. Worked around in the woo-mcp chart with the
  namespace-qualified short Service name, which is correct DNS anyway. The regex remains a trap for
  a future chart that genuinely needs an FQDN.

**Security note.** The prod WordPress admin password was printed into a chat transcript while being
retrieved for a browser login. Rotated with `scripts/rotate-admin.sh`; the exposed value now returns
`incorrect_password`.

**Next.** GHCR push and the VPS half of woo-mcp, then gateway phase 1.

---

## 2026-10-17, session 6: GHCR, VPS, gateway phase 1

**Goal.** Push woo-mcp to GHCR and deploy it on the VPS, set the store timezone, then build
gateway phase 1 and pass GW-1 to GW-9.

**Proposed.**
- K: GHCR multi-arch push, VPS deploy with VWM re-checks, a permanent Job guard, then gateway
  phase 1 with Postgres, fx-mcp and nine pre-registered checks.
- C-code: the verifications, the implementation, the checks.

**Decided.** D-009 and D-010 both stay open but now carry verified facts. D-020 unchanged.

**Verified.** VWM-2/4/6/8 pass on the VPS. GW-1 to GW-9 all pass locally. Detail in
`docs/requirements-trace.md`.

**Built.** `scripts/check-cluster.sh`; store timezone Asia/Kolkata; `services/fx-mcp` and its
chart; `services/gateway` and its chart with a Postgres StatefulSet.

**AI errors caught.**
- **`wp option update gmt_offset 0` killed the bootstrap Job, invisibly.** It exits non-zero when
  the value is unchanged, and under `set -eu` that failed the Job. The Job still reported
  `Complete` because `backoffLimit` retried it and the retry took the SKIP branch. Both clusters
  showed `Complete 1/1` with an `Error` pod sitting next to a `Completed` one. Writing gmt_offset
  was also simply wrong: WordPress derives it. This produced the permanent guard,
  `scripts/check-cluster.sh`, which fails any Job with `status.failed > 0`.
- **The first guard fixture proved the wrong thing.** It used `/tmp`, which is fresh per pod, so
  the Job failed all four attempts and never reached `Complete`. That demonstrated the guard
  catching an outright failure, not the retry-masked case it exists for. Redone with a hostPath
  marker so the first pod fails and the second succeeds.
- **`DATABASE_URL` referenced `$(PGPASSWORD)` declared after it.** Kubernetes expands `$(VAR)`
  only against earlier entries, so the literal string was sent and Postgres replied `password
  authentication failed`, which reads like a wrong password.
- **Mounting the SDK's Streamable HTTP app in FastAPI does not run its lifespan.** The session
  manager's task group never started and every MCP request died with `Task group is not
  initialized`.
- **`last_error` read `ExceptionGroup`.** anyio wraps transport failures, so the status an
  operator reads said nothing. `_reason()` now unwraps to the first real cause and it reads
  `ConnectError`. Still type-only: a transport error's text can quote request headers.
- **C-code wrongly accused the gateway of flattening upstream schemas.** The Inspector showed a
  schema with no descriptions and no enum, and C-code reported the gateway as lossy. Checking
  rather than assuming showed the gateway's schema is byte-identical to woo-mcp's: the gateway is
  a faithful proxy and woo-mcp is the lossy end. The claim was corrected before any change was
  made to the gateway.
- **A dependency version was stated from memory and was wrong.** `psycopg[binary]==3.2.12` does
  not exist for python 3.15. Versions are now queried from the index before pinning.

**Nearly an error, avoided.** GHCR showed 5 package versions, 1 tagged and 4 untagged, and the
obvious move was to prune the untagged ones. All four turned out to be referenced by the tagged
manifest list, two as arch manifests and two as attestations. Pruning would have broken the image.
Checked digest by digest first; nothing was deleted.

**Security note.** The gateway bootstrap API key was printed into a chat transcript while being
retrieved for the GW-2 and GW-3 runs. It reaches only `gateway.localhost`, so the practical
exposure is nil today, but it must be rotated before the gateway gets a public Ingress on the VPS.

**Next.** Rotate the bootstrap key, then the dashboard and chat agent (C-01 to C-04), which are
what DOD-03 and DOD-04 still need. The gateway's VPS deploy also remains.
