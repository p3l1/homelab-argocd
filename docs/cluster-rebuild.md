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
**der Schreibvorgang löscht die SSD vollständig**. Danach liest es das
Geschriebene zurück und vergleicht es mit dem Abbild; erst dann legt es die
`custom.toml` mit Hostname, Benutzer, SSH-Schlüssel und Locale ab.

Die Rücklese-Prüfung kostet etwa eine Minute und deckt stille Schreibfehler
auf, die sich sonst erst beim nicht bootenden Pi zeigen. Mit `--no-verify`
lässt sie sich überspringen.

Zusätzlich trägt das Skript `init=/usr/lib/raspberrypi-sys-mods/firstboot` in
`cmdline.txt` ein. Ohne diesen Parameter wird `custom.toml` beim Start
kommentarlos ignoriert — der Pi kommt dann als `raspberrypi` ohne SSH hoch.
`firstboot` entfernt den Parameter selbst wieder, sobald es durchgelaufen
ist.

Hinterlegt werden alle öffentlichen Schlüssel aus `ansible/files/ssh/` —
derzeit ausschließlich der GPG-Authentication-Subkey des YubiKey. Die Rolle
`node_base` pflegt später dieselbe Liste, Quelle ist also beide Male dasselbe
Verzeichnis. Passwort-Anmeldung ist abgeschaltet.

Der Zugang hängt damit vollständig am YubiKey: Ohne gesteckten Token gibt es
keinen Weg auf die Nodes — weder für dich noch für Ansible.

Ändern sich die Schlüssel, muss eine bereits geflashte SSD nicht neu
beschrieben werden:

```bash
./scripts/flash-node.sh --config-only kube-01 /dev/disk4
```

Das schreibt nur die `custom.toml` neu und lässt das Abbild unberührt.

Das richtige Gerät findest du mit `diskutil list` — interne Datenträger lehnt
das Skript ab.

## 2. Node in Betrieb nehmen

SSD in den Pi, einschalten, etwa eine Minute warten. Der Pi hängt danach an
einer DHCP-Adresse und heißt noch `raspberrypi`.

### Welches Gerät wird welcher Node?

Die Server gehören auf die Raspberry Pi 4, die Agents auf die stärkeren Pi 5.
Welches Gerät welches Modell ist, verrät:

```bash
./scripts/identify-nodes.sh 10.35.99.11 10.35.99.20 10.35.99.30
```

Die Adressen findest du in der DHCP-Liste des Routers. Trage sie anschließend
in `inventory/bootstrap.yml` ein — dort steht je Node, über welche Adresse
verbunden wird (`ansible_host`) und welche er dauerhaft bekommt
(`node_address`).

Die Belegung am USW Flex 2.5G 8 PoE:

| Port | Node | Modell |
|---|---|---|
| 1 | `kube-05` | Pi 5 |
| 2 | `kube-06` | Pi 5 |
| 3, 4 | Docker-Hosts, nicht im Cluster | Pi 5 |
| 5 | `kube-01` | Pi 4 |
| 6 | `kube-03` | Pi 4 |
| 7 | `kube-02` | Pi 4 |
| 8 | `kube-04` | Pi 4 |

### Erstkontakt

```bash
ansible-playbook -i inventory/bootstrap.yml playbooks/bootstrap.yml --ask-pass
```

Das Playbook meldet sich als `pi` mit Passwort an, setzt Hostname und
Zeitzone, installiert die Pakete, hinterlegt den YubiKey, schaltet Swap und
Passwort-Anmeldung ab und schreibt die feste Adresse fest. Beim
Adresswechsel startet der Node neu; Ansible folgt ihm dabei auf die neue
Adresse.

`sudo` verlangt auf den Pis ein Passwort, also zusätzlich
`--ask-become-pass` angeben.

### sudo über den SSH-Agent statt Passwort

Optional kann `sudo` sich über den weitergereichten SSH-Agent
authentifizieren — dann genügt der gesteckte YubiKey und es braucht kein
Passwort mehr. Die Rolle bringt das mit, **standardmäßig abgeschaltet**.

Erst prüfen, was der aktuelle Stand ist:

```bash
ansible-playbook playbooks/check-sudo-agent.yml --limit kube-05 --ask-become-pass
```

Dann auf **einem** Node aktivieren und erneut prüfen:

```bash
ansible-playbook playbooks/bootstrap.yml --limit kube-05 \
  --ask-become-pass -e node_sudo_via_ssh_agent=true
ansible-playbook playbooks/check-sudo-agent.yml --limit kube-05
```

Erst wenn das sauber durchläuft, die Einstellung dauerhaft in
`inventory/group_vars/all/main.yml` setzen.

Zwei Vorkehrungen sind eingebaut: Der PAM-Eintrag ist `sufficient`, nicht
`required` — scheitert die Agent-Prüfung, fragt PAM wie bisher nach dem
Passwort. Und schlägt die Änderung fehl, stellt ein `rescue`-Block die
gesicherte `/etc/pam.d/sudo` wieder her.

Die akzeptierten Schlüssel liegen in `/etc/security/sudo_authorized_keys` und
gehören root. Unter `~/.ssh/authorized_keys` könnte sich sonst jeder, der
Zugriff auf das Konto hat, selbst `sudo`-Rechte eintragen.

Ab hier ist Passwort-Anmeldung abgeschaltet und der YubiKey der einzige Weg
hinein — alle weiteren Läufe kommen ohne `--ask-pass` aus und nutzen das
reguläre Inventory.

Vor jeder Änderung prüft das Playbook, ob der antwortende Host wirklich der
gemeinte ist — so lässt sich nicht versehentlich ein laufender Node
überschreiben.

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
