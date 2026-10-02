#!/usr/bin/env bash
#
# Legt einen Pangolin-Maschinen-Client über die Integration-API an.
#
#   ./scripts/pangolin-client.sh "cloud.p3l1.de Arcane Agent"
#
# Das Dashboard kann das nicht: es antwortet 403, auch dem Org-Owner. Die
# Begruendung steht in pangolin/README.md unter "Clients entstehen nur ueber
# die API". Der API-Schluessel braucht die Aktion createClient.
#
# Gibt niceId, Client-ID und Secret aus. Das Secret zeigt Pangolin nur hier,
# danach nie wieder.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[94m==>\033[0m %s\n' "$1"; }

[[ $# -eq 1 ]] || die "Aufruf: $0 <Name>"
NAME="$1"

command -v sops >/dev/null || die "sops fehlt."

SECRETS=secrets/pangolin-credentials.sops.yaml
[[ -f $SECRETS ]] || die "$SECRETS fehlt."

info "Lese Zugangsdaten aus $SECRETS"
sops -d "$SECRETS" | NAME="$NAME" python3 -c '
import json, os, sys, urllib.error, urllib.request, yaml

data = (yaml.safe_load(sys.stdin) or {}).get("stringData") or {}
for key in ("PANGOLIN_ENDPOINT", "PANGOLIN_INTEGRATION_API_KEY", "PANGOLIN_ORG_ID"):
    if not data.get(key):
        sys.exit(f"Fehler: {key} fehlt in der Datei.")

endpoint = data["PANGOLIN_ENDPOINT"].rstrip("/")
org = data["PANGOLIN_ORG_ID"]
headers = {
    "Authorization": "Bearer " + data["PANGOLIN_INTEGRATION_API_KEY"],
    "Content-Type": "application/json",
}


def call(method, path, body=None):
    request = urllib.request.Request(
        endpoint + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:400]
        hint = ""
        if error.code == 403:
            hint = "\n  Dem API-Schluessel fehlt wohl die Aktion createClient."
        sys.exit(f"Fehler: {method} {path} -> {error.code}\n  {detail}{hint}")


defaults = call("GET", f"/org/{org}/pick-client-defaults")["data"]
created = call(
    "PUT",
    f"/org/{org}/client",
    {
        "name": os.environ["NAME"],
        "olmId": defaults["olmId"],
        "secret": defaults["olmSecret"],
        "subnet": defaults["subnet"],
        "type": "olm",
    },
)["data"]

print()
print(f"  niceId  {created.get('niceId')}")
print(f"  id      {defaults['olmId']}")
print(f"  secret  {defaults['olmSecret']}")
print(f"  subnet  {defaults['subnet']}")
print()
print("niceId gehoert in die machines-Liste der Ressource in")
print("pangolin/blueprints/homelab.yaml, id und secret auf den Host.")
'
