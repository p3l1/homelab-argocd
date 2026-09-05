#!/usr/bin/env bash
#
# Erstkontakt mit einem Node - waehlt selbst das passende Inventory.
#
#   ./bootstrap-node.sh kube-04
#   ./bootstrap-node.sh kube-04 -e node_sudo_via_ssh_agent=true
#
# Ein frisch aufgesetzter Node haengt am DHCP und wird ueber
# inventory/bootstrap.yml erreicht. Hat er seine feste Adresse schon - etwa
# nach einem abgebrochenen Lauf - greift das regulaere Inventory. Das Skript
# probiert beide Adressen und nimmt die, die antwortet.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[94m==>\033[0m %s\n' "$1"; }

[[ $# -ge 1 ]] || die "Aufruf: $0 <node> [weitere ansible-playbook-Optionen]"
NODE="$1"; shift

grep -q "^        ${NODE}:" inventory/bootstrap.yml \
  || die "$NODE steht nicht in inventory/bootstrap.yml."

BLOCK=$(grep -A3 "^        ${NODE}:" inventory/bootstrap.yml)
DHCP_IP=$(awk '/ansible_host/ {print $2}' <<<"$BLOCK")
TARGET_IP=$(awk '/node_address/ {print $2}' <<<"$BLOCK")

[[ "$DHCP_IP" == *CHANGEME* ]] \
  && die "Fuer $NODE ist in inventory/bootstrap.yml noch keine Adresse eingetragen."

reachable() { nc -z -G 3 "$1" 22 >/dev/null 2>&1; }

if reachable "$TARGET_IP"; then
  INV="inventory/hosts.yml"
  info "$NODE antwortet bereits unter $TARGET_IP - regulaeres Inventory"
elif reachable "$DHCP_IP"; then
  INV="inventory/bootstrap.yml"
  info "$NODE antwortet unter $DHCP_IP - Uebergangs-Inventory, Ziel $TARGET_IP"
else
  die "$NODE antwortet weder unter $TARGET_IP noch unter $DHCP_IP."
fi

# Steht der Schluessel schon, braucht es kein Passwort mehr.
AUTH_ARGS=(--ask-pass)
if ssh -n -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
       -o ConnectTimeout=5 "pi@$(reachable "$TARGET_IP" && echo "$TARGET_IP" || echo "$DHCP_IP")" \
       true >/dev/null 2>&1; then
  AUTH_ARGS=()
  info "Anmeldung per Schluessel moeglich - kein --ask-pass noetig"
else
  info "Passwort wird abgefragt (SSH und sudo, beides der Benutzer pi)"
fi

echo
exec ansible-playbook -i "$INV" playbooks/bootstrap.yml \
  --limit "$NODE" "${AUTH_ARGS[@]}" --ask-become-pass "$@"
