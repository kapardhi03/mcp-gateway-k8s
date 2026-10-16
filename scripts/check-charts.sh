#!/usr/bin/env bash
# check-charts.sh
# Two guards on the Helm charts. See D-002 and the chart rules in CLAUDE.md.
#
#   1. Portability. Templates must not hardcode k3s-only parts. Those come from
#      values, so the charts still install on a reviewer's kind or EKS cluster.
#   2. Prod leakage. Rendering a chart with values-prod.yaml must not emit
#      local-only values such as localhost, a .local host, or pullPolicy: Never.
#
# Prints PASS or FAIL per check. Exits non-zero if any check fails.
# Prints SKIP and exits 0 while charts/ does not exist.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d charts ]; then
  echo "SKIP  charts/ does not exist yet"
  exit 0
fi

PORTABILITY_RE='traefik|local-path|ingressClassName: *[a-z]|storageClassName: *[a-z]'
LEAKAGE_RE='localhost|\.local$|\.local[^a-zA-Z0-9]|pullPolicy: *Never'

fail=0

# ---------- check 1: portability ----------
hits="$(grep -rniE "$PORTABILITY_RE" charts/*/templates/ 2>/dev/null || true)"
if [ -z "$hits" ]; then
  echo "PASS  portability: no hardcoded k3s parts under charts/*/templates/"
else
  echo "FAIL  portability: hardcoded k3s parts under charts/*/templates/"
  printf '%s\n' "$hits" | sed 's/^/        /'
  fail=1
fi

# ---------- check 2: prod leakage ----------
leak_fail=0
chart_count=0

for chart in charts/*/; do
  [ -d "$chart" ] || continue
  chart="${chart%/}"
  chart_count=$((chart_count + 1))

  vals="$chart/values-prod.yaml"
  if [ ! -f "$vals" ]; then
    echo "FAIL  prod leakage: $chart has no values-prod.yaml"
    leak_fail=1
    continue
  fi

  if ! rendered="$(helm template "$chart" -f "$vals" 2>&1)"; then
    echo "FAIL  prod leakage: helm template failed for $chart"
    printf '%s\n' "$rendered" | sed 's/^/        /'
    leak_fail=1
    continue
  fi

  hits="$(printf '%s\n' "$rendered" | grep -niE "$LEAKAGE_RE" || true)"
  if [ -n "$hits" ]; then
    echo "FAIL  prod leakage: $chart renders local-only values"
    printf '%s\n' "$hits" | sed 's/^/        /'
    leak_fail=1
  fi
done

if [ "$chart_count" -eq 0 ]; then
  echo "SKIP  prod leakage: charts/ holds no charts yet"
elif [ "$leak_fail" -eq 0 ]; then
  echo "PASS  prod leakage: no local-only values in any values-prod.yaml render"
else
  fail=1
fi

exit "$fail"
