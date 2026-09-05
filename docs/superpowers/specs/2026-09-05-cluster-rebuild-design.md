# Cluster-Neuaufbau: idempotente Node-Provisionierung

Datum: 2026-09-05
Status: freigegeben

## Ziel

Der k3s-Homelab-Cluster wird von Grund auf neu aufgebaut. Alle Nodes sind
ausgefallen. Das Ergebnis ist ein reproduzierbarer Weg von der leeren SSD bis
zum laufenden ArgoCD — wiederholbar für jeden einzelnen Node, ohne dass ein
zweiter Durchlauf etwas verändert.

## Ausgangslage

Bisher lebte die Cluster-Automatisierung in `p3l1/ansible-homelab-k3s`. Deren
Playbooks installieren k3s per `shell: curl … | sh` und tragen die Adresse des
ersten Servers hartkodiert im Task. Beides verhindert Idempotenz: Jeder Lauf
führt die Installation erneut aus, und ein Wechsel der Topologie erfordert
Änderungen am Code statt an Variablen.

Die Rolle `p3l1/ansible-role-ubuntu-base-config` ist auf Ubuntu mit netplan
ausgelegt und passt nicht auf Raspberry Pi OS, das NetworkManager verwendet.

## Entscheidungen

| Thema | Entscheidung |
|---|---|
| Ort | `homelab-argocd/ansible/`, analog zu `talos/` in `homelab-monitoring` |
| k3s-Installation | Collection `k3s.orchestration` (k3s-io/k3s-ansible) 1.2.2 |
| Topologie | 3 Server mit embedded etcd, 3 Agents, 2 Nodes reserviert |
| Erstkonfiguration | `custom.toml` auf der Boot-Partition, per Skript erzeugt |
| Secrets | SOPS mit PGP-Key `7954EC02CDDF896536DFDCDE056C6FDDF9E15CF2` |

Der Fork `p3l1/k3s-ansible` (von `timothystewart6`, 233 Commits im Rückstand)
wird nicht weiterverwendet. Die offizielle Collection deckt den Bedarf ab und
erscheint in Releases.

### Warum drei Server

Bei einem einzelnen Server legt k3s keine automatischen Backups an; nach einem
Ausfall ist die Control Plane ohne selbst gesichertes `state.db` verloren. Mit
drei Servern hält das etcd-Quorum den Ausfall eines Nodes aus, k3s schreibt
stündliche Snapshots, und der Ersatz eines Nodes ist ein Playbook-Lauf mit
`--limit`. Die zusätzliche Schreiblast ist auf SSDs unkritisch.

Die Control Plane liegt auf den Raspberry Pi 4: etcd braucht verlässliche I/O,
aber wenig Rechenleistung. Die stärkeren Pi 5 tragen die Workloads.

## Zielbild

```
ansible/
├── ansible.cfg
├── requirements.yml
├── inventory/
│   ├── hosts.yml
│   └── group_vars/all/
│       ├── main.yml
│       └── secrets.sops.yml
├── playbooks/
│   ├── bootstrap.yml
│   ├── site.yml
│   ├── reset.yml
│   └── upgrade.yml
├── roles/
│   ├── node_base/
│   └── kube_vip/
└── scripts/
    └── flash-node.sh
```

## Von der leeren SSD zum Node

`scripts/flash-node.sh <hostname> <device>` lädt das aktuelle Raspberry Pi OS
Lite arm64 (Trixie, Debian 13), prüft die SHA256-Summe, verlangt eine
ausdrückliche Bestätigung des Ziel-Device und schreibt das Image. Danach legt
es auf der Boot-Partition eine `custom.toml` ab: Hostname, Benutzer, dessen
SSH-Public-Key, aktivierter SSH-Dienst, deaktivierte Passwort-Anmeldung,
Locale und Zeitzone.

macOS kann die ext4-Root-Partition nicht schreiben, nur die FAT32-Boot-
Partition. Eine statische Adresse lässt sich deshalb nicht mitflashen. Der
Node startet per DHCP und erhält seine Adresse aus einer Reservierung im
Router; `bootstrap.yml` verbindet sich darüber und schreibt sie per `nmcli`
fest, sodass der Node danach nicht mehr vom DHCP abhängt.

Der Weg über mDNS (`<hostname>.local`) wäre ohne Reservierungen möglich,
verlangt aber, dass Namensauflösung im gesamten Netz zuverlässig funktioniert;
die Reservierung ist die verlässlichere Grundlage.

Das Skript ist wiederholbar: Ein erneuter Lauf über dieselbe SSD stellt den
Auslieferungszustand wieder her.

## Rolle `node_base`

Ersetzt `ansible-role-ubuntu-base-config` für Raspberry Pi OS Trixie:

- Pakete `open-iscsi`, `nfs-common`, `util-linux` — Voraussetzungen für
  Longhorn — sowie `curl`, `git`, `htop`, `jq`
- statische Adresse über ein NetworkManager-Verbindungsprofil
- Swap abgeschaltet und maskiert (`dphys-swapfile`), wie von Kubernetes verlangt
- SSH: `PasswordAuthentication no`, `PermitRootLogin prohibit-password`

Kein UFW. Die Regeln kollidieren mit denen von k3s; die Collection bringt für
diesen Zweck `manage_firewall` mit.

Die cgroup-Parameter in `cmdline.txt` setzt die Rolle nicht selbst — das
erledigt `raspberrypi` aus der Collection bereits idempotent, samt
Reboot-Handler.

## Rolle `kube_vip`

Die API erhält unter `10.35.99.210` eine schwebende Adresse. kube-vip läuft als
DaemonSet im Cluster, weshalb die Adresse noch nicht existiert, wenn der zweite
Server über sie beitreten will. Die Rolle legt das Manifest deshalb **vor dem
Start von k3s** unter `/var/lib/rancher/k3s/server/manifests/kube-vip.yaml` ab;
k3s rollt dieses Verzeichnis beim Start automatisch aus. Der erste Server
bringt die Adresse hoch, bevor die übrigen beitreten.

`k3s.orchestration` trägt die Adresse als `api_endpoint` in `tls-san` ein,
setzt `cluster-init` beim ersten Server und `server:` bei den weiteren.

## Adressplan in 10.35.99.0/24

Belegt und ausgespart: `.1` Gateway, `.100` Talos-Node des
Monitoring-Clusters, `.200` dessen Traefik-LoadBalancer.

| Zweck | Adresse | Hardware |
|---|---|---|
| API-VIP | `.110` | — |
| `kube-01` – `kube-03`, Server | `.211` – `.213` | 3× Pi 4 |
| `kube-04`, Agent | `.214` | 1× Pi 4 |
| `kube-05`, `kube-06`, Agent | `.215` – `.216` | 2× Pi 5 |
| `kube-07`, `kube-08`, reserviert | `.217` – `.218` | 2× Pi 5, derzeit Docker |
| MetalLB-Pool | `.230` – `.250` | — |

Die Server-Nodes tragen `CriticalAddonsOnly=true:NoExecute`, damit Workloads
auf den Agents landen.

## Secrets

`.sops.yaml` im Repo-Root, `encrypted_regex: ^(token)$`, PGP wie in
`ansible-homelab-k3s` und `homelab-monitoring`. Das Vars-Plugin aus
`community.sops` lädt `group_vars/all/secrets.sops.yml` transparent, sodass
Playbooks die Entschlüsselung nicht kennen müssen.

## Nachweis der Idempotenz

Molecule wäre für ein Homelab dieser Größe überdimensioniert. Stattdessen:

- `yamllint` und `ansible-lint` in der bestehenden Woodpecker-Pipeline
- `--check --diff` als Probelauf vor jeder Anwendung
- Abnahmekriterium beim Rollout: **der zweite Lauf von `site.yml` meldet
  `changed=0`**

## Abgrenzung

Nicht Teil dieses Vorhabens ist die Zentralisierung der Anwendungen — der
Umzug von `homelab-metallb`, `homelab-whoami` und den übrigen Repos in dieses
Repository, wie in `homelab-monitoring` geschehen. Das ist ein eigenes
Vorhaben mit eigener Spezifikation.

Der ArgoCD-Bootstrap gehört dagegen dazu, weil der Neuaufbau ohne ihn nicht
abgeschlossen ist: `argocd-autopilot` gegen den frischen Cluster und der
MetalLB-Pool auf `.230` – `.250`. Er wird als Kapitel des Runbooks
`docs/cluster-rebuild.md` festgehalten.
