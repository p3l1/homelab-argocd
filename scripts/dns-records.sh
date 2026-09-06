#!/usr/bin/env bash
#
# Listet die DNS-Eintraege, die im Router hinterlegt sein muessen - abgeleitet
# aus den HTTPRoutes im Cluster, nicht aus einer gepflegten Liste.
#
# Solange external-dns ruht (siehe apps/external-dns/README.md), gehoeren sie
# von Hand in den UniFi Express unter
# Settings -> Routing & Firewall -> DNS -> Local DNS Records.

set -euo pipefail

GW_IP=$(kubectl -n traefik get svc traefik \
        -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
[[ -n "$GW_IP" ]] || { echo "Traefik hat keine Adresse." >&2; exit 1; }

printf '%-34s %s\n' "NAME" "ZIEL"
printf '%-34s %s\n' "----------------------------------" "-------------"
kubectl get httproute -A -o jsonpath='{range .items[*]}{range .spec.hostnames[*]}{@}{"\n"}{end}{end}' \
  2>/dev/null | sort -u | while read -r host; do
  [[ -n "$host" ]] && printf '%-34s %s\n' "$host" "$GW_IP"
done
