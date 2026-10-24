# Threat model

Draft. Kapardhi to edit for voice.

**One thing to confirm before this is final.** The requirements ask for a threat model covering
four named topics, and `docs/requirements-trace.md` row S-07 records that count but not the names.
They are not written down anywhere in this repo. The sections below are the ones this system
actually needs. Check them against the requirements document and tell me which headings to use.

## What this system is, in security terms

One public endpoint holds credentials for several upstream services and hands tool access to a
team. The whole point is that a user gets to use an upstream without ever holding its credential.
That makes the gateway the thing worth attacking, and it makes credential leakage the failure that
matters most.

Two trust boundaries:

1. **Browser or MCP client to gateway.** Untrusted. Everything here is authenticated and audited.
2. **Gateway to upstream.** The gateway holds the credential and adds it to the outbound request.
   Nothing on the other side of boundary 1 ever sees it.

## 1. Credential handling

**What we protect.** Upstream credentials (the WooCommerce consumer key and secret, a GitHub PAT),
the model API key, the database password, and user API keys.

**How.**

- Upstream credentials are encrypted at rest with Fernet, using a key from a Kubernetes Secret.
  They are decrypted only to build the outbound header, in `upstreams.auth_headers`, which is kept
  small and pure so it can be tested without a network.
- No secret is in source, in a committed values file, or in an image layer. Charts take the *name*
  of a Secret that already exists (D-019).
- API keys are stored as SHA-256 only and shown once at creation (D-013). Passwords are argon2id
  (D-012). The two are deliberately opposite: a 256-bit random key has no dictionary to attack and
  a slow hash would cost on every tool call, while a human password is the reverse case.
- Upstream errors report the exception **type** and never its text, because a transport error can
  quote the request including its headers. That is where a credential would otherwise surface.

**Evidence.** SEC-7 greps a canary credential across six dashboard endpoints plus the gateway and
Postgres logs: 0 hits, with the canary proven to decrypt back so the grep had something real to
find. SEC-8 greps five secrets across four pod logs: 0 hits in all 20 combinations, with a control
grep proving the machinery worked.

**Known weakness.** The Fernet key sits in a Secret in the same cluster, so cluster admin equals
credential access. Kubernetes Secrets are base64, not encrypted, unless encryption at rest is
configured on etcd. It is not configured here. For a demo that is accepted. In production this
wants a KMS-backed provider or an external secret store.

## 2. Authentication, authorisation and multi-user isolation

**Authentication.** Two paths. MCP clients present `Authorization: Bearer gw_<prefix>_<secret>`,
checked in ASGI middleware that runs **before** the MCP app, so a rejected call never reaches an
upstream. Dashboard users get a server-side session: the cookie carries an opaque id and nothing
else, so a tampered cookie cannot assert a user or a role.

**Authorisation.** Two roles, admin and member. Every state-changing route checks the role
server-side, not by hiding a button.

**Isolation.** A member sees only their own API keys and can revoke only their own. Ownership is
checked against the stored owner, never against anything the client sent.

**Evidence.** SEC-4: member B is refused invite, list users and disable upstream, all 403, while
admin A gets 200 and no session at all gets 401. SEC-5: A and B each see exactly one key, their
own, and B revoking A's key is 403.

**A bug this section nearly shipped with.** Audit rows were attributed to the API key's *name*, and
every key created in the dashboard is named "default" unless renamed, so two different users'
calls were indistinguishable in the log. Found while building the chat agent. Attribution is only
as good as the field you attribute to.

**Known weakness.** There is no rate limit on login. An attacker can grind passwords at whatever
rate the network allows. Failed logins are audited, so the attempt is visible after the fact, but
nothing stops it at the time.

## 3. Network exposure and blast radius

- The gateway is the only component with an Ingress. woo-mcp and fx-mcp have none.
- A NetworkPolicy on each in-cluster MCP server allows ingress **only** from pods labelled
  `app.kubernetes.io/name=gateway`. A pod without that label is refused at the network layer, not
  by application logic.
- Postgres and MariaDB are ClusterIP with no Ingress.
- On the VPS, only 80 and 443 are open to the internet. The Kubernetes API on 6443 is never
  exposed; kubectl reaches it through an IAP tunnel, and SSH is IAP-only.
- Every container runs as non-root with a read-only root filesystem, no privilege escalation and
  all capabilities dropped.

**Evidence.** WM-6 tried to reach woo-mcp from an unlabelled pod and the connection was refused.
The prediction had been "timeout"; k3s sends a TCP reset instead. That was recorded as a wrong
prediction rather than quietly rewritten.

**Known weakness.** The NetworkPolicy keys on a label, and any pod that can set its own labels in
that namespace can wear it. Namespace-level separation would be stronger.

## 4. Transport security

TLS terminates at Traefik, with certificates from Let's Encrypt over HTTP-01, issued by
cert-manager (D-022). Both public hosts redirect plain HTTP to HTTPS with a 308.

The session cookie is `HttpOnly`, `SameSite=lax`, and `Secure` **when the request is HTTPS**. That
conditional was deliberate and was asserted rather than claimed for a long time: local runs on
plain HTTP, where an unconditional assertion would be either a false failure or a lie. It is now
discharged on the VPS, where the real `Set-Cookie` reads:

```
gw_session=...; HttpOnly; Max-Age=43200; Path=/; SameSite=lax; Secure
```

Getting there needed `FORWARDED_ALLOW_IPS`. TLS ends at the proxy, so the pod is reached over plain
HTTP and `request.url.scheme` is `http`; uvicorn parses `X-Forwarded-Proto` only for clients listed
in that setting, and the default is 127.0.0.1. Without it the flag could never have turned on,
however correct the conditional was.

**On the local cluster there is no TLS, so `Secure` is absent there and the session cookie travels
in clear.** That is accepted for a laptop and would not be accepted anywhere else.

**Known weakness.** HSTS is not set. A first visit over plain HTTP is still strippable even though
it redirects.

## 5. CSRF

Every state-changing dashboard route checks `Origin` against the request's own host. A browser
attaches `Origin` to exactly the cross-site requests that matter. A missing `Origin` is allowed on
purpose, because curl and MCP clients send none; the cookie is `SameSite=lax`, which is what stops
the cross-site form post that a missing-Origin check would otherwise let through.

**Evidence.** SEC-3: a valid admin cookie with `Origin: http://evil.example` is 403, the same
request with the correct Origin is 200. Eight cases are unit-tested including a suffix attack
(`gateway.localhost.evil.example`) and a port mismatch.

## 6. The chat agent

The agent runs server side. The browser sends a sentence and gets back an answer plus the list of
tools that were called. It never sees the model API key, never sees an upstream URL, and never
calls a tool itself.

The agent reaches its tools through the gateway's **own** public `/mcp`, with a short-lived key
minted for the signed-in user and deleted when the turn ends. So it is just another MCP client: no
second privileged path exists that could behave differently from the one the demo shows, and the
audit row says the user because that is who actually made the call.

**Prompt injection is the open risk and is not solved here.** Tool output goes back into the
model's context. A product description or an order note containing instructions can try to steer
the next tool call. What limits the damage:

- The agent can only call tools the gateway exposes, as that user, with that user's permissions.
- A hard cap of six tool steps per turn.
- Every call is audited, so an injected call is visible afterwards.

What is **not** there: no filtering of tool output, and no confirmation step before a write tool
such as `create_product` or `update_order_status`. A successful injection could create or modify a
product within the signed-in user's rights. For a production system the write tools would need
either a confirmation step or a read-only default.

## 7. Secrets in transcripts, and what was done about it

Several credentials were read into a session transcript during development: two dashboard
passwords, the WordPress admin password, and the local gateway bootstrap key. None of them protect
anything public, but they are treated as compromised.

`docs/requirements-trace.md` row S-11 tracks replacing all three before the demo recording, each
with its own mechanism: dashboard users through the invite flow so only Kapardhi types a password,
`scripts/rotate-admin.sh` for WordPress, and `scripts/rotate-gateway-key.sh` for the bootstrap key.

The VPS bootstrap key was generated fresh and never printed, and was rotated anyway before anything
was publicly reachable. That rotation is also how a bug in the rotation script was found: it
selected the Deployment by a label the chart only sets on the pod template, so it could never have
matched on any cluster. It failed closed and changed nothing.

## What a determined attacker gets

- **Steals a user's API key.** They act as that user until an admin revokes it. They cannot read
  any upstream credential, and every call they make is audited under that user.
- **Steals the session cookie on the local cluster.** There is no TLS there, so this is realistic
  on a shared network. They get that user's dashboard session for up to 12 hours.
- **Gets cluster admin.** Everything. The Fernet key, every Secret, every credential. There is no
  defence inside this design for that case, and the honest answer is that there is not meant to be.
