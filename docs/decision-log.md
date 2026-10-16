# Decision log

Rules: see `PROJECT_INSTRUCTIONS.md` section 3.
A decision is `decided` only when the **Kapardhi's reason** field is filled in his own words and survived one "why not X?" question.
Tooling choices may have AI-drafted reasons, marked "AI-drafted, accepted by Kapardhi". Design choices the demo video must explain (MCP internals, security, local-to-prod) need Kapardhi's own words: D-001, D-006, D-009, D-013, D-014 and any new entry in those areas.
Reversals get a new entry. Old entries are never edited except to set status `superseded by D-xxx`.

## Index

| ID | Question | Blocks | Status |
|---|---|---|---|
| D-001 | Which MCP spec version does the gateway speak? | Gateway, Woo MCP server | open, needs spike |
| D-002 | Which local Kubernetes? | Day 1 | decided |
| D-003 | Which Ingress controller? | Day 1 | open |
| D-004 | Local domain approach | Day 1 | open |
| D-005 | Where do the WordPress and DB images and chart come from? | Day 1 | decided |
| D-006 | How does the Woo MCP server talk to the store? | Woo MCP server | open |
| D-007 | Language and MCP SDK for gateway and Woo MCP server | All backend code | decided, revisit after D-001 spike |
| D-008 | Gateway database | Gateway | open |
| D-009 | Tool name collision scheme | Gateway | open |
| D-010 | The two other upstream MCP servers | Gateway, demo | open |
| D-011 | LLM for the chat agent | Chat agent | open |
| D-012 | Dashboard login and invite flow | Team features | open |
| D-013 | API key format and hashing | Team features | open |
| D-014 | How the chat agent acts as the logged-in user | Chat agent | open |
| D-015 | Which stretch goal(s) to go deep on | After core passes | deferred |
| D-016 | Timeline and VPS target | Planning | open |
| D-017 | Local toolchain (Colima 0.10.3, Helm 4.x) | Day 1, all charts | decided |
| D-018 | Repo visibility before submission | Submission | decided |

---

## D-001: Which MCP spec version does the gateway speak?

**Why this matters.** The gateway is both an MCP server (to clients) and an MCP client (to upstreams). If the two sides disagree on protocol version, nothing works.

**Facts found (2026-10-14).**
- Spec `2026-07-28` was released on 28 Jul 2026. It removes the `initialize` handshake and the `Mcp-Session-Id` header. Each request carries its version and client info in `_meta`. Streamable HTTP requests must carry `Mcp-Method` and `Mcp-Name` headers. Source: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- The TypeScript, Python, Go and C# SDKs were updated to this version on release. Same source.
- The previous version is `2025-11-25`, which has sessions.

**Unknown.** Which version Claude Code, Cursor and MCP Inspector actually send today, and whether the Python and TypeScript SDKs still serve `2025-11-25` clients. This must be measured, not assumed.

**Options.**
- A. Gateway speaks only `2026-07-28`, both sides.
- B. Gateway speaks only `2025-11-25`, both sides.
- C. Gateway accepts both versions from clients, and talks to each upstream in the version that upstream supports.

**Tradeoffs.**
- A: stateless makes multi-replica gateway easy (stretch goal 7). Risk: a demo client that only speaks the old version fails.
- B: matches most deployed clients today. Gives up the stateless benefit. Sessions complicate multiple replicas.
- C: most robust. Most work.

**Claude's recommendation.** Do not decide from reading. Run a half-day spike first: a hello-world MCP server in the chosen SDK, connect Claude Code, Cursor and MCP Inspector, log the `MCP-Protocol-Version` header each one sends. Then decide. My prior is A if all three demo clients speak the new version, else C.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open, needs spike

---

## D-002: Which local Kubernetes?

**Options.** kind, k3d, Minikube. (Any of the three meets K-01.)

**Tradeoffs.**
- k3d: runs k3s in Docker. The VPS target is k3s, so local and prod are the same distribution. Same default Ingress controller, same default storage class (`local-path`). Smallest values-file diff.
- kind: very common, close to upstream Kubernetes. No default Ingress or dynamic storage class story that matches k3s, so more local-only config.
- Minikube: heavier. Addons differ from k3s.

**Claude's recommendation.** k3d, because "same Helm charts, configuration changes only" is easiest when local and VPS run the same distribution.

**Facts verified (2026-10-15).** Homebrew versions on this machine: k3d 5.9.0, kind 0.33.0, Minikube 1.39.0, kubectl 1.37.1. Cluster `gw-local` was created and k3d pulled `docker.io/rancher/k3s:v1.35.5-k3s1`. The node reports `v1.35.5+k3s1`. That tag is what `values-prod.yaml` must pin so the VPS runs the same k3s. See the K-01 row in `docs/requirements-trace.md` for the evidence.

**Kapardhi's choice:** k3d 5.9.0.

**Kapardhi's reason (own words):** Local and prod both run k3s, so there is one chart to defend.

**"Why not X?" asked and answer:**
Asked: "kind is closest to upstream Kubernetes. k3d bundles Traefik and local-path, so the charts could quietly depend on them and break on a reviewer's kind or EKS cluster. Why not kind?"
Answer: k3d bundles Traefik and local-path, the same as the k3s VPS. In my chart they show up only in values files, never in templates.

**What would change my mind:** If the VPS ends up on managed Kubernetes instead of k3s on a VM, or `scripts/check-charts.sh` shows the charts depend on k3s-only behaviour, test on kind. (AI-drafted, accepted by Kapardhi)

**Status:** decided

---

## D-003: Which Ingress controller?

**Facts found (2026-10-14).**
- Kubernetes retired the Ingress NGINX project. Maintenance stopped in March 2026. No more releases or security patches after that. Sources: https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/ and https://kubernetes.io/blog/2026/01/29/ingress-nginx-statement/
- The requirements explicitly ask for **Ingress** with stable URLs.

**Options.**
- A. Traefik (bundled with k3s and k3d).
- B. ingress-nginx.
- C. Gateway API (HTTPRoute) instead of Ingress.

**Tradeoffs.**
- A: zero install on k3d and k3s. Same on both sides. Standard `Ingress` objects work.
- B: retired. Hard to defend in a security review.
- C: the modern direction, but the requirements say Ingress. Using it risks reading as not following the requirements.

**Claude's recommendation.** A. Mention C in the tradeoffs note as the production direction.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-004: Local domain approach

The requirements say this must be documented.

**Options.**
- A. `*.localhost` (for example `store.localhost`, `gateway.localhost`). No setup in most browsers.
- B. `/etc/hosts` entries for names like `store.mcpgw.local`.
- C. Wildcard DNS services like `store.127.0.0.1.nip.io` or `sslip.io`.

**Tradeoffs.**
- A: no setup. But some CLI tools and DNS resolvers do not resolve `*.localhost`. The MCP client on my machine must reach the gateway, so this must be tested with Claude Code, not only a browser.
- B: works everywhere. Manual step per machine. Easy to document.
- C: no local edit. Depends on a third-party DNS service being up during the demo.

**Claude's recommendation.** No strong pick. Test A with Claude Code and curl first. If it fails anywhere, use B. Avoid C because the demo should not depend on an outside DNS service.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-005: Where do the WordPress and DB images and chart come from?

**Facts found (2026-10-14).**
- Bitnami changed its free catalog effective 28 Aug 2025. Versioned images moved to `bitnamilegacy` without updates, or need a Bitnami Secure Images subscription. Sources: https://github.com/bitnami/charts/issues/36215 and https://gitlab.com/backupscale/drubernetes/-/issues/3

**Options.**
- A. Write my own Helm templates around the official `wordpress` and `mariadb` (or `mysql`) images.
- B. Use the Bitnami chart with `bitnamilegacy` images.
- C. Use the Bitnami chart with a Bitnami Secure Images subscription.

**Tradeoffs.**
- A: I control and can explain every probe, limit, Secret and PVC. More work up front. WooCommerce install and setup need a bootstrap Job.
- B: fast start. Images are frozen with no security updates. A reviewer can ask "why ship unpatched images?".
- C: costs money. Adds an outside dependency.

**Claude's recommendation.** A. The requirement is that I understand the Kubernetes resources. Templates I wrote are easier to defend than a vendor chart with hundreds of values.

**Facts verified (2026-10-16).** `docker manifest inspect` against Docker Hub shows all three official images publish both architectures needed: `wordpress:latest` and `wordpress:cli` on `linux/amd64` and `linux/arm64/v8` (plus 386, arm/v6, arm/v7, ppc64le, riscv64, s390x), and `mariadb:latest` on `linux/amd64` and `linux/arm64/v8` (plus ppc64le, s390x). This covers an Ampere A1 aarch64 VPS and an x86 VPS.

**Kapardhi's choice:** A. Own Helm templates around the official `wordpress`, `mariadb` and `wordpress:cli` images.

**Kapardhi's reason:** Every probe, limit, Secret and PVC is ours, so each can be explained line by line. Official images are patched and multi-arch (arm64 and amd64), which covers both VPS options. Bitnami images are frozen. (AI-drafted, accepted by Kapardhi)

**"Why not X?" asked and answer:** Not asked. Tooling choice under the amended protocol.

**What would change my mind:** If the WooCommerce bootstrap Job takes more than one day, fall back to the Bitnami chart and log the patching risk. (AI-drafted, accepted by Kapardhi)

**Status:** decided

---

## D-006: How does the Woo MCP server talk to the store?

The requirements say this must be documented with a reason.

**Options.**
- A. WooCommerce REST API (`/wp-json/wc/v3/...`) over the cluster-internal Service, with a consumer key and secret from a Secret.
- B. WP-CLI.
- C. Direct database queries.

**Tradeoffs.**
- A: runs in its own pod. Uses WooCommerce business logic (stock, totals, hooks). Needs a bootstrap step that creates the API key and stores it in a Secret.
- B: WP-CLI needs the WordPress code on disk. That means `kubectl exec` into the WordPress pod (needs RBAC power) or sharing its volume. Both weaken isolation.
- C: skips WooCommerce logic. Order totals and stock can go wrong. Schema can change.

**Claude's recommendation.** A. Sub-decision to log later: how the consumer key is created at install time (a Helm hook Job running WP-CLI inside the WordPress image is one way).

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-007: Language and MCP SDK for gateway and Woo MCP server

**Options.**
- A. Python: FastAPI + official MCP Python SDK.
- B. TypeScript: Node + official MCP TypeScript SDK.
- C. Mixed: Python backend, TypeScript only for the React dashboard.

**Tradeoffs.**
- A: my strongest stack, fastest for me to build and explain. Must confirm the SDK covers both the client role and the server role at the version chosen in D-001.
- B: the TypeScript SDK is often first to get new spec features. One language with the dashboard.
- C: the dashboard is React in all options, so C is A with a stated split.

**Claude's recommendation.** A (which is C in practice), unless the D-001 spike shows the Python SDK is missing something the gateway needs.

**Kapardhi's choice:** A. Python with FastAPI and the official MCP Python SDK. React only for the dashboard.

**Kapardhi's reason:** Strongest stack, fastest to build and easiest to explain under questioning. The Python SDK was updated to spec 2026-07-28 on release. (AI-drafted, accepted by Kapardhi)

**"Why not X?" asked and answer:** Not asked. Tooling choice under the amended protocol.

**What would change my mind:** If the D-001 spike shows the Python SDK lacks a client or server feature the gateway needs, switch the gateway to TypeScript. (AI-drafted, accepted by Kapardhi)

**Status:** decided, revisit after D-001 spike

---

## D-008: Gateway database

Holds users, roles, hashed API keys, registered servers, encrypted upstream credentials, audit log.

**Options.** Postgres in the cluster. SQLite on a PVC. Reuse the store's MariaDB with a separate schema.

**Tradeoffs.**
- Postgres: separate failure domain from the store. Supports more than one gateway replica later.
- SQLite: simplest. Blocks running two gateway replicas (stretch goal 7).
- Reuse store DB: fewer pods. Couples the gateway to the store. A store problem takes down the audit log. Bad isolation story.

**Claude's recommendation.** Postgres.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-009: Tool name collision scheme

The requirements say the scheme must be documented.

**Options.**
- A. Always prefix: `<server_slug>__<tool>` for every tool.
- B. Prefix only when two servers collide.
- C. Keep names, add server in the tool description.

**Tradeoffs.**
- A: stable names. Adding a new server never renames existing tools, so saved prompts and client configs do not break. Makes the routing rule trivial.
- B: shorter names, but a tool's name changes when an unrelated server is added. Hard to defend.
- C: two tools with the same name in one list. Clients may reject or shadow one.

**Claude's recommendation.** A. Sub-decisions: slug rules (lowercase, max length), separator character, and checking the result against the MCP tool-name rules of the chosen spec version.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-010: The two other upstream MCP servers

**Constraints from the Definition of Done.**
- One demo step kills the pod of an upstream and shows the others still work. So at least one upstream must run in my cluster.
- One demo step needs a single prompt that uses tools from two different servers.

**Options.**
- A. Write two small in-cluster servers that pair with orders (for example currency conversion and shipping estimate). Prompt: "total of today's orders in EUR".
- B. One in-cluster server I write, plus one public remote MCP server.
- C. Two public remote MCP servers.

**Tradeoffs.**
- A: full control. Demo has no outside dependency. Shows I can write MCP servers. Risk: looks like toys.
- B: proves the gateway works with a server I did not write (real interop). Demo depends on that service and its auth.
- C: pod-kill step needs the Woo server to be the one killed. Two outside dependencies.

**Claude's recommendation.** B, if a stable public Streamable HTTP server with a static token exists. Else A. Choose the pair so the cross-server prompt is natural, not forced.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-011: LLM for the chat agent

The requirement is the tool loop, not answer quality. The key is a Secret like any other.

**Options.** Hosted free tier with tool calling (for example Gemini or Groq). Local model with Ollama in the cluster. Paid API.

**Tradeoffs.**
- Hosted free tier: light on the cluster. Rate limits can hit during the demo.
- Ollama in cluster: no outside dependency. Needs a lot of RAM and CPU on a laptop and on a small VPS. Small models are weaker at tool calling.
- Paid: most reliable. Costs money.

**Claude's recommendation.** Hosted free tier, with the provider behind one small interface so I can switch in one values change.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-012: Dashboard login and invite flow

API keys are for MCP clients. People still need to log in to the dashboard.

**Options.** Email + password with server sessions. Invite link that sets a password. OAuth login (overlaps stretch goal 3).

**Claude's recommendation.** Invite link (single-use, expiring token) that sets a password, then a server-side session cookie. Smallest thing that covers "invite team members".

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-013: API key format and hashing

**Options.**
- A. Key = short public prefix + long random secret. Store prefix in clear for lookup, store SHA-256 of the full key.
- B. Same format, store bcrypt or argon2 hash.

**Tradeoffs.**
- A: keys are high-entropy random strings, so brute force is not the threat a slow hash defends against. Fast lookup on every MCP call.
- B: slow hash on every tool call adds latency for little gain on random keys. Slow hashes matter for human passwords (D-012).

**Claude's recommendation.** A for API keys, argon2 for dashboard passwords. Show the raw key once at creation.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-014: How the chat agent acts as the logged-in user

Its calls must appear in the audit log under that user.

**Options.**
- A. The agent calls the gateway's MCP endpoint with a short-lived internal token minted for the logged-in user's session.
- B. The agent uses the user's own API key.
- C. The agent calls gateway internals directly and passes the user id.

**Tradeoffs.**
- A: same path as an external client, so the agent proves the gateway works. Users without an API key can still chat.
- B: forces every user to create a key first. Key would need to sit in the browser or server memory.
- C: skips the auth and routing path the requirements want exercised. Easy to forget an audit write.

**Claude's recommendation.** A.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**"Why not X?" asked and answer:**
**What would change my mind:**
**Status:** open

---

## D-015: Which stretch goal(s) to go deep on

Deferred until the core Definition of Done passes. Decide then, with time left as an input.
The four that interest me most: 6 Security hardening, 2 Tool permissions, 1 VPS deployment, 8 Observability.

**Status:** deferred

---

## D-016: Timeline and VPS target

**Needed from Kapardhi.** Start date and deadline, and which VPS or free tier will run k3s.

**Kapardhi's choice:**
**Kapardhi's reason (own words):**
**Status:** open

---

## D-017: Local toolchain (Colima 0.10.3, Helm 4.x)

**Why this matters.** k3d (D-002) runs k3s inside containers, so it needs a container runtime. This machine had none. The requirements also mandate Helm and forbid Kustomize, and Helm 4 is a major version. Both are small toolchain choices, so they are batched into one entry under `PROJECT_INSTRUCTIONS.md` section 3. No "why not X?" was asked for that reason.

**Facts verified (2026-10-15).** Host is macOS 15.6.1, Apple M1, 8 cores, 8 GB RAM, arm64. Installable versions: Colima 0.10.3 (with Lima 2.2.1), Docker Desktop 4.95.0, OrbStack 2.2.4, Rancher Desktop 1.24.0, Docker CLI 29.9.1, Helm 4.3.1. Colima 0.10.3 defaults to the macOS Virtualization.framework VM type (`vz`) and `virtiofs` mounts. Helm 4.3.1 talks to the k3d cluster and lists k3s's own releases, `traefik-39.0.701+up39.0.7` and `traefik-crd-39.0.701+up39.0.7`, app version v3.6.12. Helm reports `KubeClientVersion:"v1.37"`. Helm 3 support dates, checked 2026-10-16: the last Helm 3 feature and bug-fix release was 9 September 2026, and security fixes continue until 10 February 2027, after which Helm 3 receives nothing. An earlier schedule saying bug fixes ended 8 July 2026 and security fixes end 11 November 2026 was superseded. Source: https://helm.sh/blog/helm-v3-end-of-life

**Container runtime options.**
- A. Colima. CLI only. Explicit CPU, memory and disk flags.
- B. Docker Desktop. Most conventional. Heaviest. Licence terms apply to larger organisations.
- C. OrbStack. Light on Apple Silicon. Proprietary, free for personal use.
- D. Rancher Desktop. Bundles its own k3s, which overlaps with k3d.

**Container runtime tradeoffs.**
- A: smallest moving parts, and the resource ceiling is set on the command line, which is easy to show in a walkthrough. Holds its allocation while running.
- B: everyone recognises it. Largest idle footprint on an 8 GB machine.
- C: gives memory back when idle. Proprietary, and the licence is a question in a work context.
- D: two k3s installations on one machine invites confusion about which cluster is under test.

**Helm options.**
- A. Track Helm 4.x, no patch pin.
- B. Pin one Helm 4 patch.
- C. Target Helm 3.

**Helm tradeoffs.**
- A: follows upstream. Patch drift between machines is possible, as happened here: 4.3.0 was quoted and 4.3.1 installed.
- B: reproducible, but needs a deliberate bump and a reason each time.
- C: matches most tutorials and CI images today. Gives up Helm 4 behaviour and ages immediately.

**Claude's recommendation.** Runtime: Colima or OrbStack, because on 8 GB the memory behaviour matters more than the brand. Helm: none offered, this was Kapardhi's call.

**Kapardhi's choice:** Colima 0.10.3 as the container runtime. Helm 4.x, not pinned to a patch; installed 4.3.1. Charts stay at `apiVersion: v2`.

**Kapardhi's reason:** Colima is open source, so there is no licence question, and its fixed 5 GB cap stops the cluster from pushing an 8 GB Mac into swap. Helm 3 stopped getting bug fixes in September 2026. Charts stay `apiVersion: v2`, so Helm 3 users can still install them. (AI-drafted, accepted by Kapardhi)

**"Why not X?" asked and answer:** Not asked. Batched tooling choice under `PROJECT_INSTRUCTIONS.md` section 3.

**What would change my mind:** If the full stack does not fit in 5 GB while macOS still has headroom, try OrbStack. If a reviewer cannot install with Helm 3, or Helm 4 server-side apply breaks an upgrade or rollback, document a Helm 3 path. (AI-drafted, accepted by Kapardhi)

**Status:** decided

---

## D-018: Repo visibility before submission

**Why this matters.** The repo holds the decision log, the defence notes and the whole solution. It is public by default on GitHub. The submission needs a repo link, so it cannot stay private forever.

**Facts verified (2026-10-16).** `gh repo view kapardhi03/mcp-gateway-k8s` reported `PUBLIC` with 0 stars and 0 forks, so no fork or star history was lost by switching. After `gh repo edit --visibility private`, the same command reports `PRIVATE`. The GitHub repo was renamed from `MCP-Gateway` to `mcp-gateway-k8s`; the old name still redirects, but the local `origin` URL is stale.

**Options.**
- A. Private until submission day, then public.
- B. Public throughout.
- C. Private permanently, share by invite at submission.

**Tradeoffs.**
- A: nothing is copyable during the open window, and the submission still gets a public link.
- B: anyone can read the solution and the defence notes while the work is open.
- C: needs the reviewer to accept an invite, which adds a step the submission form does not ask for.

**Claude's recommendation.** None offered. This was housekeeping, not a design choice.

**Kapardhi's choice:** A. Private now, public on submission day.

**Kapardhi's reason:** No one copies the charts during the open window; interview prep stays private. The submission form needs the repo, so it goes public on submission day. (AI-drafted, accepted by Kapardhi)

**"Why not X?" asked and answer:** Not asked. Housekeeping under the amended protocol.

**What would change my mind:** Not recorded. Housekeeping.

**Status:** decided
