# Ansible

Provisionierung der Cluster-Nodes. Anleitung im Runbook
[`../docs/cluster-rebuild.md`](../docs/cluster-rebuild.md), Entwurfsentscheidungen
in [`../docs/superpowers/specs/2026-09-05-cluster-rebuild-design.md`](../docs/superpowers/specs/2026-09-05-cluster-rebuild-design.md).

## Playbooks

| Playbook | Zweck |
|---|---|
| `bootstrap.yml` | Erstkontakt als `pi` mit Passwort, setzt Hostname und feste Adresse |
| `site.yml` | Vollständige Konvergenz: Nodes, kube-vip, k3s |
| `upgrade.yml` | Hebt k3s auf die Version aus `group_vars` |
| `reset.yml` | Entfernt k3s wieder |
| `arcane-agent.yml` | Arcane-Agent auf den Docker-Hosts ausserhalb des Clusters |

## Inventories

| Datei | Zweck |
|---|---|
| `inventory/hosts.yml` | Regulärer Betrieb, Nodes unter ihren festen Adressen |
| `inventory/bootstrap.yml` | Erstkontakt, solange die Nodes noch am DHCP hängen |
| `inventory/docker-hosts.yml` | Docker-Hosts ausserhalb des Clusters, Anmeldung als `root` |

## Skripte

| Skript | Zweck |
|---|---|
| `flash-node.sh` | SSD beschreiben, prüfen und Erstkonfiguration ablegen |
| `identify-nodes.sh` | Modell, MAC und Seriennummer frisch gestarteter Pis |
| `bootstrap-node.sh` | Erstkontakt für einen, mehrere oder `all` Nodes; wählt Inventory und Flags selbst (`--dry-run` zeigt nur, was liefe) |
| `led.sh` | Rack-LED eines Nodes schalten, um ihn im Rack zu finden |
| `cluster-status.sh` | Nodes, Pods, kube-vip und API-VIP auf einen Blick |

## Rollen

| Rolle | Zweck |
|---|---|
| `node_base` | Pakete, feste Adresse, Swap aus, SSH-Härtung |
| `kube_vip` | Manifest der schwebenden API-Adresse, vor dem k3s-Start |
| `arcane_agent` | Arcane-Edge-Agent als Docker-Compose-Projekt in `/opt/arcane` |

k3s selbst installiert die Collection `k3s.orchestration` aus
[k3s-io/k3s-ansible](https://github.com/k3s-io/k3s-ansible); von dort stammen
auch `prereq` und `raspberrypi`.

## Secrets

Der k3s-Token liegt SOPS-verschlüsselt in
`inventory/group_vars/all/secrets.sops.yml`. `community.sops` lädt ihn als
Vars-Plugin, die Playbooks kennen die Entschlüsselung also nicht.

```bash
sops inventory/group_vars/all/secrets.sops.yml    # bearbeiten
```

## Arcane-Agent

Der Agent läuft im **Edge**-Betrieb: er wählt nach außen zum Manager, der
Host braucht keinen offenen Port. Sein Token gehört zu genau einem
Environment und wird vom Manager erzeugt — das Environment muss also
**vorher** bestehen:

```bash
ansible-playbook -i inventory/docker-hosts.yml playbooks/arcane-agent.yml \
  -e arcane_agent_token=arc_...
```

Dauerhaft gehört das Token nach
`inventory/group_vars/docker_hosts/secrets.sops.yml`, von wo `community.sops`
es als Vars-Plugin lädt — so wie der k3s-Token unter `all`. Je Host gilt
`host_vars/<name>/secrets.sops.yml`.

Auf dem Host landet es als Docker-Secret in `/opt/arcane/agent-token`, nicht
als Umgebungsvariable: Arcane zeigt die Umgebung der Container, die es
verwaltet, in der Oberfläche an — und der Agent verwaltet sich selbst mit.

`EDGE_TRANSPORT` bleibt auf `poll`. `auto` hält einen gRPC-Tunnel offen und
verlangt dafür im Reverse Proxy einen h2c-Router auf `/api/tunnel/connect`
und einen Read-Timeout von `0s`. Im Poll-Betrieb meldet der Manager das
Environment als **Standby**, solange nichts abgefragt wird; das ist der
gesunde Zustand.

Ein `401 Unauthorized` in `docker logs arcane-edge-agent` heißt, dass der
Manager das Token nicht kennt — das Environment fehlt oder sein Token wurde
neu erzeugt. Die Rolle prüft genau darauf und bricht ab.

## sudo ohne Passwort

`node_base` richtet `pam_ssh_agent_auth` ein, `sudo` nimmt damit den
weitergereichten YubiKey. Ansibles `become` ruft aber `sudo -n` auf, und `-n`
bricht ab, bevor PAM läuft:

```bash
ANSIBLE_BECOME_FLAGS='-H -S' ansible-playbook playbooks/site.yml
```

Zum Prüfen von Hand `sudo -K; sudo -H -S true < /dev/null` — ohne `-K` meldet
der globale Zeitstempel aus `/etc/sudoers.d/010_global-tty` auch dann Erfolg,
wenn die Agent-Anmeldung gar nicht greift.

## Prüfen

```bash
yamllint . && ansible-lint
ansible-playbook playbooks/site.yml --check --diff
```

`--check` scheitert in `network.yml` an „Fail if the profile did not take": die
vorangehende `command`-Aufgabe wird im Check-Modus übersprungen, die Variable
bleibt leer. Kein echter Fehler.
