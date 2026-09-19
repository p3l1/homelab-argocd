#!/usr/bin/env bash
#
# Hinterlegt einen ghcr-Zugang an den beiden Stellen, die ihn brauchen:
#
#   ghcr-pull    dockerconfigjson in preview-secrets, von apps/preview-secrets
#                in jeden Preview-Namensraum kopiert - damit die Pods die
#                privaten Images ziehen koennen
#   ghcr-charts  Repository-Eintrag in argocd, damit ArgoCD das OCI-Chart
#                findet
#
#   ./scripts/registry-credentials.sh
#
# Erwartet ein Personal Access Token (classic) mit read:packages. Der Token
# wird verdeckt abgefragt, vor dem Schreiben an der Registry erprobt und
# landet nur SOPS-verschluesselt im Repo.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[91mFehler:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[94m==>\033[0m %s\n' "$1"; }
ok() { printf '\033[92m[OK]\033[0m %s\n' "$1"; }

USER_NAME="${GHCR_USER:-p3l1}"
PROBE_IMAGE="${GHCR_PROBE:-p3l1/taktwerk}"

command -v sops >/dev/null || die "sops fehlt."
command -v kubectl >/dev/null || die "kubectl fehlt."

read -r -s -p "  ghcr-Token fuer ${USER_NAME} (read:packages): " TOKEN; echo
[[ -n "$TOKEN" ]] || die "Der Token darf nicht leer sein."

# Erst erproben, dann schreiben: ein Token ohne read:packages faellt sonst
# erst als ImagePullBackOff auf, weit weg von seiner Ursache.
info "Erprobe den Token an ghcr.io/${PROBE_IMAGE}"
BEARER=$(curl -fsSL -u "${USER_NAME}:${TOKEN}" \
  "https://ghcr.io/token?scope=repository:${PROBE_IMAGE}:pull&service=ghcr.io" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))') \
  || die "Die Registry hat die Anmeldung abgelehnt."
[[ -n "$BEARER" ]] || die "Die Registry hat kein Token ausgestellt."

curl -fsS -o /dev/null -H "Authorization: Bearer ${BEARER}" \
  "https://ghcr.io/v2/${PROBE_IMAGE}/tags/list" \
  || die "Anmeldung ok, aber kein Lesezugriff - fehlt dem Token read:packages?"
ok "Der Token darf ghcr.io/${PROBE_IMAGE} lesen"

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT; chmod 700 "$TMP"

AUTH=$(printf '%s:%s' "$USER_NAME" "$TOKEN" | base64 | tr -d '\n')
DOCKERCFG=$(python3 - "$USER_NAME" "$TOKEN" "$AUTH" <<'PY'
import base64, json, sys
user, token, auth = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = {"auths": {"ghcr.io": {"username": user, "password": token, "auth": auth}}}
print(base64.b64encode(json.dumps(cfg).encode()).decode())
PY
)

cat > "$TMP/ghcr-pull.yaml" <<EOF
# Von scripts/registry-credentials.sh erzeugt. Anwenden mit:
#   sops -d secrets/ghcr-pull.sops.yaml | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: ghcr-pull
  namespace: preview-secrets
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: ${DOCKERCFG}
EOF

cat > "$TMP/ghcr-charts.yaml" <<EOF
# Von scripts/registry-credentials.sh erzeugt. Anwenden mit:
#   sops -d secrets/ghcr-charts.sops.yaml | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: ghcr-charts
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repository
type: Opaque
stringData:
  name: ghcr-charts
  url: ghcr.io/p3l1/charts
  type: helm
  enableOCI: "true"
  username: ${USER_NAME}
  password: ${TOKEN}
EOF

info "Wende beide Secrets im Cluster an"
kubectl get namespace preview-secrets >/dev/null 2>&1 \
  || kubectl create namespace preview-secrets >/dev/null
kubectl apply -f "$TMP/ghcr-pull.yaml" >/dev/null
kubectl apply -f "$TMP/ghcr-charts.yaml" >/dev/null
ok "ghcr-pull in preview-secrets und ghcr-charts in argocd angelegt"

for f in ghcr-pull ghcr-charts; do
  cp "$TMP/$f.yaml" "secrets/$f.sops.yaml"
  sops --encrypt --in-place "secrets/$f.sops.yaml"
  grep -q "ENC\[" "secrets/$f.sops.yaml" || die "secrets/$f.sops.yaml ist nicht verschluesselt."
  ok "Verschluesselt nach secrets/$f.sops.yaml"
done

echo
echo "Noch einzuchecken:  git add secrets/ghcr-pull.sops.yaml secrets/ghcr-charts.sops.yaml && git commit"
