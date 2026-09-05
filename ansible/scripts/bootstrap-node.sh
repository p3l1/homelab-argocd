#!/usr/bin/env bash
#
# Erstkontakt mit einem oder mehreren Nodes - waehlt selbst das passende
# Inventory.
#
#   ./bootstrap-node.sh kube-04
#   ./bootstrap-node.sh kube-01 kube-02 kube-03
#   ./bootstrap-node.sh all
#   ./bootstrap-node.sh all -- -e node_sudo_via_ssh_agent=true
#   ./bootstrap-node.sh all --dry-run
#
# Ein frisch aufgesetzter Node haengt am DHCP und wird ueber
# inventory/bootstrap.yml erreicht. Hat er seine feste Adresse schon, greift
# das regulaere Inventory. Nodes beider Sorten werden in getrennten Laeufen
# abgearbeitet.
#
# Alles nach -- geht unveraendert an ansible-playbook.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[94m==>\033[0m %s\n' "$1"; }

ALL_NODES=(kube-01 kube-02 kube-03 kube-04 kube-05 kube-06)

NODES=()
EXTRA=()
DRY_RUN=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --) shift; EXTRA=("$@"); break ;;
    --dry-run) DRY_RUN=true ;;
    all) NODES=("${ALL_NODES[@]}") ;;
    *) NODES+=("$1") ;;
  esac
  shift
done
[[ ${#NODES[@]} -gt 0 ]] || die "Aufruf: $0 <node|all> [node ...] [-- ansible-playbook-Optionen]"

reachable() { nc -z -G 3 "$1" 22 >/dev/null 2>&1; }

VIA_DHCP=()
VIA_TARGET=()
for NODE in "${NODES[@]}"; do
  grep -q "^        ${NODE}:" inventory/bootstrap.yml \
    || die "$NODE steht nicht in inventory/bootstrap.yml."
  BLOCK=$(grep -A3 "^        ${NODE}:" inventory/bootstrap.yml)
  DHCP_IP=$(awk '/ansible_host/ {print $2}' <<<"$BLOCK")
  TARGET_IP=$(awk '/node_address/ {print $2}' <<<"$BLOCK")
  [[ "$DHCP_IP" == *CHANGEME* ]] && die "Fuer $NODE fehlt die Adresse in inventory/bootstrap.yml."

  if reachable "$TARGET_IP"; then
    VIA_TARGET+=("$NODE"); info "$NODE ist bereits unter $TARGET_IP"
  elif reachable "$DHCP_IP"; then
    VIA_DHCP+=("$NODE"); info "$NODE unter $DHCP_IP, Ziel $TARGET_IP"
  else
    die "$NODE antwortet weder unter $TARGET_IP noch unter $DHCP_IP."
  fi
done

run_group() {
  local inv="$1"; shift
  local nodes="$1"; shift

  if $DRY_RUN; then
    printf '  wuerde laufen: ansible-playbook -i %s --limit %s\n' "$inv" "$nodes"
    return 0
  fi

  local first="${nodes%%,*}"
  local probe
  probe=$(grep -A3 "^        ${first}:" inventory/bootstrap.yml \
          | awk -v k="$( [[ "$inv" == *bootstrap* ]] && echo ansible_host || echo node_address )" \
                '$1 ~ k {print $2}')

  # Steht der Schluessel schon, braucht es kein Passwort mehr.
  local auth=(--ask-pass)
  if ssh -n -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
         -o ConnectTimeout=5 "pi@${probe}" true >/dev/null 2>&1; then
    auth=()
    info "Anmeldung per Schluessel moeglich - kein --ask-pass"
  else
    info "Passwort wird abgefragt (SSH und sudo, beides der Benutzer pi)"
  fi

  echo
  ansible-playbook -i "$inv" playbooks/bootstrap.yml \
    --limit "$nodes" "${auth[@]}" --ask-become-pass "${EXTRA[@]+"${EXTRA[@]}"}"
}

if [[ ${#VIA_DHCP[@]} -gt 0 ]]; then
  printf '\n\033[1m--- Uebergangs-Inventory: %s ---\033[0m\n' "${VIA_DHCP[*]}"
  run_group inventory/bootstrap.yml "$(IFS=,; echo "${VIA_DHCP[*]}")"
fi

if [[ ${#VIA_TARGET[@]} -gt 0 ]]; then
  printf '\n\033[1m--- Regulaeres Inventory: %s ---\033[0m\n' "${VIA_TARGET[*]}"
  run_group inventory/hosts.yml "$(IFS=,; echo "${VIA_TARGET[*]}")"
fi
