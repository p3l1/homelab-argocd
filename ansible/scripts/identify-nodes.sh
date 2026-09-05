#!/usr/bin/env bash
#
# Fragt frisch aufgesetzte Pis nach Modell, Seriennummer und MAC-Adresse.
# Grundlage fuer die Zuordnung in inventory/bootstrap.yml - die Server
# gehoeren auf die Raspberry Pi 4, die Agents auf die Pi 5.
#
#   ./identify-nodes.sh 10.35.99.11 10.35.99.20 10.35.99.30
#
# Der Benutzer ist "pi", das Passwort wird einmal abgefragt und fuer alle
# Geraete verwendet.

set -euo pipefail

USER_NAME="pi"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }

[[ $# -ge 1 ]] || die "Aufruf: $0 <ip> [ip ...]"
command -v sshpass >/dev/null || die "sshpass fehlt. Installation: brew install sshpass"

read -r -s -p "Passwort fuer ${USER_NAME}: " PW
echo
echo

printf '%-15s %-22s %-18s %s\n' "ADRESSE" "MODELL" "MAC" "SERIENNUMMER"
printf '%-15s %-22s %-18s %s\n' "---------------" "----------------------" "------------------" "----------------"

for ip in "$@"; do
  out=$(sshpass -p "$PW" ssh \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=5 -o LogLevel=ERROR \
        "${USER_NAME}@${ip}" \
        'printf "%s|%s|%s" "$(tr -d "\0" </proc/device-tree/model)" \
                           "$(cat /sys/class/net/eth0/address 2>/dev/null || echo -)" \
                           "$(grep -m1 Serial /proc/cpuinfo | awk "{print \$3}")' \
        2>/dev/null) || { printf '%-15s %s\n' "$ip" "nicht erreichbar"; continue; }

  IFS='|' read -r model mac serial <<< "$out"
  printf '%-15s %-22s %-18s %s\n' "$ip" "${model:-?}" "${mac:-?}" "${serial:-?}"
done

echo
echo "Die Adressen entsprechend in inventory/bootstrap.yml eintragen:"
echo "  Pi 4 -> kube-01..04   |   Pi 5 -> kube-05, kube-06"
