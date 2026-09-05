#!/usr/bin/env bash
#
# Zeigt den Zustand des Clusters. Fragt den ersten Server ab, damit kein
# kubeconfig auf dem Mac noetig ist.
#
#   ./cluster-status.sh

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FIRST=$(grep -A3 "^        kube-01:" inventory/hosts.yml 2>/dev/null \
        | awk '/ansible_host/ {print $2}' || true)
VIP=$(awk '/^api_endpoint:/ {print $2}' inventory/group_vars/all/main.yml)
PORT=$(awk '/^api_port:/ {print $2}' inventory/group_vars/all/main.yml)

[[ -n "$FIRST" ]] || { echo "kube-01 nicht im Inventory gefunden." >&2; exit 1; }

hr() { printf '\033[1m--- %s ---\033[0m\n' "$1"; }

hr "API-VIP $VIP:$PORT"
if nc -z -G 3 "$VIP" "$PORT" 2>/dev/null; then
  echo "  erreichbar"
else
  echo "  ANTWORTET NICHT"
fi

hr "Nodes"
ssh -n -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 \
  "pi@${FIRST}" 'kubectl get nodes -o wide' 2>&1 || echo "  Abfrage fehlgeschlagen"

hr "Nicht laufende Pods"
ssh -n -o BatchMode=yes -o ConnectTimeout=8 "pi@${FIRST}" \
  'kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded 2>&1 | head -20' \
  2>&1 || true

hr "kube-vip"
ssh -n -o BatchMode=yes -o ConnectTimeout=8 "pi@${FIRST}" \
  'kubectl -n kube-system get ds kube-vip-ds -o wide 2>&1' 2>&1 || true

hr "etcd-Mitglieder"
ssh -n -o BatchMode=yes -o ConnectTimeout=8 "pi@${FIRST}" \
  'kubectl get nodes -l node-role.kubernetes.io/control-plane=true --no-headers 2>/dev/null | wc -l | xargs -I{} echo "  {} Control-Plane-Nodes"' 2>&1 || true
