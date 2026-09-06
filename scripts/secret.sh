#!/usr/bin/env bash
#
# Legt ein Kubernetes-Secret an und hinterlegt es SOPS-verschluesselt im Repo.
#
#   ./scripts/secret.sh newt-credentials newt PANGOLIN_ENDPOINT NEWT_ID NEWT_SECRET
#
# Die Werte werden einzeln abgefragt und dabei nicht angezeigt. Ohne Eingabe
# bleibt ein vorhandener Wert aus der verschluesselten Datei bestehen, sodass
# sich einzelne Schluessel nachtragen lassen.
#
# Das Secret geht sofort in den Cluster und zusaetzlich nach
# secrets/<name>.sops.yaml - sonst waere es nach einem Neuaufbau verloren.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[94m==>\033[0m %s\n' "$1"; }
ok() { printf '\033[92m[OK]\033[0m %s\n' "$1"; }

[[ $# -ge 3 ]] || die "Aufruf: $0 <name> <namespace> <SCHLUESSEL> [SCHLUESSEL ...]"
NAME="$1"; NS="$2"; shift 2
KEYS=("$@")

command -v sops >/dev/null || die "sops fehlt."
command -v kubectl >/dev/null || die "kubectl fehlt."

FILE="secrets/${NAME}.sops.yaml"
mkdir -p secrets

# Vorhandene Werte einlesen, damit einzelne Schluessel ergaenzt werden koennen.
declare -A CURRENT=()
if [[ -f "$FILE" ]]; then
  info "Vorhandene Datei $FILE wird als Grundlage genommen"
  while IFS='=' read -r k v; do
    [[ -n "$k" ]] && CURRENT["$k"]="$v"
  done < <(sops -d "$FILE" 2>/dev/null | python3 -c "
import sys, yaml
d = yaml.safe_load(sys.stdin) or {}
for k, v in (d.get('stringData') or {}).items():
    print(f'{k}={v}')
" 2>/dev/null || true)
fi

declare -A VALUES=()
for k in "${KEYS[@]}"; do
  if [[ -n "${CURRENT[$k]:-}" ]]; then
    read -r -s -p "  ${k} [vorhanden, Enter behaelt]: " val; echo
    VALUES["$k"]="${val:-${CURRENT[$k]}}"
  else
    read -r -s -p "  ${k}: " val; echo
    [[ -n "$val" ]] || die "$k darf nicht leer sein."
    VALUES["$k"]="$val"
  fi
done

# Schluessel, die schon in der Datei stehen und diesmal nicht abgefragt
# wurden, bleiben erhalten. Ohne das loescht ein Aufruf, der nur einen
# Schluessel nachtragen will, alle uebrigen aus der Datei - im Cluster
# faellt es nicht auf, weil "kubectl apply" zusammenfuehrt, aber nach
# einem Neuaufbau waeren sie weg.
ALL_KEYS=("${KEYS[@]}")
for k in "${!CURRENT[@]}"; do
  if [[ -z "${VALUES[$k]:-}" ]]; then
    VALUES["$k"]="${CURRENT[$k]}"
    ALL_KEYS+=("$k")
    info "$k bleibt unveraendert erhalten"
  fi
done

# Erst schreiben, dann verschluesseln - die Klartextfassung existiert nur
# kurz und mit engen Rechten.
TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT
chmod 600 "$TMP"
{
  echo "# Von scripts/secret.sh erzeugt. Anwenden mit:"
  echo "#   sops -d $FILE | kubectl apply -f -"
  echo "apiVersion: v1"
  echo "kind: Secret"
  echo "metadata:"
  echo "  name: $NAME"
  echo "  namespace: $NS"
  echo "type: Opaque"
  echo "stringData:"
  for k in "${ALL_KEYS[@]}"; do
    printf '  %s: %s\n' "$k" "$(printf '%s' "${VALUES[$k]}" | python3 -c 'import sys,json;print(json.dumps(sys.stdin.read()))')"
  done
} > "$TMP"

info "Wende das Secret im Cluster an"
kubectl get namespace "$NS" >/dev/null 2>&1 || kubectl create namespace "$NS" >/dev/null
kubectl apply -f "$TMP" >/dev/null
ok "Secret $NAME in $NS angelegt"

cp "$TMP" "$FILE"
sops --encrypt --in-place "$FILE"
ok "Verschluesselt nach $FILE"

grep -q "ENC\[" "$FILE" || die "Die Datei ist nicht verschluesselt - bitte pruefen."
echo
echo "Noch einzuchecken:  git add $FILE && git commit"
