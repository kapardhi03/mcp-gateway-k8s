#!/usr/bin/env bash
# rotate-admin.sh
# Rotates the WordPress admin password and the Kubernetes Secret that holds it.
# See D-019.
#
# Why this exists: deleting and recreating the Secret does NOT change the
# WordPress user. The password lives in two places, the wp_users table and the
# Secret, and both have to move together.
#
# The new value is never printed, never passed on a command line, and never
# written to a file. It goes to the pod on stdin and to kubectl on stdin.
#
# Safe to re-run. Each run generates a fresh password and sets both sides, so a
# run that fails halfway is fixed by running it again.
#
# Usage: scripts/rotate-admin.sh [namespace]
#   Targets whatever cluster KUBECONFIG / the current context points at.
#   The target node is printed so you can see which cluster you hit.

set -euo pipefail

NAMESPACE="${1:-store}"
ADMIN_SECRET="store-admin"
WP_USER="admin"

node="$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [ -z "$node" ]; then
  echo "FAIL  cannot reach a cluster. Check KUBECONFIG." >&2
  exit 1
fi
echo "cluster node : $node"
echo "namespace    : $NAMESPACE"

pod="$(kubectl -n "$NAMESPACE" get pods -o name 2>/dev/null | grep -- '-wp-' | head -1 | cut -d/ -f2 || true)"
if [ -z "$pod" ]; then
  echo "FAIL  no WordPress pod found in namespace $NAMESPACE" >&2
  exit 1
fi
echo "wordpress pod: $pod"

if ! kubectl -n "$NAMESPACE" get secret "$ADMIN_SECRET" >/dev/null 2>&1; then
  echo "FAIL  secret/$ADMIN_SECRET does not exist in $NAMESPACE" >&2
  exit 1
fi

# 32 chars, alphanumeric only, same alphabet as dev-secrets.sh so the bootstrap
# Job's shell never has to quote anything surprising.
# `tr ... | head -c 32` dies with SIGPIPE under `set -o pipefail`: head exits at
# 32 bytes and tr is killed writing to the closed pipe. Read a bounded block and
# use cut, which consumes the whole stream, so no stage ever sees a closed pipe.
new_pw="$(head -c 4096 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c1-32)"

# ---- 1. WordPress first. It is the authoritative side. ----
# The password goes in on stdin, so it never appears in the pod's process list.
set +e
wp_out="$(printf '%s' "$new_pw" | kubectl -n "$NAMESPACE" exec -i "$pod" -- php -r '
require_once "/var/www/html/wp-load.php";
$pw = stream_get_contents(STDIN);
$u  = get_user_by("login", "admin");
if ( ! $u ) { fwrite(STDERR, "no such user\n"); exit(1); }
wp_set_password($pw, $u->ID);
$check = wp_authenticate("admin", $pw);
if ( is_wp_error($check) ) { fwrite(STDERR, "reauth failed\n"); exit(1); }
echo "wordpress-updated\n";
' 2>&1)"
wp_rc=$?
set -e

if [ "$wp_rc" -ne 0 ] || ! printf '%s' "$wp_out" | grep -q 'wordpress-updated'; then
  echo "FAIL  WordPress password not changed. Secret left untouched, nothing rotated." >&2
  printf '%s\n' "$wp_out" | sed 's/^/        /' >&2
  exit 1
fi
echo "OK    WordPress user '$WP_USER' password changed and re-authenticated"

# ---- 2. Then the Secret. ----
# --dry-run=client | apply keeps this a single atomic update and avoids
# delete-then-create, which would leave a window with no Secret at all.
existing_email="$(kubectl -n "$NAMESPACE" get secret "$ADMIN_SECRET" \
  -o jsonpath='{.data.email}' | base64 -d)"

if kubectl -n "$NAMESPACE" create secret generic "$ADMIN_SECRET" \
     --from-literal=password="$new_pw" \
     --from-literal=email="$existing_email" \
     --dry-run=client -o yaml | kubectl -n "$NAMESPACE" apply -f - >/dev/null; then
  echo "OK    secret/$ADMIN_SECRET updated"
else
  echo "FAIL  WordPress was rotated but the Secret was NOT updated." >&2
  echo "      They are out of sync. Re-run this script to set both again." >&2
  exit 1
fi

unset new_pw

echo
echo "Rotated. The new value was not printed. To read it back:"
echo "  kubectl -n $NAMESPACE get secret $ADMIN_SECRET -o jsonpath='{.data.password}' | base64 -d"
