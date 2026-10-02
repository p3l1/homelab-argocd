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
| `pangolin-client.yml` | Pangolin-Maschinen-Client, Voraussetzung für `arcane-agent.yml` |

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
| `pangolin_client` | Pangolin-CLI als `pangolin-client.service`, verbindet den Host mit dem Tunnel |

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

Der Agent läuft im **Edge**-Betrieb: er wählt nach außen zum Manager, der Host
braucht keinen offenen Port.

Er erreicht den Manager **nicht** über `arcane.cloud.p3l1.de`. Diese Route
liegt hinter Pangolins SSO — der Controller schaltet es per Vorgabe ein — und
ein Agent hat keine Pangolin-Sitzung. Jeder Pfad dort, die Anmeldeseite
eingeschlossen, antwortet mit `401`.

Stattdessen über die `private-resource` `arcane-manager` aus
[`../pangolin/blueprints/homelab.yaml`](../pangolin/blueprints/homelab.yaml),
erreichbar nur mit aktivem Pangolin-Client. Die Reihenfolge:

1. **Maschinen-Client** im Pangolin-Dashboard anlegen und seine `niceId` in
   die `machines`-Liste von `arcane-manager` eintragen. Ohne Eintrag haben
   nur Admins Zugriff.
2. **Blueprint anwenden** über die Tekton-Pipeline, siehe
   [`../pangolin/README.md`](../pangolin/README.md).
3. **Client verbinden:**
   ```bash
   ansible-playbook -i inventory/docker-hosts.yml playbooks/pangolin-client.yml \
     -e pangolin_client_id=... -e pangolin_client_secret=...
   ```
4. **Tunneladresse der Ressource ablesen** — `pangolin list aliases` auf dem
   Host. `pangolin_client` biegt den Resolver des Hosts bewusst **nicht** um:
   dort laufen Pangolin, Traefik und Pocket ID, und eine übernommene
   DNS-Konfiguration träfe sie mit.
5. **Agent ausrollen:**
   ```bash
   ansible-playbook -i inventory/docker-hosts.yml playbooks/arcane-agent.yml \
     -e arcane_agent_token=arc_... \
     -e '{"arcane_agent_extra_hosts":{"arcane-manager.homelab.internal":"<Adresse>"}}'
   ```

Das Agent-Token gehört zu genau einem Environment und wird vom Manager
erzeugt — das Environment muss also **vorher** bestehen. Dauerhaft gehören
Token und Client-Zugangsdaten nach
`inventory/group_vars/docker_hosts/secrets.sops.yml`, von wo `community.sops`
sie als Vars-Plugin lädt, so wie der k3s-Token unter `all`.

Auf dem Host landet das Token als Docker-Secret in `/opt/arcane/agent-token`,
nicht als Umgebungsvariable: Arcane zeigt die Umgebung der Container, die es
verwaltet, in der Oberfläche an — und der Agent verwaltet sich selbst mit.

`EDGE_TRANSPORT` bleibt auf `poll`. `auto` hält einen gRPC-Tunnel offen und
verlangt dafür im Reverse Proxy einen h2c-Router auf `/api/tunnel/connect`
und einen Read-Timeout von `0s`. Im Poll-Betrieb meldet der Manager das
Environment als **Standby**, solange nichts abgefragt wird; das ist der
gesunde Zustand.

Ein `401 Unauthorized` in `docker logs arcane-edge-agent` heißt, dass der
Manager das Token nicht kennt — oder dass die Anfrage bei Pangolins SSO
hängt statt beim Manager anzukommen. Die Rolle prüft darauf und bricht ab.

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

Ebenso scheitert `--check` in `pangolin-client.yml` an „Destination
/usr/local/lib/pangolin does not exist": im Check-Modus entsteht das
Verzeichnis nicht, das der Download braucht. Auch kein echter Fehler.
