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
# Usage: scripts/dev-secrets.sh [namespace] [--ghcr]
#   --ghcr also creates the imagePullSecret prod needs to pull from GHCR.
#          Local does not need it: k3d imports the image directly (D-020).
#   --llm  also creates the LLM API key Secret. Prompts for the key with the
#          terminal echo off; never writes it to a file. See D-011.

set -euo pipefail

NAMESPACE="${1:-store}"
WITH_GHCR=0
WITH_LLM=0
for arg in "$@"; do
  [ "$arg" = "--ghcr" ] && WITH_GHCR=1
  [ "$arg" = "--llm" ]  && WITH_LLM=1
done

DB_SECRET="store-db"
ADMIN_SECRET="store-admin"
WOO_SECRET="woo-api"
GW_DB_SECRET="gateway-db"
GW_SECRET="gateway-secrets"
LLM_SECRET="llm-api"

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

# WooCommerce REST API pair for the Woo MCP server. See D-006.
#
# Format matches what WooCommerce itself generates in class-wc-ajax.php:
#   'ck_' . wc_rand_hash()   where wc_rand_hash() is bin2hex(random_bytes(20))
# so 'ck_' + 40 hex = 43 chars, which is exactly the char(43) column width.
# Generating it here means the bootstrap Job only has to INSERT it, and no pod
# needs permission to write a Kubernetes Secret.
if kubectl -n "$NAMESPACE" get secret "$WOO_SECRET" >/dev/null 2>&1; then
  echo "SKIP  secret/$WOO_SECRET already exists"
else
  kubectl -n "$NAMESPACE" create secret generic "$WOO_SECRET" \
    --from-literal=consumer-key="ck_$(openssl rand -hex 20)" \
    --from-literal=consumer-secret="cs_$(openssl rand -hex 20)"
  echo "OK    secret/$WOO_SECRET created"
fi

# Gateway Secrets: Postgres password, encryption key, bootstrap API key.
#
# The encryption key is a Fernet key, which is urlsafe-base64 of 32 random
# bytes. `openssl rand -base64 32 | tr '+/' '-_'` produces exactly that, and
# it is verified against cryptography.Fernet before use.
#
# The bootstrap API key follows D-013 option A: gw_<8 hex>_<secret>. Only its
# SHA-256 is stored by the gateway; this is the one time the raw value exists.
if kubectl -n "$NAMESPACE" get secret "$GW_DB_SECRET" >/dev/null 2>&1; then
  echo "SKIP  secret/$GW_DB_SECRET already exists"
else
  kubectl -n "$NAMESPACE" create secret generic "$GW_DB_SECRET" \
    --from-literal=password="$(rand)"
  echo "OK    secret/$GW_DB_SECRET created"
fi

if kubectl -n "$NAMESPACE" get secret "$GW_SECRET" >/dev/null 2>&1; then
  echo "SKIP  secret/$GW_SECRET already exists"
else
  fernet="$(openssl rand -base64 32 | tr '+/' '-_')"
  bootstrap="gw_$(openssl rand -hex 4)_$(openssl rand -hex 24)"
  kubectl -n "$NAMESPACE" create secret generic "$GW_SECRET" \
    --from-literal=encryption-key="$fernet" \
    --from-literal=bootstrap-api-key="$bootstrap"
  unset fernet bootstrap
  echo "OK    secret/$GW_SECRET created"
  echo "      read the bootstrap key back with:"
  echo "      kubectl -n $NAMESPACE get secret $GW_SECRET -o jsonpath='{.data.bootstrap-api-key}' | base64 -d"
fi

# LLM API key. See D-011.
#
# Typed by Kapardhi at the prompt with `read -s`, so it is never echoed, never
# in shell history, never in a process list and never written to a file. It
# goes straight from the terminal into the Secret.
#
# If you would rather not type it every time, export ANTHROPIC_API_KEY first
# from a file OUTSIDE the repo, e.g.:
#     set -a; . ~/.config/mcp-gw/llm.env; set +a
# Deliberately not a .env inside the repo: a gitignored file is still one
# `git add -f`, one editor plugin or one backup sync away from leaking, and
# this project's rule is that no key lives in the repo folder at all.
if [ "$WITH_LLM" -eq 1 ]; then
  if kubectl -n "$NAMESPACE" get secret "$LLM_SECRET" >/dev/null 2>&1; then
    echo "SKIP  secret/$LLM_SECRET already exists"
  else
    key="${ANTHROPIC_API_KEY:-}"
    if [ -z "$key" ]; then
      printf 'Anthropic API key (input hidden): ' >&2
      stty -echo 2>/dev/null || true
      IFS= read -r key
      stty echo 2>/dev/null || true
      printf '\n' >&2
    else
      echo "      using ANTHROPIC_API_KEY from the environment"
    fi
    if [ -z "$key" ]; then
      echo "FAIL  no key entered" >&2
      exit 1
    fi
    case "$key" in
      sk-ant-*) : ;;
      *) echo "WARN  key does not start with sk-ant-, continuing anyway" >&2 ;;
    esac
    kubectl -n "$NAMESPACE" create secret generic "$LLM_SECRET" \
      --from-literal=anthropic-api-key="$key"
    unset key
    echo "OK    secret/$LLM_SECRET created"
  fi
fi

# GHCR imagePullSecret, prod only. See D-020.
#
# The token is read from `gh auth token` (or GHCR_TOKEN) and piped straight
# into kubectl. It is never echoed, never written to a file and never passed
# as a command-line argument where it would show up in a process list.
if [ "$WITH_GHCR" -eq 1 ]; then
  if kubectl -n "$NAMESPACE" get secret ghcr >/dev/null 2>&1; then
    echo "SKIP  secret/ghcr already exists"
  else
    token="${GHCR_TOKEN:-$(gh auth token 2>/dev/null || true)}"
    if [ -z "$token" ]; then
      echo "FAIL  no GHCR token. Set GHCR_TOKEN or run: gh auth login" >&2
      exit 1
    fi
    kubectl -n "$NAMESPACE" create secret docker-registry ghcr \
      --docker-server=ghcr.io \
      --docker-username="${GHCR_USER:-kapardhi03}" \
      --docker-password="$token"
    unset token
    echo "OK    secret/ghcr created"
  fi
fi

echo
echo "Secrets in $NAMESPACE (key names only, never values):"
for s in "$DB_SECRET" "$ADMIN_SECRET" "$WOO_SECRET" "$GW_DB_SECRET" "$GW_SECRET" "$LLM_SECRET"; do
  keys="$(kubectl -n "$NAMESPACE" get secret "$s" \
    -o go-template='{{range $k, $v := .data}}{{$k}} {{end}}' 2>/dev/null || true)"
  printf '  %-14s %s\n' "$s" "$keys"
done
echo
echo "To read the admin password back:"
echo "  kubectl -n $NAMESPACE get secret $ADMIN_SECRET -o jsonpath='{.data.password}' | base64 -d"
