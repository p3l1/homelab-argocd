#!/usr/bin/env bash
#
# Holt das Wurzelzertifikat der cluster-lokalen CA und legt es im Schlüsselbund
# ab. Ohne das meldet jeder Browser bei *.homelab.internal eine unsichere
# Verbindung.
#
#   ./scripts/trust-ca.sh            nur herunterladen
#   ./scripts/trust-ca.sh --install  zusaetzlich im System hinterlegen

set -euo pipefail

OUT="${TMPDIR:-/tmp}/homelab-ca.crt"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }
ok() { printf '\033[92m[OK]\033[0m %s\n' "$1"; }

kubectl -n cert-manager get secret homelab-ca-key-pair >/dev/null 2>&1 \
  || die "homelab-ca-key-pair nicht gefunden - laeuft cert-manager?"

kubectl -n cert-manager get secret homelab-ca-key-pair \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > "$OUT"
ok "Zertifikat liegt unter $OUT"

openssl x509 -in "$OUT" -noout -subject -enddate | sed 's/^/  /'

if [[ "${1:-}" == "--install" ]]; then
  [[ "$(uname -s)" == "Darwin" ]] || die "--install ist nur fuer macOS gebaut."
  # Der Systemschluesselbund verlangt erhoehte Rechte; per Touch ID bestaetigen.
  sudo security add-trusted-cert -d -r trustRoot \
    -k /Library/Keychains/System.keychain "$OUT"
  ok "Im Systemschluesselbund hinterlegt"
else
  echo
  echo "Zum Hinterlegen:  $0 --install"
fi
