#!/usr/bin/env bash
# dev-secrets.sh
# Creates the Secrets the store chart expects, with random values, for local
# development only. See D-019.
#
# The chart never takes a password as a Helm value. It takes the NAME of a
# Secret. That keeps passwords out of values files, out of shell history and
# out of the Helm release manifest.
#
# Idempotent: a Secret that already exists is left alone, so re-running this
# never rotates a password out from under a running database.
#
# Usage: scripts/dev-secrets.sh [namespace]

set -euo pipefail

NAMESPACE="${1:-store}"
DB_SECRET="store-db"
ADMIN_SECRET="store-admin"

rand() {
  # 32 chars, alphanumeric only. WordPress and MariaDB both cope with these
  # without quoting surprises in the bootstrap Job's shell.
  #
  # Not `tr ... | head -c 32`: under `set -o pipefail` that dies with SIGPIPE
  # once head exits at 32 bytes and tr writes to the closed pipe. It is a race,
  # so it passed for two sessions before failing. cut consumes the whole stream.
  head -c 4096 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c1-32
}

if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  echo "creating namespace $NAMESPACE"
  kubectl create namespace "$NAMESPACE"
fi

if kubectl -n "$NAMESPACE" get secret "$DB_SECRET" >/dev/null 2>&1; then
  echo "SKIP  secret/$DB_SECRET already exists"
else
  kubectl -n "$NAMESPACE" create secret generic "$DB_SECRET" \
    --from-literal=root-password="$(rand)" \
    --from-literal=password="$(rand)"
  echo "OK    secret/$DB_SECRET created"
fi

if kubectl -n "$NAMESPACE" get secret "$ADMIN_SECRET" >/dev/null 2>&1; then
  echo "SKIP  secret/$ADMIN_SECRET already exists"
else
  kubectl -n "$NAMESPACE" create secret generic "$ADMIN_SECRET" \
    --from-literal=password="$(rand)" \
    --from-literal=email="admin@example.com"
  echo "OK    secret/$ADMIN_SECRET created"
fi

echo
echo "Secrets in $NAMESPACE (key names only, never values):"
for s in "$DB_SECRET" "$ADMIN_SECRET"; do
  keys="$(kubectl -n "$NAMESPACE" get secret "$s" \
    -o go-template='{{range $k, $v := .data}}{{$k}} {{end}}' 2>/dev/null || true)"
  printf '  %-14s %s\n' "$s" "$keys"
done
echo
echo "To read the admin password back:"
echo "  kubectl -n $NAMESPACE get secret $ADMIN_SECRET -o jsonpath='{.data.password}' | base64 -d"
