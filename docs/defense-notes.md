# Defense notes

Questions the demo video and the design walkthrough will ask.
**Kapardhi writes the answers.** Claude checks the mechanism and pushes back. Claude does not write answers here.
An answer is `ready` when I can say it aloud without notes and it matches the code.

Sections follow the required demo video sections.

## 1. System design

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 1.1 | What are the components and what does each own? | | | todo |
| 1.2 | Walk the Definition-of-Done flow with two users. | | | todo |

## 2. Kubernetes

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 2.1 | What runs in which namespace, and why? | | | todo |
| 2.2 | Which Secrets exist, who reads each, how do they get into the pod? | | | todo |
| 2.3 | Which volumes exist and what happens to data on pod restart? | | | todo |
| 2.4 | How did you choose requests and limits? | | | todo |
| 2.5 | What do the readiness and liveness probes check, and why those checks? | | | todo |
| 2.6 | What is public, what is internal-only, and what enforces it? | | | todo |

## 3. MCP internals

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 3.1 | How does the gateway connect to upstreams? | | | todo |
| 3.2 | Trace one tool call from client to store and back. | | | todo |
| 3.3 | How do you handle name collisions? | | | todo |
| 3.4 | What happens on a timeout? On a dead upstream? | | | todo |
| 3.5 | Which MCP spec version, and why? | | | todo |
| 3.6 | Why does woo-mcp need two store URLs? | | | todo |
| 3.7 | What happens if an upstream changes a tool's schema but keeps the name? | | | todo |

## 4. Security posture

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 4.1 | How are API keys stored and checked? | | | todo |
| 4.2 | How are upstream credentials stored and used? | | | todo |
| 4.3 | What can a member do and not do? | | | todo |
| 4.4 | What if an admin adds a malicious or compromised MCP server? | | | todo |
| 4.5 | Why are client tokens not passed through to upstreams? | | | todo |
| 4.6 | What can a member do with a shared upstream credential they never see? | | | todo |
| 4.7 | Tool descriptions written to manipulate the model: what is the risk and the mitigation? | | | todo |
| 4.8 | What can one team member do to another? | | | todo |

## 5. Chat agent

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 5.1 | Explain the tool loop. | | | todo |
| 5.2 | How does the agent act as the logged-in user? | | | todo |

## 6. Local to VPS

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 6.1 | What changes between local and VPS in values files? | | | todo |
| 6.2 | Ingress, domains, storage and secrets strategy on the VPS. | | | todo |
| 6.3 | How do you upgrade and roll back with Helm? | | | todo |
