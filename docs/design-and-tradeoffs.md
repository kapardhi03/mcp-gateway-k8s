# System design and tradeoffs

Draft. Kapardhi to edit for voice. Every decision here has a D-number in
`docs/decision-log.md` with the options that were considered and the reason one was picked.

## The shape

```
browser ──► gateway ──► woo-mcp  ──► WordPress + WooCommerce
            (dashboard)   fx-mcp   ──► Frankfurter
            (chat agent)
MCP client ─► gateway
```

One endpoint, `/mcp`. Clients get a single URL and a single key. The gateway holds every upstream
credential and every upstream URL. A client that can call seven tools has been told nothing about
where any of them live.

That is the whole idea, and most of the decisions below follow from protecting it.

## Serving both MCP protocol versions (D-001)

The spec moved from a session-based model to a stateless one. Clients in the wild send both.

- **Only the new one:** breaks Claude Code and MCP Inspector today.
- **Only the old one:** breaks the stateless clients the spec is moving toward.
- **Both, on one endpoint:** picked. The SDK's Streamable HTTP app handles both, so the cost is
  nearly zero and no client has to be told which URL to use.

This was settled with a spike that recorded what real clients actually send, not from the spec
text.

## A dynamic proxy, not generated code (D-009, D-010)

Upstream tools are discovered at runtime and republished under a `slug__tool` prefix. The
alternative was to generate a wrapper per tool at build time.

Dynamic wins because the registry is editable at runtime: an admin adds a server in the dashboard
and its tools appear without a rebuild or a restart. Prefixing is what makes two upstreams able to
expose `list_products` without colliding.

The cost is subtle and bit us. The SDK derives its argument validator from the function signature,
so a proxy function is synthesised from the upstream's JSON schema, and the upstream's exact schema
is then pinned over the derived one because the derived one is lossy.

**And keying the registry on tool name alone was a bug.** A tool whose schema changed under the
same name was skipped forever, so the gateway served a stale schema after woo-mcp added an enum.
It is now keyed on name plus a sorted-JSON fingerprint of the schema, so a changed schema forces a
rebuilt function.

## Tool aggregation, routing and failure handling (D-009, D-010)

The three together, because they are one mechanism seen from three angles.

**Aggregation.** On refresh the gateway asks every *enabled* upstream for its tool list,
concurrently. Each tool is republished as `slug__tool`, so `list_products` from woo becomes
`woo__list_products`. A client sees one flat list of seven tools and one endpoint.

Refresh runs on a 30 second background loop and also before any MCP request whose cached list is
older than three seconds. That second trigger is what makes a killed upstream disappear and a
registry change take effect promptly, instead of waiting for the slow loop.

**Routing.** The prefix is the routing key. `proxy.split()` turns `woo__list_orders` back into
`("woo", "list_orders")`, the registry gives the upstream row for that slug, and the call goes
there and nowhere else. A call for a slug that is not registered, or for one that is disabled,
fails before any network call.

**Failure handling, and what each failure looks like.**

| Failure | What the client sees |
|---|---|
| One upstream dead | Its tools are absent. The others are returned. Status reads `Unreachable` with a reason. |
| One upstream slow | Its own timeout, 8s by default, then as above. The fan-out is concurrent, so one slow upstream costs 8s total, not 8s each. |
| Tool raises upstream | A `ToolError` carrying the upstream's message, so the model can act on it. |
| Transport error | A `ToolError` naming the exception type, never its text, because the text can quote request headers. |
| Upstream disabled by an admin | Tools vanish from `tools/list` within the refresh window. The pod keeps running; this is a registry flag, not a scaling action. |

The alternative, serial queries under one global timeout, means a single slow upstream starves the
others and the client gets a short list with no explanation.

Verified by scaling woo-mcp to zero on both clusters: the list still returned the fx tools in
under a second against an eight second budget, and woo read `Unreachable` with `ConnectError`.

**Use `scale --replicas=0`, not `delete pod`, to demonstrate this.** A pod delete self-heals in
about four seconds, faster than the health loop and faster than the registry cache, so nothing
visible happens. That is a point in Kubernetes' favour and a bad demo.

## Postgres for the gateway, separate from the store's MariaDB (D-008)

The gateway needs a registry, users, sessions, keys and an audit log. Reusing the store's MariaDB
would couple the control plane to the thing it controls: a store database problem would take out
authentication and the audit log at the same moment.

Separate StatefulSet, separate failure domain, and it can back more than one gateway replica later.

## Helm only, with cluster-specific values pushed out to values files (D-002)

`ingressClassName`, `storageClassName`, hostnames, TLS and the issuer never appear in a template.
They come from `values-local.yaml` or `values-prod.yaml`. The point is that a reviewer can install
these charts on kind or EKS without editing a template.

`scripts/check-charts.sh` enforces it by grepping the templates. It is crude, and it caught a
template **comment** of mine containing the word Traefik. The comment got reworded rather than the
guard loosened.

## API keys hashed with SHA-256, passwords with argon2id (D-012, D-013)

Deliberately opposite, for a reason that is easy to get backwards.

An API key is 256 bits of CSPRNG output. There is no dictionary to attack, so a slow hash buys
nothing and would cost on every single tool call. A human password is the reverse: low entropy,
attacked with a dictionary, and verified rarely. So keys get a fast hash and passwords get a slow
one.

Keys carry an 8-character clear prefix so a row can be found without scanning, and only the hash of
the whole key is stored, so a lost key cannot be recovered. Only recreated.

## The chat agent talks to its own public endpoint (D-011)

The agent runs inside the gateway process, and still reaches its tools over HTTP to the gateway's
own `/mcp`, using a short-lived key minted for the signed-in user.

Calling the tool functions in-process would be simpler and faster. It would also create a second,
privileged path that nothing else in the demo exercises, where a bug would be invisible to every
other check. As built, the agent is the same kind of client as Claude Code: same endpoint, same
prefixes, same timeouts, same failures. Disabling an upstream removes its tools from the agent for
free, because the agent asks the same registry everyone else asks.

The key is minted per turn and deleted when the turn ends, with a five minute expiry as the
backstop if the process dies mid-turn.

### Model choice and cost control

Claude Haiku 5.5 through the Anthropic API. Credits are limited and cannot be topped up, so the
guards are tight and all of them are Helm values: six tool steps, 1024 max tokens per call, 200
turns per day across all users, 2000 characters of question, 6000 characters of tool result.

Two settings matter more than they look. `output_config.effort` is set to `low`, because thinking
is adaptive and always on and thinking tokens bill at the output rate. And
`disable_parallel_tool_use` is on, so a six-step cap means at most six calls rather than six rounds
of unbounded fan-out.

Measured: about **$0.0005 per question**, against an estimate of $0.004 in D-011. The daily cap is
therefore roughly ten cents a day at worst.

**The Gemini fallback is a seam, not an omission.** `llm.provider` selects a provider and
`gateway/llm.py` defines the interface. Only the Anthropic adapter is written. Writing a Gemini
adapter with no key to test it against would put untested code on the one path that exists for when
the credits run out, which is the worst possible moment to find out it does not work. Choosing
`gemini` today fails immediately with a message saying exactly that.

## DuckDNS rather than sslip.io for TLS (D-022)

Let's Encrypt limits certificates to 50 per registered domain per week, globally across all
accounts, and uses the Public Suffix List to decide what the registered domain is.

`sslip.io` is **not** on that list, so `store.34.93.101.10.sslip.io` would share one global bucket
with every sslip.io user in the world and could be refused mid-demo for reasons nothing to do with
this project. `duckdns.org` **is** on the list, so `kapardhi-gw.duckdns.org` gets its own bucket.

Checked by downloading the 16,570-line list and grepping it, with `github.io` as a control. No
wildcard-IP service is on it: sslip.io, nip.io, traefik.me, localtest.me, lvh.me, local-ip.co,
1u.ms and xip.io were all absent.

The move cost one values change per chart, because the hostname was already a per-environment
value.

## What changes for production

Everything below is a values difference. No template changes, which is what
`scripts/check-charts.sh` exists to keep true.

| | Local (k3d) | VPS (k3s) |
|---|---|---|
| **DNS** | `*.localhost`, resolved by the browser, nothing configured | `store.kapardhi-gw.duckdns.org` and `gateway.kapardhi-gw.duckdns.org`, both A records to the static IP. DuckDNS because it is on the Public Suffix List and so gets its own Let's Encrypt rate-limit bucket (D-022). |
| **Ingress** | `className: traefik`, plain HTTP, no TLS block | Same class, plus `ingress.tls.enabled` and a `cert-manager.io/cluster-issuer` annotation. Certificates from Let's Encrypt over HTTP-01. A cluster-level Traefik config redirects HTTP to HTTPS. |
| **Storage class** | `local-path`, k3d's default, backed by a directory in the node container. Lost if the cluster is deleted. | `local-path` again, but on the VPS it is a real directory on a 50 GB persistent disk. Same class name, very different durability. Neither template names it; both come from values. |
| **Secrets** | `scripts/dev-secrets.sh` generates random values into Kubernetes Secrets. No GHCR pull secret needed, because k3d imports images directly. | The same script run **on the VPS context**, generating fresh values there. No value is ever copied from local. Adds the GHCR imagePullSecret, because prod pulls multi-arch images from a private registry. The LLM key is typed by hand at a `read -s` prompt and never written to a file. |
| **Images** | Built locally and imported with `k3d image import` | Pulled from GHCR, multi-arch, pinned tags in `values-prod.yaml` so a rollback does not depend on remembering a `--set` |
| **Proxy headers** | Not set. Nothing in front of the pod. | `forwardedAllowIps: "*"`, or the session cookie's `Secure` flag can never turn on behind a TLS-terminating proxy. |
| **WordPress** | `home` and `siteurl` are `http://store.localhost` | `https://store.kapardhi-gw.duckdns.org`, plus `trustForwardedProto` so WordPress believes the proxy instead of redirect-looping. |

**Two prod values are easy to get wrong, and both have a comment in the values file saying why.**

`woo-mcp`'s `store.homeUrl` keeps the **http** scheme even though the site is https. WooCommerce
builds its OAuth base string with `get_home_url(null, $path, is_ssl() ? 'https' : 'http')`, so the
host follows the stored home URL while the scheme follows `is_ssl()`, which is false for
in-cluster plain-HTTP calls. New host, old scheme. Setting it to https gives a 401 that looks
exactly like a wrong credential.

And `forwardedAllowIps`, above. uvicorn parses forwarded headers only for listed clients and
defaults to 127.0.0.1, which the ingress controller is not.

**Upgrade and rollback.** `helm upgrade` with the prod values file; `helm rollback <release> <n>`
to go back. The store's bootstrap Job is a `post-upgrade` hook with
`hook-delete-policy: before-hook-creation`, so it re-runs on every upgrade and every step inside
it is guarded, which is what makes re-running safe.

## What is deliberately not here

- **No service mesh.** The isolation this needs is "only the gateway may reach the MCP servers",
  which a NetworkPolicy expresses in a few lines.
- **No horizontal scaling of the gateway.** It is one replica. The registry cache is per process,
  so a second replica would need shared invalidation. Postgres already supports it; the code does
  not yet.
- **No migration tool.** Schema is `CREATE TABLE IF NOT EXISTS` plus guarded `ALTER TABLE`, which
  is honest about what this is.
- **No rate limiting.** Named in the threat model as a known weakness rather than hidden.

## The thing this project kept relearning

Three bugs had the same shape, and it is the most useful thing here.

1. A bootstrap Job failed, retried, and reported `Complete` because a later attempt succeeded.
2. `store_timezone()` read PHP's process timezone instead of the site timezone, and the tests that
   "covered" it mocked a payload WordPress never sends, so they agreed with the bug.
3. A Traefik redirect was applied with a wrong key path. Helm reported the upgrade deployed at
   revision 2 and the Deployment did not change. Nothing logged an unknown key.

In each case a check was green while the thing it claimed to verify was false. The responses:
`scripts/check-cluster.sh` fails any Job with `status.failed > 0`, regression tests are proved by
mutation (reintroduce the fault, confirm the test fails, restore), and a configuration change is
verified by its observable effect rather than by the tool's exit code.

A check that passes under both the correct and the incorrect implementation is not evidence,
however green it looks.
