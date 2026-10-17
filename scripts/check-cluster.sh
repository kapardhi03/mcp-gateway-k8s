#!/usr/bin/env bash
# check-cluster.sh
# Cluster-side guards that a chart render cannot catch. Run against a live
# cluster. See CLAUDE.md chart rules.
#
# Guard 1: no Job may have status.failed > 0.
#
#   Why this exists. A Kubernetes Job with backoffLimit > 0 reports
#   `Complete` as soon as ONE pod succeeds, no matter how many died first.
#   The store bootstrap Job did exactly that on 2026-10-17: the first attempt
#   died on `wp option update gmt_offset`, the retry took a SKIP branch and
#   succeeded, and `kubectl get jobs` showed `Complete 1/1`. The failure was
#   invisible unless you listed the pods. "Complete" is therefore not evidence
#   that a Job works; `failed == 0` is.
#
# Usage: scripts/check-cluster.sh [namespace ...]
#   With no arguments, checks every namespace.
#   Respects KUBECONFIG / the current context. Prints the target first.

set -uo pipefail

node="$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [ -z "$node" ]; then
  echo "FAIL  cannot reach a cluster. Check KUBECONFIG." >&2
  exit 1
fi
echo "cluster: $node"

if [ "$#" -gt 0 ]; then
  scope=""
  for ns in "$@"; do scope="$scope -n $ns"; done
  echo "scope  : namespaces $*"
else
  scope="--all-namespaces"
  echo "scope  : all namespaces"
fi
echo

fail=0
count=0

# One line per Job: namespace, name, succeeded, failed.
# `// 0` covers the field being absent, which is how Kubernetes represents 0.
while IFS=$'\t' read -r ns name succeeded failed; do
  [ -n "${name:-}" ] || continue
  count=$((count + 1))
  if [ "${failed:-0}" -gt 0 ]; then
    echo "FAIL  job $ns/$name: succeeded=$succeeded failed=$failed"
    echo "        A Job that only passed on retry is a failure. Inspect with:"
    echo "        kubectl -n $ns get pods --selector=job-name=$name"
    fail=1
  else
    echo "PASS  job $ns/$name: succeeded=$succeeded failed=0"
  fi
done < <(
  # shellcheck disable=SC2086
  kubectl get jobs $scope -o go-template='{{range .items}}{{.metadata.namespace}}{{"\t"}}{{.metadata.name}}{{"\t"}}{{if .status.succeeded}}{{.status.succeeded}}{{else}}0{{end}}{{"\t"}}{{if .status.failed}}{{.status.failed}}{{else}}0{{end}}{{"\n"}}{{end}}' 2>/dev/null
)

echo
if [ "$count" -eq 0 ]; then
  echo "SKIP  no Jobs found"
  exit 0
fi

if [ "$fail" -eq 0 ]; then
  echo "PASS  $count Job(s), none with a failed pod"
else
  echo "FAIL  at least one Job succeeded only after a failed attempt"
fi
exit "$fail"
