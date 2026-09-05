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

## Inventories

| Datei | Zweck |
|---|---|
| `inventory/hosts.yml` | Regulärer Betrieb, Nodes unter ihren festen Adressen |
| `inventory/bootstrap.yml` | Erstkontakt, solange die Nodes noch am DHCP hängen |

## Skripte

| Skript | Zweck |
|---|---|
| `flash-node.sh` | SSD beschreiben, prüfen und Erstkonfiguration ablegen |
| `identify-nodes.sh` | Modell, MAC und Seriennummer frisch gestarteter Pis |
| `bootstrap-node.sh` | Erstkontakt mit dem richtigen Inventory und den nötigen Flags |

## Rollen

| Rolle | Zweck |
|---|---|
| `node_base` | Pakete, feste Adresse, Swap aus, SSH-Härtung |
| `kube_vip` | Manifest der schwebenden API-Adresse, vor dem k3s-Start |

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

## Prüfen

```bash
yamllint . && ansible-lint
ansible-playbook playbooks/site.yml --check --diff
```
