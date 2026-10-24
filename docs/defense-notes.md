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
| 4.9 | Why argon2 for passwords but SHA-256 for API keys? | | | todo |
| 4.10 | How do you stop two people accepting the same invite at once? | | | todo |
| 4.11 | How is the first admin created, and why not a default password? | | | todo |
| 4.12 | What does SameSite=lax plus an Origin check protect against, and what doesn't it? | | | todo |

## 5. Chat agent

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 5.1 | Explain the tool loop. | | | todo |
| 5.2 | How does the agent act as the logged-in user? | | | todo |
| 5.3 | The agent runs inside the gateway, yet it talks to the gateway's own `/mcp` over HTTP. Why not just call the tools in-process? | | | todo |
| 5.4 | Why is the per-turn key deleted rather than revoked, when every other key is revoked? | | | todo |
| 5.5 | Your audit log recorded two different users as "default". How did that happen, and what does it tell you about trusting the rest of the attribution? | | | todo |
| 5.6 | Why is the daily chat cap global rather than per user? What does that let one user do to the others? | | | todo |
| 5.7 | D-011 names Gemini as the fallback. Why is there no Gemini adapter? | | | todo |
| 5.8 | Six tool steps and 1024 max_tokens. What happens when a question genuinely needs more, and is failing the right answer? | | | todo |
| 5.9 | The agent told you it had assumed the store currency. What would have happened if it had not mentioned it? | | | todo |

## 6. Local to VPS

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 6.1 | What changes between local and VPS in values files? | | | todo |
| 6.2 | Ingress, domains, storage and secrets strategy on the VPS. | | | todo |
| 6.3 | How do you upgrade and roll back with Helm? | | | todo |
| 6.4 | Why is a DuckDNS hostname a safer base for Let's Encrypt than sslip.io, and how did you establish that? | | | todo |
| 6.5 | Without TLS, which security property do you lose, and where is that written down? | | | todo |
| 6.6 | Your rotation script had never been run until the night you needed it. What else in this repo is in that category? | | | todo |
| 6.7 | Helm said the Traefik upgrade was deployed and nothing changed. How would you catch that class of failure in future? | | | todo |
| 6.8 | woo-mcp signs `http://` against a site whose home URL is `https://`. Explain why that is correct and not a bug. | | | todo |
| 6.9 | Why is the ACME email not in the repo, and how is it supplied instead? | | | todo |

## 7. Testing and evidence

| # | Question | My answer | Checked against code | Status |
|---|---|---|---|---|
| 7.1 | Your store-timezone test passed for four days while the code resolved "today" in UTC. How is that possible, and how would you catch the next one? | | | todo |
| 7.2 | You have twice shipped a bug that a green check could not distinguish from correct behaviour. What do those two have in common? | | | todo |
| 7.3 | What does "proved by mutation" mean here, and which tests have been proved that way? | | | todo |
| 7.4 | Which of your passing rows are evidence of the thing they claim, and which are only evidence that nothing crashed? | | | todo |
| 7.5 | DOD-01 passed while the shop page showed "launching soon" to every visitor who was not an admin. How did a green row and a broken storefront coexist, and what does that say about checks run while signed in? | | | todo |
| 7.6 | VDOD-7 was predicted before it was run and the prediction held. What would you have done if only one of the three variants had failed instead of two? | | | todo |
