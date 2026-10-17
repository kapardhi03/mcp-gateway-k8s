# CLAUDE.md

Rules for Claude Code in this repo. Read `docs/decision-log.md` before changing design.

## Who decides

- Kapardhi makes every design decision. You propose, build, and verify.
- If a task needs a choice that is not in `docs/decision-log.md`, stop and propose it as a new decision entry. Ask Kapardhi for his choice and his reason. Do not pick silently.
- If you see code that makes an unlogged choice, flag it.

## Git

- Stage files explicitly. Never `git add -A` or `git add .`.
- Show the diff and wait for Kapardhi to read it before committing.
- One logical change per commit. Reference the D-number or requirement ID in the message when one applies.

## Verification

- A task is done only when there is evidence: test output, `kubectl` output, `helm` output, or a recorded demo step.
- Before running a Definition-of-Done check, write the expected result in `docs/requirements-trace.md`. Then record the actual result.
- When source code and a chat summary disagree, the source code wins. Say so.
- Look up current versions and deprecations. Do not state them from memory.

## Hard constraints from the requirements

- The WooCommerce MCP server is written in this repo. Do not install an existing Woo MCP server or plugin.
- Helm only. No Kustomize. Local vs prod differences only in `values-local.yaml` and `values-prod.yaml`.
- No secret in source, in values files committed to git, or in image layers. Use Kubernetes Secrets.
- Upstream credentials never go to the browser or to an MCP client. Check every API response and log line for leaks.
- The Woo MCP server has no Ingress and is blocked from outside the cluster.
- Every workload has readiness and liveness probes and resource requests and limits.
- API keys are stored hashed. Never log a raw key.
- Every tool call writes an audit row: user, server, tool, timestamp, duration, outcome.

## Chart rules

- Never hardcode `ingressClassName`, `storageClassName`, `traefik` or `local-path` in `templates/`. They come from values only. This keeps the charts portable to a reviewer's kind or EKS cluster. See D-002.
- Run `scripts/check-charts.sh` before calling any chart done.
- A Job is done only when `status.failed == 0`. `Complete` is not enough: a Job with a `backoffLimit` reports `Complete` as soon as one pod succeeds, however many died first, so a Job that only passed on retry looks identical to one that worked. Run `scripts/check-cluster.sh` against the cluster, and record `failed == 0` in every Job row in `docs/requirements-trace.md`, not just `Complete`.

## Cloud cost

- Never upgrade billing, never click or call anything that activates a paid account.
- Never create a billable resource without showing Kapardhi the cost and getting his OK.

## Scope

- Core Definition of Done first. No stretch goals until `docs/requirements-trace.md` shows the core passing end to end.
- If a change does not move a requirements-trace row, say so before doing it.

## Logs

- At the end of a session, draft an entry in `docs/build-log.md`: what was proposed, by whom, what was decided, what was verified, any AI errors found.

## Writing

- Docs and README: short sentences, no em dashes, no filler. Explain why, and link the D-number.
