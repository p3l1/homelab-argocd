#!/usr/bin/env bash
#
# Zustand des Clusters auf einen Blick: Nodes, ArgoCD-Anwendungen, Speicher
# und die Erreichbarkeit der Dienste.
#
#   ./cluster-status.sh

set -uo pipefail

hr() { printf '\n\033[1m── %s ──\033[0m\n' "$1"; }
kubectl version --request-timeout=5s >/dev/null 2>&1 \
  || { echo "Kein Zugriff auf den Cluster." >&2; exit 1; }

hr "Nodes"
kubectl get nodes --no-headers 2>/dev/null \
  | awk '{printf "  %-9s %-7s %-22s %s\n",$1,$2,$3,$5}'

hr "ArgoCD"
tot=$(kubectl -n argocd get applications --no-headers 2>/dev/null | wc -l | tr -d ' ')
ok=$(kubectl -n argocd get applications --no-headers 2>/dev/null \
     | awk '$2=="Synced" && $3=="Healthy"' | wc -l | tr -d ' ')
printf '  %s von %s Synced/Healthy\n' "$ok" "$tot"
kubectl -n argocd get applications --no-headers 2>/dev/null \
  | awk '!($2=="Synced" && $3=="Healthy"){printf "  offen: %-20s %-11s %s\n",$1,$2,$3}'

hr "Pods"
bad=$(kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded \
      --no-headers 2>/dev/null | wc -l | tr -d ' ')
printf '  %s laufend, %s auffaellig\n' \
  "$(kubectl get pods -A --no-headers 2>/dev/null | wc -l | tr -d ' ')" "$bad"
[ "$bad" -gt 0 ] && kubectl get pods -A \
  --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers 2>/dev/null \
  | awk '{printf "  %-14s %-38s %s\n",$1,$2,$4}' | head -8

hr "Speicher"
kubectl get sc --no-headers 2>/dev/null | awk '{printf "  StorageClass %s\n",$1}'
printf '  Volumes: %s gebunden\n' \
  "$(kubectl get pvc -A --no-headers 2>/dev/null | grep -c Bound)"

hr "Dienste"
GW=$(kubectl -n traefik get svc traefik \
     -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
if [ -z "$GW" ]; then
  echo "  Traefik hat keine Adresse."
else
  echo "  Gateway: $GW"
  kubectl get httproute -A -o jsonpath='{range .items[*]}{range .spec.hostnames[*]}{@}{"\n"}{end}{end}' \
    2>/dev/null | sort -u | while read -r h; do
    [ -z "$h" ] && continue
    code=$(curl -sk --max-time 6 --resolve "$h:443:$GW" \
           -o /dev/null -w '%{http_code}' "https://$h/" 2>/dev/null)
    printf '  %-32s HTTP %s\n' "$h" "${code:-keine Antwort}"
  done
fi
