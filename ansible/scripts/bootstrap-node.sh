#!/usr/bin/env bash
#
# Erstkontakt mit einem frisch aufgesetzten Node.
#
#   ./bootstrap-node.sh kube-04
#   ./bootstrap-node.sh kube-04 -e node_sudo_via_ssh_agent=true
#
# Waehlt inventory/bootstrap.yml aus - dort steht die aktuelle DHCP-Adresse.
# Mit dem reguleren Inventory liefe der Aufruf gegen die Zieladresse, die der
# Node noch gar nicht hat.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }

[[ $# -ge 1 ]] || die "Aufruf: $0 <node> [weitere ansible-playbook-Optionen]"
NODE="$1"; shift

grep -q "^        ${NODE}:" inventory/bootstrap.yml \
  || die "$NODE steht nicht in inventory/bootstrap.yml."

if grep -A1 "^        ${NODE}:" inventory/bootstrap.yml | grep -q CHANGEME; then
  die "Fuer $NODE ist in inventory/bootstrap.yml noch keine Adresse eingetragen."
fi

HOST=$(grep -A1 "^        ${NODE}:" inventory/bootstrap.yml \
       | awk '/ansible_host/ {print $2}')
printf '\033[94m==>\033[0m %s ueber %s, Passwort ist zweimal das des Benutzers pi\n\n' "$NODE" "$HOST"

exec ansible-playbook -i inventory/bootstrap.yml playbooks/bootstrap.yml \
  --limit "$NODE" --ask-pass --ask-become-pass "$@"
