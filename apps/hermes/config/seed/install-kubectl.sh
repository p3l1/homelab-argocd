#!/bin/sh
# Legt kubectl fuer den Cluster-Check aufs Volume (nur Lesezugriff ueber den
# ServiceAccount). Fehlt im Image. Version = Cluster-Version; bei anderer
# Version wird neu installiert. KUBECTL_VERSION kommt aus dem initContainer.
set -eu
have=$(/opt/data/bin/kubectl version --client -o json 2>/dev/null |
  grep -o '"gitVersion": "[^"]*' | head -1 | cut -d'"' -f4 || true)
[ "$have" = "v${KUBECTL_VERSION}" ] && exit 0
url="https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/arm64/kubectl"
curl -fsSL -o /tmp/kubectl "$url"
echo "$(curl -fsSL "$url.sha256")  /tmp/kubectl" | sha256sum -c -
install -D -m 0755 /tmp/kubectl /opt/data/bin/kubectl
