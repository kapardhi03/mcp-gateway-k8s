#!/usr/bin/env bash
# rotate-gateway-key.sh
# Rotates the gateway's bootstrap API key. See D-011, D-013.
#
# Why this exists: the bootstrap key was printed into a chat transcript while
# being retrieved for the GW-2 and GW-3 client checks. That is harmless while
# the gateway answers only on gateway.localhost, and not harmless the moment
# it gets a public Ingress on the VPS.
#
# Two places have to move together:
#   1. Secret gateway-secrets, key bootstrap-api-key
#   2. the api_keys row in Postgres, which stores only the SHA-256
# The gateway re-seeds the hash from the Secret on every start, so restarting
# it after the Secret changes is what makes step 2 happen. The old key stops
# working at that moment, not before.
#
# The new value is never printed. Read it back from the Secret afterwards.
#
# Safe to re-run: each run makes a fresh key and sets both sides.
#
# Usage: scripts/rotate-gateway-key.sh [namespace]

set -euo pipefail

NAMESPACE="${1:-store}"
GW_SECRET="gateway-secrets"
DEPLOY_LABEL="app.kubernetes.io/component=gateway"

node="$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [ -z "$node" ]; then
  echo "FAIL  cannot reach a cluster. Check KUBECONFIG." >&2
  exit 1
fi
echo "cluster  : $node"
echo "namespace: $NAMESPACE"

if ! kubectl -n "$NAMESPACE" get secret "$GW_SECRET" >/dev/null 2>&1; then
  echo "FAIL  secret/$GW_SECRET does not exist in $NAMESPACE" >&2
  exit 1
fi

deploy="$(kubectl -n "$NAMESPACE" get deploy -l "$DEPLOY_LABEL" -o name 2>/dev/null | head -1)"
if [ -z "$deploy" ]; then
  echo "FAIL  no gateway deployment found in $NAMESPACE" >&2
  exit 1
fi
echo "deploy   : $deploy"

# D-013 option A: gw_<8 hex>_<secret>. Only the SHA-256 is ever stored.
new_key="gw_$(openssl rand -hex 4)_$(openssl rand -hex 24)"

# The encryption key must survive untouched: it decrypts every stored upstream
# credential. Losing it would make them unrecoverable.
enc="$(kubectl -n "$NAMESPACE" get secret "$GW_SECRET" \
  -o jsonpath='{.data.encryption-key}' | base64 -d)"
if [ -z "$enc" ]; then
  echo "FAIL  encryption-key missing from $GW_SECRET, refusing to rewrite the Secret" >&2
  exit 1
fi

if kubectl -n "$NAMESPACE" create secret generic "$GW_SECRET" \
     --from-literal=encryption-key="$enc" \
     --from-literal=bootstrap-api-key="$new_key" \
     --dry-run=client -o yaml | kubectl -n "$NAMESPACE" apply -f - >/dev/null; then
  echo "OK    secret/$GW_SECRET updated (encryption-key preserved)"
else
  echo "FAIL  could not update the Secret. Nothing rotated." >&2
  exit 1
fi
unset new_key enc

# Restart so the gateway re-reads the Secret and re-seeds the stored hash.
# Until this completes the OLD key still works, because the hash in Postgres
# has not changed yet.
kubectl -n "$NAMESPACE" rollout restart "$deploy" >/dev/null
echo "OK    $deploy restarting"
if kubectl -n "$NAMESPACE" rollout status "$deploy" --timeout=180s >/dev/null 2>&1; then
  echo "OK    rollout complete, new key is live"
else
  echo "FAIL  rollout did not complete. The Secret holds the NEW key but the" >&2
  echo "      running pod may still accept the OLD one. Check the pod." >&2
  exit 1
fi

echo
echo "Rotated. The new value was not printed. To read it back:"
echo "  kubectl -n $NAMESPACE get secret $GW_SECRET -o jsonpath='{.data.bootstrap-api-key}' | base64 -d"
echo
echo "Every MCP client configured with the old key must be updated."
