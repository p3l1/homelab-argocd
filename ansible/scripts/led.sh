#!/usr/bin/env bash
#
# Schaltet die Rack-LED eines Nodes vom Mac aus.
#
#   ./led.sh kube-05 blink        blinkt 60s
#   ./led.sh kube-05 blink 120
#   ./led.sh kube-05 on|off|status
#   ./led.sh all status
#
# Die LED sitzt am Rackmate-Einschub und ist nur an den Raspberry Pi 5
# verdrahtet - auf den Pi 4 laeuft der Befehl, bleibt aber unsichtbar.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }

[[ $# -ge 1 ]] || die "Aufruf: $0 <node|all> [on|off|blink [Sekunden]|status]"
TARGET="$1"; shift
ACTION=("${@:-status}")

address_of() {
  # Ohne das || true beendet set -e das Skript, wenn grep nichts findet -
  # die Fehlermeldung unten kaeme dann nie.
  grep -A3 "^        ${1}:" inventory/hosts.yml 2>/dev/null \
    | awk '/ansible_host/ {print $2}' || true
}

if [[ "$TARGET" == all ]]; then
  NODES=(kube-01 kube-02 kube-03 kube-04 kube-05 kube-06)
else
  NODES=("$TARGET")
fi

for NODE in "${NODES[@]}"; do
  IP=$(address_of "$NODE")
  [[ -n "$IP" ]] || die "$NODE steht nicht in inventory/hosts.yml."
  ssh -n -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
      "pi@${IP}" "node-led ${ACTION[*]}" 2>&1 \
    || printf '\033[91m%s nicht erreichbar\033[0m\n' "$NODE"
done
