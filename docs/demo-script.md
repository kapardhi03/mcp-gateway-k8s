# Demo script

Notes for the recorded walkthrough (S-09). Six sections are required. This file holds the
things that are easy to get wrong on camera, not a word-for-word script.

## Showing an upstream failure: use `scale`, not `delete pod`

Scale the Deployment to zero:

```bash
kubectl -n store scale deploy/woo-woo-mcp --replicas=0
```

Then show the Servers tab, ask the chat agent a question each upstream would answer, and bring
it back:

```bash
kubectl -n store scale deploy/woo-woo-mcp --replicas=1
```

**Do not use `kubectl delete pod` for this.** It was the pre-registered method for DOD-10 and it
produced no evidence at all: the replacement pod was `Running` in **under 4 seconds**, which is
faster than the 30 second health loop and faster than the registry's own refresh window, so the
gateway never observed a degraded state and the dashboard never changed. On camera that looks
like nothing happening.

Worth saying out loud while demonstrating, because it is a point in the system's favour rather
than an excuse: a pod delete self-heals in about four seconds, and that self-healing is the
Kubernetes half of the story. Scaling to zero is how you hold the failure open long enough to
show the *gateway's* half, which is the part being demonstrated: one upstream down, the others
unaffected.

## What to show during the outage

Both halves, in this order:

1. **The Servers tab** shows `woo` as `Unreachable` with `ConnectError`, `fx` still `Connected`.
   This updates on the first page load after the failure, not after a delay.
2. **An external client's `tools/list`** returns exactly the two `fx__*` tools. The five
   `woo__*` tools are gone, without the client being reconfigured.
3. **The chat agent answers an fx question normally**, for example "What is 100 US dollars in
   Japanese yen?".
4. **The chat agent refuses a woo question honestly.** Asked "How many products are in the
   store?" during the outage it answered: *"My tools only cover currency exchange rates and
   conversions, and I don't have access to the store's product catalog."* It called no tool and
   invented no number. This is the single best moment in the failure demo, so ask this question
   rather than only the one that works.

Then scale back to 1 and show everything returning with no restart and no other action.

## The timezone question needs the right order

"What orders came in today?" only demonstrates the store timezone if the order it returns was
placed between **00:00 and 05:30 IST**, and the question is asked **after 05:30 IST** on the
same IST day. Outside that, a UTC implementation gives the identical answer and the
demonstration proves nothing. See the correction section in `requirements-trace.md`.

## Accounts

Use the accounts created for the recording, not the ones from development: see S-11. The
development A and B passwords appear in a session transcript.
