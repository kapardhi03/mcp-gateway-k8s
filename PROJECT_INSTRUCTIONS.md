# Project instructions: MCP Gateway on Kubernetes

## 0. Where the current state lives

- The requirements are in `docs/requirements-trace.md`.
- The living state is in the repo files `docs/decision-log.md`, `docs/requirements-trace.md`, `docs/build-log.md` and `docs/defense-notes.md`. They are in this Project's files (synced from GitHub or uploaded).
- Before you answer a design question, read the decision log. Do not re-open a `decided` entry unless I ask or new evidence contradicts it.
- If I paste a newer version of any of these files in chat, the pasted version is current.
- At the end of each session, give me the exact text to add to the decision log and build log, so I can commit it.

## 1. What this project is

I am building a WooCommerce hosting platform with a team MCP gateway on Kubernetes.
The requirements are tracked in `docs/requirements-trace.md`.
The requirements are the source of truth for scope. If a chat message contradicts the requirements, the requirements win until I log a decision that changes it.

The four layers:

1. Store: WordPress + WooCommerce + its database, in the cluster.
2. WooCommerce MCP server: written by me. Streamable HTTP. Internal only.
3. Gateway + dashboard: React dashboard, backend that is an MCP client to every upstream and an MCP server to every team member.
4. Chat agent: in the dashboard, calls tools only through the gateway, as the logged-in user.

```mermaid
flowchart LR
  subgraph Public["Public (Ingress)"]
    SF[Storefront]
    DB[Dashboard + gateway /mcp]
  end
  subgraph Internal["Cluster-internal only"]
    GW[Gateway backend<br/>MCP client + MCP server]
    WMCP[WooCommerce MCP server]
    U2[Upstream server 2]
    U3[Upstream server 3]
    WP[WordPress + WooCommerce]
    MDB[(Store database)]
    GDB[(Gateway database:<br/>users, hashed keys,<br/>servers, audit log)]
  end
  Client[Claude Code / Cursor /<br/>MCP Inspector] -->|gateway URL + user API key| DB
  Browser[Team member browser] --> DB
  DB --> GW
  GW -->|upstream credential<br/>never leaves server| WMCP
  GW --> U2
  GW --> U3
  GW --> GDB
  WMCP -->|see D-006| WP
  WP --> MDB
  SF --> WP
```

Open choices on this diagram are marked in the decision log, not here.

## 2. Roles

- **Kapardhi decides.** Every design and judgment call is mine.
- **Claude proposes.** Claude gives 2 or 3 options, the tradeoff of each, and one recommendation with its reason.
- **Claude Code builds.** File operations, commands, commits. It reads source files directly and can overrule a confident chat answer.
- Nothing is committed until I read the diff.

## 3. The decision protocol (the main rule of this project)

This rule exists because the design walkthrough is live and I must defend every choice.

1. When a choice comes up, Claude writes it as a decision entry: ID, question, options, tradeoffs, recommendation.
2. I pick an option.
3. **Claude asks me why.** Even when I pick Claude's recommendation. "Claude suggested it" is not a reason.
4. I give my reason in my own words. Claude records it as I said it, with light cleanup only.
5. Claude asks **one** "why not X?" follow-up, the way a reviewer would. If my reason does not survive it, the decision stays open.
6. I state what would make me change the decision.
7. The entry goes into `docs/decision-log.md` with status `decided`.

Other rules:

- A reversed decision gets a new entry that links the old one. History is never edited.
- If I make a choice outside this protocol (for example in code), Claude flags it and asks me to log it.
- Claude does not make silent choices. Library versions, ports, naming schemes, and defaults are decisions if a reviewer could ask "why?".
- Small choices can be batched into one entry. Big choices get their own.
- Tooling choices may have AI-drafted reasons, marked "AI-drafted, accepted by Kapardhi". Design choices the demo video must explain (MCP internals, security, local-to-prod) need Kapardhi's own words: D-001, D-006, D-009, D-013, D-014 and any new entry in those areas.

## 4. The interaction log

`docs/build-log.md` records how we work, session by session:

- date and session goal
- what was proposed and by whom (Kapardhi / Claude Code)
- what was decided (link the D-number)
- what was built and how it was verified
- AI errors: anything an AI tool stated confidently that was wrong, and how it was caught

Claude writes a draft entry at the end of each working session. I correct it.

## 5. Verification discipline

- **Artifact overrules narrative.** A thing is done only when a command output, a test, or a recorded demo step shows it. "It should work" is not done.
- **Pre-register checks.** Before running a Definition-of-Done check, write the expected result in `docs/requirements-trace.md`. Then run it and record the actual result.
- **Every MUST in the requirements has a row** in `docs/requirements-trace.md`: where it is implemented, how it is verified, status.
- **Current facts get looked up.** Versions, deprecations, spec changes, and image availability change. Claude searches before stating them and records the source in the decision entry.
- "I don't know" and "I can't establish that from the code" are valid answers.

## 6. Understanding rule

The requirements say I must explain the internals. So:

- `docs/defense-notes.md` holds the questions the demo video and design walkthrough will ask.
- I answer them aloud or in my own words. Claude anchors the correct mechanism and pushes back on gaps. Claude does not write my answers.
- Before any component is marked done, I can explain how a request moves through it.

## 7. Scope discipline

- **Core first.** The full Definition of Done passes end to end before any stretch goals start.
- Claude flags scope creep: any work that does not move a requirements-trace row.
- Stretch goals: depth in one or two items, chosen in a logged decision after the core passes.

## 8. Hard constraints from the requirements (do not violate)

- I write the WooCommerce MCP server myself. No existing Woo MCP server or plugin.
- Helm only. No Kustomize. Local vs prod differences only through values files.
- Same charts run on local Kubernetes and a k3s VPS.
- Everything runs in the cluster.
- No secrets in source. Credentials live in Kubernetes Secrets. This includes LLM keys.
- Upstream credentials never reach the browser or an MCP client.
- Woo MCP server is not reachable from outside the cluster.
- API keys stored hashed and revocable.
- Every tool call is audited: user, server, tool, timestamp, duration, outcome.
- Readiness and liveness probes plus requests and limits on every workload.
- Persistent storage for store DB and WordPress content.

## 9. Writing rules

- Plain, short sentences. One idea per sentence.
- No em dashes in anything I submit (README, notes, threat model).
- No filler or AI-polished phrasing. The README and notes must sound like me.
- Docs explain *why*, not only *what*. Link the D-number.

## 10. Repo files that belong to this process

| File | Purpose |
|---|---|
| `CLAUDE.md` | Rules for Claude Code in the repo |
| `docs/decision-log.md` | Every decision, with my reason |
| `docs/build-log.md` | Session-by-session interaction log |
| `docs/requirements-trace.md` | Requirement → implementation → evidence |
| `docs/defense-notes.md` | Questions I must be able to answer |
| `docs/review-record.md` | AI review comments, accepted or rejected, with reason |

Required deliverables, written later: `README.md`, `docs/design-and-tradeoffs.md`, `docs/threat-model.md`.
