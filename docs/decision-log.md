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
| D-003 | Which Ingress controller? | Day 1 | decided |
| D-004 | Local domain approach | Day 1 | decided |
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
| D-016 | Timeline and VPS target | Planning | decided |
| D-017 | Local toolchain (Colima 0.10.3, Helm 4.x) | Day 1, all charts | decided |
| D-018 | Repo visibility before submission | Submission | decided |
| D-019 | How dev and prod secrets reach the chart | Store chart, all charts | open, needs Kapardhi's words |
| D-020 | Image registry and build (GHCR, multi-arch) | All images | decided |

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

**Build proceeds on the recommendation (2026-10-17).** The Woo MCP server is being built as
option C, accepting both protocol versions, on Claude's recommendation and with the spike
measurements in `docs/requirements-trace.md` behind it. This entry stays **open**: it is not
decided until Kapardhi gives his choice and his reason in his own words. The build is reversible,
because the spike showed one SDK 2.3.0 server serving both versions at once with no special
handling, so option A or B would be a narrowing, not a rewrite.

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

**Facts verified (2026-10-16).** The k3d cluster `gw-local` ships Traefik by default: `kubectl get ingressclass` returns `traefik  traefik.io/ingress-controller`, installed by k3s's Helm controller as chart `traefik-39.0.701+up39.0.7`, app v3.6.12. `curl -sI http://localhost` returns Traefik's 404 with no routes defined.

**Kapardhi's choice:** A. Traefik, with standard `Ingress` objects.

**Kapardhi's reason:** Bundled with k3s on both sides, ingress-nginx is retired, and the requirements say Ingress, not Gateway API. (AI-drafted, accepted by Kapardhi)

**"Why not X?" asked and answer:** Not asked. Tooling choice under the amended protocol.

**What would change my mind:** Not recorded.

**Status:** decided

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

**Measured (2026-10-16), before choosing.** `store.localhost` was resolved and fetched four ways against the running k3d cluster, with Traefik answering and no route defined yet. All four reached Traefik.

| Client | Resolves | Reached Traefik |
|---|---|---|
| macOS resolver (`getaddrinfo`, `dscacheutil`) | yes, `127.0.0.1` and `::1` | n/a |
| `curl` | yes | yes, HTTP 404 |
| Python `httpx` | yes | yes, HTTP 404 |
| Node `fetch` | yes | yes, HTTP 404 |
| Browser | yes | yes, Traefik's `404 page not found` |

No fallback was needed, so `*.gw.test` with `/etc/hosts` was not used. `.local` was excluded on purpose: macOS routes it to mDNS.

**Kapardhi's choice:** A. `*.localhost`.

**Kapardhi's reason:** Passed curl, httpx, Node fetch and a browser with no machine setup, so a reviewer can run it without editing `/etc/hosts`. `.local` avoided because macOS sends it to mDNS. (AI-drafted, accepted by Kapardhi)

**"Why not X?" asked and answer:** Not asked. Settled by measurement under the amended protocol.

**What would change my mind:** Any client in the demo fails to resolve it; then `/etc/hosts` with `*.gw.test`. (AI-drafted, accepted by Kapardhi)

**Status:** decided. In use: `charts/store/values-local.yaml` sets `ingress.host: store.localhost`, verified serving HTTP 200 on 2026-10-16.

**Addendum 2026-10-17: the prod host.** D-004 chose the local domain. Prod needs one too.
There is no paid domain for this project, so prod uses `store.34.93.101.10.sslip.io`.
sslip.io resolves any `<ip>.sslip.io` name to that IP, so the VPS static IP `34.93.101.10`
gets a hostname with nothing to buy and no DNS to configure. Local stays `*.localhost`.

This is the option C that D-004 rejected for local, and the reason it was rejected still
stands: it depends on a third-party DNS service being up during the demo. It is accepted
for prod because the alternative is buying a domain, and because the local demo path, which
is where the Definition of Done runs, does not touch sslip.io. If sslip.io is down during
the demo, prod is reachable by IP and local is unaffected.

This addendum records a new fact. It does not change the D-004 choice.

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

**Build proceeds on the recommendation (2026-10-17).** The Woo MCP server is being built as
option A, the WooCommerce REST API. This entry stays **open** until Kapardhi gives his words.

**Verified against WooCommerce 11.2.1 source, not documentation (2026-10-17).** Read from the
running pod at `wp-content/plugins/woocommerce/includes/class-wc-rest-authentication.php`.

1. **Auth over plain HTTP is OAuth 1.0a one-legged, not basic auth.** `authenticate()` lines
   206-221 read:

   ```php
   if ( is_ssl() ) {
       $user_id = $this->perform_basic_authentication();
   }
   if ( $user_id ) { return $user_id; }
   return $this->perform_oauth_authentication();
   ```

   Basic auth is attempted only under TLS. The cluster-internal Service is plain HTTP, so
   woo-mcp must sign with OAuth 1.0a. Kapardhi's prior was correct.

2. **The signature base string uses the store's home URL, not the Host header.** Line 581:

   ```php
   $base_request_uri = rawurlencode( get_home_url( null, $request_path, is_ssl() ? 'https' : 'http' ) );
   ```

   This is the trap. woo-mcp will connect to `http://<service>.<ns>.svc.cluster.local/...`
   but the server builds its base string from `get_home_url()`, which is
   `http://store.localhost` locally and `http://store.34.93.101.10.sslip.io` on the VPS.
   The client must sign the home URL while connecting to the Service address, or every
   signature fails. Two different values, one request.

3. **Consumer keys are stored hashed, secrets in clear.** `wc_api_hash()` in
   `wc-core-functions.php:1311` is `hash_hmac( 'sha256', $data, 'wc-api' )`: a fixed key,
   no salt, fully deterministic. `get_user_data_by_consumer_key()` line 733 hashes the
   incoming key and looks it up in `woocommerce_api_keys.consumer_key`. The secret is stored
   as-is and compared with `hash_equals()` at line 386. Because the hash is deterministic,
   a key/secret pair can be generated outside WordPress and inserted directly, which is what
   lets `dev-secrets.sh` pre-generate it with no pod ever writing a Kubernetes Secret.

4. **Signature algorithm.** Line 603: `base64_encode( hash_hmac( $algo, $string_to_sign, $secret, true ) )`,
   where `$algo` comes from `oauth_signature_method` with the `HMAC-` prefix stripped, so
   `HMAC-SHA256` is supported.

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

**Build proceeds on the recommendation (2026-10-17).** The gateway is being built as option A,
always prefix, `<server_slug>__<tool>`. This entry stays **open** until Kapardhi gives his words.

**Tool-name rules verified in BOTH spec versions before writing the scheme (2026-10-17).**
Read from the specification pages, not from an SDK or a client's behaviour.

Both versions state the identical rules, word for word:

- Tool names **SHOULD** be between 1 and 128 characters in length (inclusive).
- Tool names **SHOULD** be considered case-sensitive.
- "The following **SHOULD** be the only allowed characters: uppercase and lowercase ASCII letters
  (A-Z, a-z), digits (0-9), underscore (\_), hyphen (-), and dot (.)"
- Tool names **SHOULD NOT** contain spaces, commas, or other special characters.
- Tool names **SHOULD** be unique within a server.

**Regex.** `^[A-Za-z0-9_.-]{1,128}$`, at SHOULD level in both versions. There is no MUST-level
constraint and no pattern in the schema itself.

Sources:
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools

**What this means for the scheme.** `__` is two underscores, inside the allowed set, so
`woo__list_products` is conformant in both versions. The 128-character budget is generous: the
longest current tool name is `woo__update_order_status` at 24.

**The 2026-07-28 version adds a note that endorses this decision directly**, and it is worth
quoting because it also rules out an alternative:

> "Clients or proxies that aggregate tools from multiple servers **MAY** encounter naming
> collisions (for example, two servers each exposing a `search` tool) and **SHOULD** implement a
> disambiguation strategy such as prefixing tool names with a server identifier. The server `name`
> (from `serverInfo`) is not guaranteed to be unique across servers and **SHOULD NOT** be relied
> upon for disambiguation."

So the slug must be assigned by the gateway and stored in its own registry. Taking it from the
upstream's `serverInfo.name` is explicitly discouraged. The 2025-11-25 page carries no equivalent
note, so this is guidance the newer version adds rather than changes.

**One caveat found while checking.** A stricter `^[a-zA-Z0-9_]{1,64}$` is reported in the wild as a
*client-side* rule, not spec text. `__` survives it but a dot or hyphen would not, and 64 rather
than 128 is the tighter budget. The scheme therefore sticks to letters, digits and underscores
only, which satisfies both the spec and the stricter client rule.

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

**Phase 1 proceeds on option A, in-cluster only (2026-10-17).** Two upstreams the gateway talks
to: `woo-mcp` and a new `fx-mcp`. Entry stays **open** until Kapardhi gives his words.

**Verified before choosing: GitHub's remote MCP server would work as a third upstream.**
Endpoint `https://api.githubcopilot.com/mcp/`. GitHub's own install guides show Streamable HTTP
with a personal access token sent as a static bearer header, which is exactly the shape the
gateway's registry stores (`auth header type` + credential):

```
claude mcp add-json github '{"type":"http","url":"https://api.githubcopilot.com/mcp/",
  "headers":{"Authorization":"Bearer YOUR_GITHUB_PAT"}}'
```

Sources: https://github.com/github/github-mcp-server and
https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/set-up-the-github-mcp-server

Caveats worth recording. Several clients default to OAuth and treat the PAT as the alternative,
and at least one reported failure was an OAuth path overriding the bearer header rather than a
server limitation. **No token was created.** This is recorded so the option is proven available
for phase 2 or for the demo's "server I did not write" point, not because phase 1 needs it.

**The second in-cluster upstream: `fx-mcp`, backed by Frankfurter.**
`https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,GBP,INR` returned HTTP 200 with
**no Authorization header of any kind**, data sourced from the ECB. Measured 2026-10-17:

```
{"amount":1.0,"base":"USD","date":"2026-10-16","rates":{"EUR":0.88865,"GBP":0.74989,"INR":94.96}}
```

It also exposes a dated endpoint, `/v1/2026-10-16?base=USD&symbols=EUR`, which gives unit tests a
fixed rate to assert against instead of a moving one. Free and keyless was verified by calling it,
not by reading its marketing. `https://open.er-api.com/v6/latest/USD` is a keyless fallback if
Frankfurter goes away.

Why this pairing. The Definition of Done needs one prompt that uses two different upstreams.
"Convert today's order total to EUR" needs orders from `woo-mcp` and a rate from `fx-mcp`, which is
a natural question rather than a contrived one, and neither upstream depends on the other.

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

**Facts measured (2026-10-14 to 2026-10-16).** Oracle Always Free Ampere A1 was attempted in `ap-hyderabad-1`, the tenancy home region and the only region where Always Free A1 exists. Two runs, **265 launch attempts** (148 then 117), spread over roughly 36 hours with a hard deadline of 2026-10-16 20:00 IST. Result: 0 instances. Roughly 290 `Out of host capacity` rejections and 8 HTTP 429 throttles. Nothing was misconfigured: `oci limits resource-availability get` showed 41 A1 cores and 277 GB available with 0 used, auth worked, and the VCN, internet gateway, route table, security list and public subnet were all `AVAILABLE`. `ap-hyderabad-1` has a single availability domain, so each cycle was one attempt. Evidence: `~/oci-retry/launch.log` (outside the repo).

**Options after the Oracle attempt failed.**
- A. Keep waiting on Oracle A1.
- B. Google Cloud $300 free trial, x86 VM, k3s.
- C. A paid VPS.

**Tradeoffs.**
- A: free forever if it ever lands, but 265 attempts produced nothing and there is no signal about when capacity returns.
- B: no spend inside the trial credit, available immediately, x86 rather than arm64. The chart's images are multi-arch (D-005), so the architecture change costs nothing.
- C: reliable and immediate, but costs money for a project that does not need to.

**Kapardhi's choice:** B. Google Cloud trial, x86 VM, k3s.

**Kapardhi's reason:** Zero spend; Oracle Hyderabad had no A1 capacity after 265 attempts. (AI-drafted, accepted by Kapardhi)

**"Why not X?" asked and answer:** Not asked. Infrastructure choice under the amended protocol.

**What would change my mind:** An Oracle A1 instance becomes available. (AI-drafted, accepted by Kapardhi)

**Note.** Nothing is deleted on Oracle. The VCN, gateway, route table, security list and subnet cost nothing under Always Free, and `~/oci-retry/launch-a1.sh` can be restarted against them at any time.

**Billing evidence (2026-10-16).** The Cloud Billing API does not expose trial status: the full v1 response for billing account `01F0BC-06CF08-82155F` contains only `name`, `open`, `displayName`, `masterBillingAccount`, `parent` and `currencyCode`, and `open: true` is equally true of a paid account. Confirmed in the console instead, read by Kapardhi: "You're in free trial. 0 out of ₹28,797 credits used. Expires 15 January 2027." Upgrade to a paid account was not clicked. A budget alert was created at ₹4,755, the USD 50 equivalent at 95.10 INR/USD on 2026-10-16; the API rejects a USD budget on an INR billing account.

**What was built (2026-10-16).**

| Item | Value |
|---|---|
| Project | `mcp-kb8` |
| VM | `gw-prod`, `asia-south1-a`, e2-standard-2 (2 vCPU, 8 GB), 50 GB pd-balanced |
| OS | Ubuntu 24.04 LTS amd64, matching the version chosen for the Oracle attempt |
| Static IP | `34.93.101.10` |
| Prod host | `store.34.93.101.10.sslip.io` |
| k3s | `v1.35.5+k3s1`, the same version as the local k3d cluster |
| SSH | IAP TCP forwarding only, `35.235.240.0/20` on tag `k3s-prod`. `default-allow-ssh` and `default-allow-rdp` deleted. No public SSH port |
| API server | 6443 never opened; `kubectl` reaches it through an SSH tunnel on `127.0.0.1:16443` |

**Why `mcp-kb8` and not a dedicated `gw-prod-*` project.** A dedicated project was the plan, but
`gcloud projects create` failed with `you have exceeded your allotted project quota`: the account already
holds 12 active projects and none were pending deletion. Deleting one to make room was rejected, because
`gen-lang-client-0028724881` may be serving a live ARTHRYX product and the risk is not worth a cosmetic
project name. `mcp-kb8` was created the same day for this work, had billing linked and the compute and IAP
APIs enabled, and held no resources. The budget has no project filter, so it covers every project on the
billing account regardless.

**Cost.** About ₹7,056 per month, from the Cloud Billing Catalog API for `asia-south1` on-demand:
vCPU ₹2.514838/h x 2, RAM ₹0.336990/GiB-h x 8, pd-balanced ₹11.518650/GiB-month x 50, static IP ₹1.151865/h.
Paid from the ₹28,797 trial credit, which covers about four months. The trial ends 15 January 2027.
No card charge is possible without a manual upgrade, and `CLAUDE.md` now forbids that upgrade outright.
The budget alert was raised from ₹4,755 to ₹7,500 so an alert means unexpected spend rather than the VM
simply running.

**Status:** decided

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

---

## D-019: How dev and prod secrets reach the chart

**Why this matters.** The requirements forbid secrets in source, in committed values files and in image layers. This is a security decision the demo video must explain, so under the amended protocol it needs Kapardhi's own words.

**Context.** The store chart needs a MariaDB root password, a MariaDB application password and a WordPress admin password. A chart that takes passwords as values puts them in `values-local.yaml` or on the `helm install` command line, where they reach shell history and, if anyone is careless, git.

**Options.**
- A. Chart takes `existingSecret` names only. Secrets are created outside Helm. A dev script generates random ones locally; production uses whatever the operator already has.
- B. Chart generates passwords with Helm's `randAlphaNum` and stores them in a Secret it owns.
- C. Chart takes passwords as values, documented as "do not commit".

**Tradeoffs.**
- A: nothing secret ever enters a values file or the chart's own templates. Needs one extra step before `helm install`. Works the same in dev and prod.
- B: convenient, but Helm regenerates on some upgrade paths and the value lands in the release's stored manifest.
- C: simplest to run, and the easiest to get wrong. One `git add` away from a leak.

**Claude's recommendation.** A.

**Built this way now, pending the entry.** The chart reads `existingSecret` names only, and `scripts/dev-secrets.sh` creates random Secrets with `kubectl` if and only if they do not already exist.

**Kapardhi's choice:** _TODO Kapardhi_

**Kapardhi's reason (own words):** _TODO Kapardhi_

**"Why not X?" asked and answer:** _TODO Kapardhi_

**What would change my mind:** _TODO Kapardhi_

**Status:** open, needs Kapardhi's words

---

## D-020: Image registry and build

**Why this matters.** Local k3d and the k3s VPS are different CPU architectures. Local runs
arm64 under Colima on an M1; the VPS is `x86_64` (`e2-standard-2`). One image has to work on
both, and a reviewer must be able to `helm install` without building anything.

**Decision (AI-drafted, accepted by Kapardhi).** GHCR (`ghcr.io/kapardhi03/...`), multi-arch
`linux/arm64` + `linux/amd64` built with `docker buildx`. The package stays **private** until
submission day, then goes public with the repo (D-018) so a reviewer can pull without
building. Prod pulls with an `imagePullSecret` created by `scripts/dev-secrets.sh`, never
committed.

**GHCR free-plan limits, verified 2026-10-17 before adopting.**

| | GitHub Free, private packages |
|---|---|
| Storage | 500 MB, **shared with Actions artifacts** |
| Data transfer out | 1 GB per month |
| Public packages | free and unmetered |
| Over quota, no payment method | usage is blocked |
| Over quota, payment method on file | billed, $0.25/GB storage, $0.50/GB transfer |

Source: https://docs.github.com/en/billing/concepts/product-billing/github-packages
("GitHub Packages usage is free for public packages"; Free tier row "500MB | 1GB").

**Do the limits fit? Yes, with one rule.** A multi-arch Python image is roughly 90-110 MB
compressed per architecture, so about 200 MB per pushed tag. 500 MB is therefore only two or
three retained tags, and GHCR keeps every version until it is explicitly deleted. That would
be tight if every build were pushed.

The rule that makes it fit: **local k3d never uses the registry.** `k3d image import` loads a
locally built image straight into the cluster, so the whole local phase, which is where all
the pre-registered checks run, costs zero GHCR storage and zero transfer. GHCR is used only
for VPS deploys, which are a handful of pushes and pulls. Old versions get pruned.

Transfer is not a concern: the VPS pulls amd64 only, about 100 MB, so 1 GB/month allows
roughly ten pulls.

**Cost risk.** None expected, and the failure mode is safe: with no payment method on the
account, exceeding quota blocks rather than bills. That is a demo risk, not a money risk.
Per the cloud cost rule in `CLAUDE.md`, nothing billable is created without Kapardhi's OK.

**Prerequisite not yet met.** The `gh` token on this machine has scopes
`admin:public_key, delete_repo, gist, read:org, repo`. Pushing to GHCR needs `write:packages`,
pulling needs `read:packages`, and pruning old versions needs `delete:packages`. This blocks
the VPS step only, not local work.

**Status:** decided
