#!/usr/bin/env bash
#
# Schreibt Raspberry Pi OS Lite arm64 auf eine SSD und legt die
# Erstkonfiguration fuer einen Cluster-Node ab.
#
#   ./flash-node.sh kube-01 /dev/disk6
#   ./flash-node.sh --config-only kube-01 /dev/disk6
#
# Mit --config-only wird nur die custom.toml neu geschrieben, das Image bleibt
# unberuehrt - gedacht fuer bereits geflashte SSDs, deren hinterlegte
# Schluessel sich geaendert haben.
#
# Danach: SSD in den Pi, einschalten, dann
#   ansible-playbook playbooks/bootstrap.yml --limit kube-01
#
# Der Lauf ist wiederholbar - eine erneute Ausfuehrung stellt den
# Auslieferungszustand wieder her.

set -euo pipefail

IMAGE_URL="https://downloads.raspberrypi.com/raspios_lite_arm64_latest"
CACHE_DIR="${HOME}/.cache/homelab-images"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_DIR="${SCRIPT_DIR}/../files/ssh"
NODE_USER="philipp"
TIMEZONE="Europe/Berlin"
KEYMAP="de"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[94m==>\033[0m %s\n' "$1"; }
ok() { printf '\033[92m[OK]\033[0m %s\n' "$1"; }

CONFIG_ONLY=false
if [[ "${1:-}" == "--config-only" ]]; then
  CONFIG_ONLY=true
  shift
fi

[[ $# -eq 2 ]] || die "Aufruf: $0 [--config-only] <hostname> <device>   z.B. $0 kube-01 /dev/disk6"
HOSTNAME="$1"
DEVICE="$2"

[[ "$(uname -s)" == "Darwin" ]] || die "Dieses Skript ist fuer macOS geschrieben."
[[ "$HOSTNAME" =~ ^kube-[0-9]{2}$ ]] || die "Hostname muss der Form kube-NN entsprechen."
$CONFIG_ONLY || command -v xz >/dev/null || die "xz fehlt. Installation: brew install xz"

# --- Ziel-Device pruefen --------------------------------------------------
[[ -b "$DEVICE" || -c "$DEVICE" ]] || die "$DEVICE ist kein Geraet."
[[ "$DEVICE" =~ ^/dev/disk[0-9]+$ ]] || die "Erwartet wird ein ganzes Geraet wie /dev/disk6, keine Partition."

if ! diskutil info "$DEVICE" | grep -qE '^\s*(Device Location|Internal):\s+(External|No)'; then
  die "$DEVICE sieht nach einem internen Datentraeger aus. Abbruch."
fi

# --- Schluessel einsammeln ------------------------------------------------
[[ -d "$KEY_DIR" ]] || die "Schluesselverzeichnis $KEY_DIR fehlt."
KEYS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && KEYS+=("$line")
done < <(cat "$KEY_DIR"/*.pub 2>/dev/null || true)
[[ ${#KEYS[@]} -gt 0 ]] || die "In $KEY_DIR liegt kein oeffentlicher Schluessel."

if ! $CONFIG_ONLY; then
  echo
  diskutil info "$DEVICE" | grep -E 'Device / Media Name|Disk Size|Protocol|Internal|Removable Media' || true
  echo
  printf '\033[93mACHTUNG:\033[0m Alle Daten auf %s werden geloescht.\n' "$DEVICE"
  read -r -p "Zur Bestaetigung den Geraetepfad erneut eingeben: " CONFIRM
  [[ "$CONFIRM" == "$DEVICE" ]] || die "Eingabe stimmt nicht ueberein. Abbruch."

  # --- Image beschaffen ---------------------------------------------------
  mkdir -p "$CACHE_DIR"
  info "Ermittle aktuelles Image"
  RESOLVED="$(curl -sIL -o /dev/null -w '%{url_effective}' "$IMAGE_URL")"
  [[ "$RESOLVED" == *.img.xz ]] || die "Unerwartete Image-URL: $RESOLVED"
  IMAGE_XZ="${CACHE_DIR}/$(basename "$RESOLVED")"

  if [[ ! -f "$IMAGE_XZ" ]]; then
    info "Lade $(basename "$RESOLVED")"
    curl -fL --progress-bar -o "${IMAGE_XZ}.part" "$RESOLVED"
    mv "${IMAGE_XZ}.part" "$IMAGE_XZ"
  else
    ok "Image bereits im Cache"
  fi

  info "Pruefe Signatur"
  EXPECTED="$(curl -fsSL "${RESOLVED}.sha256" | awk '{print $1}')"
  ACTUAL="$(shasum -a 256 "$IMAGE_XZ" | awk '{print $1}')"
  [[ "$EXPECTED" == "$ACTUAL" ]] || die "SHA256 stimmt nicht. Erwartet $EXPECTED, gelesen $ACTUAL"
  ok "SHA256 stimmt"

  # --- Schreiben ----------------------------------------------------------
  RAW_DEVICE="${DEVICE/\/dev\/disk//dev/rdisk}"
  info "Haenge $DEVICE aus"
  diskutil unmountDisk "$DEVICE"

  info "Schreibe Image auf $RAW_DEVICE (dauert einige Minuten)"
  xz -dc "$IMAGE_XZ" | sudo dd of="$RAW_DEVICE" bs=4m status=progress
  sync
  ok "Image geschrieben"
fi

# --- Erstkonfiguration ----------------------------------------------------
info "Warte auf die Boot-Partition"
sudo diskutil mountDisk "$DEVICE" >/dev/null
BOOT=""
for _ in $(seq 1 20); do
  BOOT="$(diskutil info "${DEVICE}s1" 2>/dev/null | awk -F': *' '/Mount Point/ {print $2}' | sed 's/ *$//')"
  [[ -n "$BOOT" && -d "$BOOT" ]] && break
  sleep 1
done
[[ -n "$BOOT" && -d "$BOOT" ]] || die "Boot-Partition wurde nicht eingehaengt."

if $CONFIG_ONLY; then
  [[ -f "${BOOT}/cmdline.txt" && -f "${BOOT}/config.txt" ]] \
    || die "Auf $DEVICE liegt kein Raspberry-Pi-OS-Abbild. Ohne --config-only aufrufen."
fi

# Zufaelliges Passwort: die Anmeldung laeuft ausschliesslich ueber die
# SSH-Schluessel, custom.toml verlangt aber ein gesetztes Passwort.
PW_HASH="$(openssl passwd -6 "$(openssl rand -base64 32)")"

# authorized_keys als TOML-Array
KEY_LIST=""
for k in "${KEYS[@]}"; do
  KEY_LIST+="\n  \"${k}\","
done
KEY_LIST="${KEY_LIST%,}"

cat > "${BOOT}/custom.toml" <<TOML
# Von flash-node.sh erzeugt. Wird beim ersten Start ausgewertet.
config_version = 1

[system]
hostname = "${HOSTNAME}"

[user]
name = "${NODE_USER}"
password = "${PW_HASH}"
password_encrypted = true

[ssh]
enabled = true
password_authentication = false
authorized_keys = [$(printf "%b" "$KEY_LIST")
]

[locale]
keymap = "${KEYMAP}"
timezone = "${TIMEZONE}"
TOML

sync
ok "custom.toml fuer ${HOSTNAME} abgelegt (${#KEYS[@]} Schluessel)"
diskutil unmountDisk "$DEVICE" >/dev/null

echo
if $CONFIG_ONLY; then
  ok "Konfiguration aktualisiert, Abbild unveraendert."
else
  ok "Fertig. SSD in den Pi setzen und einschalten."
fi
echo "   Danach:  ansible-playbook playbooks/bootstrap.yml --limit ${HOSTNAME}"
