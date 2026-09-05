# Cluster-Neuaufbau

Der Weg von einer leeren SSD bis zum laufenden ArgoCD. Jeder Schritt ist
wiederholbar: Ein zweiter Durchlauf verändert nichts mehr.

Die Entwurfsentscheidungen stehen in
[`superpowers/specs/2026-09-05-cluster-rebuild-design.md`](superpowers/specs/2026-09-05-cluster-rebuild-design.md).

## Aufbau des Clusters

| Rolle | Hardware | Hostname | Adresse |
|---|---|---|---|
| API-VIP (kube-vip) | — | — | `10.35.99.210` |
| Server, etcd, getaintet | 3× Pi 4 | `kube-01` – `kube-03` | `.211` – `.213` |
| Agent | 1× Pi 4 | `kube-04` | `.214` |
| Agent | 2× Pi 5 | `kube-05`, `kube-06` | `.215` – `.216` |
| reserviert, derzeit Docker | 2× Pi 5 | `kube-07`, `kube-08` | `.217` – `.218` |
| MetalLB-Pool | — | — | `.230` – `.250` |

Ausgespart bleiben `.1` (Gateway) sowie `.100` und `.200` — die gehören dem
Talos-Cluster aus `homelab-monitoring`.

## Voraussetzungen auf dem Mac

```bash
brew install ansible sops xz            # unter Nix bereits vorhanden
cd ansible
ansible-galaxy collection install -r requirements.yml -p ./.collections
```

Der PGP-Schlüssel `7954EC02CDDF896536DFDCDE056C6FDDF9E15CF2` muss zum
Entschlüsseln verfügbar sein. Zur Probe:

```bash
ansible-inventory --list | grep -c token   # 8 erwartet, einmal je Node
```

## 1. SSD beschreiben

```bash
cd ansible
./scripts/flash-node.sh kube-01 /dev/disk6
```

Das Skript lädt das aktuelle Raspberry Pi OS Lite arm64, prüft die
SHA256-Summe und verlangt eine ausdrückliche Bestätigung des Ziel-Device —
**der Schreibvorgang löscht die SSD vollständig**. Anschließend legt es die
`custom.toml` mit Hostname, Benutzer, SSH-Schlüssel und Locale ab.

Hinterlegt werden alle öffentlichen Schlüssel aus `ansible/files/ssh/` —
derzeit der YubiKey (GPG-Authentication-Subkey) und ein lokaler Schlüssel als
Rückfallweg. Die Rolle `node_base` pflegt später dieselbe Liste, Quelle ist
also beide Male dasselbe Verzeichnis. Passwort-Anmeldung ist abgeschaltet.

Ändern sich die Schlüssel, muss eine bereits geflashte SSD nicht neu
beschrieben werden:

```bash
./scripts/flash-node.sh --config-only kube-01 /dev/disk4
```

Das schreibt nur die `custom.toml` neu und lässt das Abbild unberührt.

Das richtige Gerät findest du mit `diskutil list` — interne Datenträger lehnt
das Skript ab.

## 2. Node in Betrieb nehmen

SSD in den Pi, einschalten, etwa eine Minute warten. Dann:

```bash
ansible-playbook playbooks/bootstrap.yml --limit kube-01
```

Der Node startet per DHCP und meldet sich über mDNS als `kube-01.local`; über
diesen Namen verbindet sich das Playbook und schreibt die feste Adresse per
NetworkManager fest. Der Node startet dabei einmal neu.

Vor jeder Änderung prüft das Playbook, ob der antwortende Host wirklich der
gemeinte ist — so lässt sich nicht versehentlich ein laufender Node
überschreiben.

Schritte 1 und 2 für jeden der sechs Nodes wiederholen.

## 3. Cluster ausrollen

```bash
ansible-playbook playbooks/site.yml
```

Das Playbook konfiguriert die Nodes (`node_base`), wendet die Vorbereitungen
der Collection an (`prereq`, `raspberrypi` — letztere setzt die
cgroup-Parameter in `cmdline.txt`), legt das kube-vip-Manifest ab und
installiert Server und Agents.

Die VIP muss stehen, bevor der zweite Server beitritt. Deshalb landet das
kube-vip-Manifest **vor** dem Start von k3s unter
`/var/lib/rancher/k3s/server/manifests/` — k3s rollt dieses Verzeichnis beim
Start selbsttätig aus.

### Abnahme

```bash
ansible-playbook playbooks/site.yml
```

Der zweite Lauf muss `changed=0` melden. Tut er das nicht, ist eine Aufgabe
nicht idempotent und gehört korrigiert.

```bash
export KUBECONFIG=~/.kube/config
kubectl get nodes -o wide          # 6 Nodes, alle Ready
kubectl -n kube-system get ds kube-vip-ds
ping 10.35.99.210
```

## 4. ArgoCD einrichten

```bash
argocd-autopilot repo bootstrap --app https://github.com/argoproj-labs/argocd-autopilot/manifests/ha
```

MetalLB muss laufen, bevor der Server über eine LoadBalancer-Adresse
erreichbar wird — der Pool ist `.230` – `.250`:

```bash
kubectl patch svc argocd-server -n argocd \
  --patch '{"spec":{"type":"LoadBalancer","loadBalancerIP":"10.35.99.230"}}'

kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo
```

## Betrieb

### Einen ausgefallenen Node ersetzen

Solange zwei der drei Server laufen, hält das etcd-Quorum und der Cluster
arbeitet weiter.

```bash
kubectl delete node kube-02
./scripts/flash-node.sh kube-02 /dev/disk6
ansible-playbook playbooks/bootstrap.yml --limit kube-02
ansible-playbook playbooks/site.yml --limit kube-02
```

Fallen zwei der drei Server aus, ist das Quorum verloren. Dann auf dem
verbliebenen Server `k3s server --cluster-reset` ausführen und die beiden
anderen anschließend wie oben neu aufnehmen.

### k3s anheben

`k3s_version` in `inventory/group_vars/all/main.yml` setzen, dann:

```bash
ansible-playbook playbooks/upgrade.yml
```

Die Nodes werden nacheinander gehoben, damit das Quorum erhalten bleibt.

### k3s entfernen

```bash
ansible-playbook playbooks/reset.yml
```

Longhorn-Daten unter `/var/lib/longhorn` bleiben erhalten und müssen bewusst
gelöscht werden.

### Die beiden reservierten Pi aufnehmen

Sind die Docker-Aufgaben auf `kube-07` und `kube-08` migriert, wandern die
beiden Hosts in `inventory/hosts.yml` aus `reserved` in die Gruppe `agent`.
Danach Schritt 1 bis 3 für sie durchlaufen.

## Probelauf ohne Änderungen

```bash
ansible-playbook playbooks/site.yml --check --diff
```

Zeigt, was ein Lauf verändern würde, ohne etwas anzufassen.
