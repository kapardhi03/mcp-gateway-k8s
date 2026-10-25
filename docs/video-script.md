# Video script

Draft. Kapardhi to edit for voice. Target 12 to 15 minutes.

`docs/demo-script.md` holds the things that are easy to get wrong on camera. Read it first. The
two that will bite: use `scale --replicas=0` rather than `delete pod`, and the timezone question
only proves anything with an order placed between 00:00 and 05:30 IST.

**Before recording**

- Fresh A and B accounts with passwords chosen on the day (S-11). The development ones are in a
  session transcript.
- Two browsers, or one normal and one private window. A in one, B in the other, side by side.
- Terminal with `KUBECONFIG=~/.kube/gw-prod.yaml` already exported, font size up.
- One order already in the store from earlier that day, so "what came in today" has something to
  return without waiting for a checkout mid-recording.
- Tabs open and ready: dashboard, storefront, `docs/decision-log.md`.

**Running order and budget**

| # | Section | Target |
|---|---|---|
| 1 | System design, and the Definition of Done with two users | 4:00 |
| 2 | Kubernetes | 2:00 |
| 3 | MCP internals | 2:00 |
| 4 | Security posture | 2:30 |
| 5 | Chat agent | 1:30 |
| 6 | Local to VPS | 2:00 |
| | **Total** | **14:00** |

Section 1 is the one with real time in it. If you overrun, take it out of 2 and 6, not 4.

---

## 1. System design, and the Definition of Done with two users (4:00)

**On screen.** Start with the architecture: one diagram or the "The shape" block from
`docs/design-and-tradeoffs.md`. Then straight into the live run, both browsers visible.

Sequence, A on the left and B on the right:

1. The storefront at `https://store.kapardhi-gw.duckdns.org/shop/`. Add Demo Widget, check out
   with Cash on Delivery. Say the padlock is a real Let's Encrypt certificate.
2. A signs in. Chat tab: *"Create a product called Demo Mug priced 12.50."* Show the tool call
   underneath the answer. Open the product on the storefront.
3. A asks *"What orders came in today?"* It returns the order from step 1.
4. B, in the other window, creates their own API key, then asks the same question and gets the
   same answer.
5. B's Claude Code, configured with only the gateway URL and B's key, lists seven tools. Show the
   config on screen so it is obvious there is no upstream URL and no upstream credential in it.
6. One prompt that crosses two upstreams: *"What is today's order total in euros?"*
7. A revokes B's key. B's next call fails.
8. A disables fx. Its tools vanish from both the chat agent and B's client. Re-enable.
9. Audit tab: every call above, A's rows as A and B's as B, with token counts on the chat turns.

**Talking points.**

- One endpoint, one key. The client is never told where anything lives, and that is the whole
  design rather than a convenience.
- Two users is not a second copy of the demo. It is what shows the per-user audit, the key
  isolation and the revocation working.
- Revocation and disabling are deliberately different things. One kills a person's access, the
  other removes a server for everyone, and neither restarts a pod.

## 2. Kubernetes (2:00)

**On screen.** `kubectl -n store get all`, then the specific bits. Have
`charts/gateway/templates/deployment.yaml` open for the probes and limits.

```bash
kubectl -n store get pods,svc,ingress
kubectl -n store get secrets        # names only
kubectl -n store get pvc
kubectl -n store get deploy gw-gateway -o yaml | grep -A12 resources:
```

**Talking points.**

- **Public versus internal.** One Ingress, on the gateway. woo-mcp and fx-mcp have none and are
  unreachable from outside by construction, not by configuration you have to remember.
- **Secrets are names, not values.** Charts take the name of a Secret that already exists, so no
  password is ever in a values file or an image layer. Show the Secret list and point out you are
  showing names only, deliberately.
- **Volumes.** MariaDB and Postgres are StatefulSets with volumeClaimTemplates, so the store's
  data and the gateway's registry survive a pod restart. Two databases on purpose: a store outage
  must not take out authentication and the audit log.
- **Probes and limits.** Every workload has readiness, liveness, requests and limits. `/healthz`
  deliberately does not touch the database, because a database outage must not restart the
  process; `/readyz` reports the live tool count, so a gateway that cannot serve tools leaves the
  Service.

## 3. MCP internals (2:00)

**On screen.** Split: the dashboard Servers tab on one side, a terminal on the other.

```bash
# the path a call takes, in the log
kubectl -n store logs deploy/gw-gateway -f
```

Then, in the other pane, scale woo to zero and watch both.

```bash
kubectl -n store scale deploy/woo-woo-mcp --replicas=0
kubectl -n store scale deploy/woo-woo-mcp --replicas=1
```

**Talking points.**

- **The call path.** Client sends `woo__list_orders` to `/mcp`. Auth middleware runs first, so a
  bad key never reaches an upstream. The prefix is split off, the registry gives the upstream, the
  credential is attached on the way out, and an audit row is written whatever happens.
- **Collisions.** Two servers can both expose `list_products`. Prefixing is what makes that a
  non-event, and the prefix is also the routing key.
- **Timeouts and a dead upstream.** Each upstream gets its own timeout and the fan-out is
  concurrent, so one dead server costs eight seconds once rather than eight seconds each. Show
  the Servers tab flipping to `Unreachable` with `ConnectError` while fx stays Connected and its
  tools keep working.
- Say out loud that you are scaling to zero rather than deleting a pod, because a pod delete
  self-heals in about four seconds and shows nothing. That is Kubernetes doing its job and a
  useless demo.

## 4. Security posture (2:30)

**On screen.** The dashboard for the first two, the terminal for the rest.

```bash
# the credential is in the database, encrypted, and not in any response
kubectl -n store exec gw-gateway-db-0 -- psql -U gateway -c \
  'select slug, left(credential_enc, 24) from upstreams;'
curl -s https://gateway.kapardhi-gw.duckdns.org/admin/upstreams | python3 -m json.tool
```

**Talking points.**

- **Keys.** `gw_<prefix>_<secret>`. Only the SHA-256 of the whole key is stored, so a lost key
  cannot be recovered, only replaced. Passwords get argon2 instead, and say why the two are
  opposite: a random 256-bit key has no dictionary to attack, a human password does.
- **Upstream credentials.** Encrypted at rest, decrypted only to build the outbound header. Show
  the ciphertext in Postgres, then show `/admin/upstreams` returning `has_credential: true` and no
  value. A member uses the credential and never holds it.
- **What a member cannot do.** As B, click through to Members: "Admins only". Then paste
  `/admin/users` straight into the address bar and get `{"error":"admin role required"}`. Say that
  the refusal is server-side and the hidden button is not the control.
- **A malicious upstream.** Be honest here, it is the strongest moment in this section. Tool
  descriptions and tool output go into the model's prompt, so an upstream that writes instructions
  into a description can try to steer the agent. What limits it: admin-only server registration,
  a six-step cap, one tool per step, and every call audited. What is missing: no filtering and no
  confirmation before a write. Point at `docs/threat-model.md` section 3.

## 5. Chat agent (1:30)

**On screen.** The Chat tab, then the Audit tab immediately after.

**Talking points.**

- **The loop.** The model is given the gateway's tool list, picks a tool, the gateway runs it, the
  result goes back, and it loops until it answers or hits six steps. Show the steps rendered under
  the answer with arguments and timings.
- **It acts as you, and not by claiming to.** The agent is a normal MCP client of the gateway's
  own `/mcp`, authenticating with a short-lived key minted for the signed-in user and deleted when
  the turn ends. So the audit row says your email because you genuinely made the call. The
  alternative, calling the tools in-process, would have been simpler and would have created a
  privileged path nothing else in this demo exercises.
- **Cost.** Haiku 5.5, effort low, six steps, token caps and a daily cap, all Helm values.
  Measured at about $0.0005 a question. Show the token count on a turn.

## 6. Local to VPS (2:00)

**On screen.** `diff` the values files, then the live hosts, then a rollback.

```bash
diff charts/gateway/values-local.yaml charts/gateway/values-prod.yaml
diff charts/store/values-local.yaml   charts/store/values-prod.yaml
helm -n store history gw
```

**Talking points.**

- **Only values change.** Same charts, same templates, both clusters. `scripts/check-charts.sh`
  enforces it by failing the build if a template hardcodes an ingress class, a storage class or a
  hostname, so the charts still install on someone else's kind or EKS cluster.
- **DNS and ingress.** `*.localhost` locally, DuckDNS on the VPS with cert-manager and Let's
  Encrypt over HTTP-01. Worth thirty seconds on why DuckDNS and not sslip.io: sslip.io is not on
  the Public Suffix List, so every sslip.io name shares one global bucket of 50 certificates a
  week and could be refused mid-demo for reasons nothing to do with this project.
- **Storage and secrets.** Same `local-path` class name, very different durability. Secrets are
  generated on each cluster separately and no value is ever copied from local to prod.
- **Upgrade and rollback.** Show `helm history`, then `helm rollback`, then the service still
  answering. The store's bootstrap Job re-runs on every upgrade and every step in it is guarded,
  which is what makes that safe.

---

## Closing, 20 seconds

One line on the thing worth saying: the hard part was not making it work, it was making the checks
mean something. Three separate bugs in this project were green while being wrong, and each one
produced a permanent guard. If there is time, name one: the Job that reported `Complete` off a
retry, and `scripts/check-cluster.sh` that now fails any Job with `status.failed > 0`.
