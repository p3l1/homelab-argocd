# homelab-argocd

Quelle der Wahrheit für mein Homelab: die Cluster-Provisionierung der
Raspberry-Pi-Nodes und die per ArgoCD ausgerollten Anwendungen.

## Aufbau

```
ansible/    Provisionierung der Nodes und Installation von k3s
apps/       Anwendungen als Kustomize-Overlays
bootstrap/  ArgoCD-Bootstrap
projects/   ArgoCD-Projekte
docs/       Runbooks und Entwurfsdokumente
```

## Cluster

Sechs Raspberry Pi mit Raspberry Pi OS Lite arm64 und k3s: drei Server mit
embedded etcd, drei Agents. Die API liegt unter der schwebenden Adresse
`10.35.99.110`. Zwei weitere Pi sind reserviert.

Der vollständige Weg von der leeren SSD bis zum laufenden ArgoCD steht im
Runbook [`docs/cluster-rebuild.md`](docs/cluster-rebuild.md).

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml -p ./.collections
./scripts/flash-node.sh kube-01 /dev/disk6      # SSD beschreiben
ansible-playbook playbooks/bootstrap.yml --limit kube-01
ansible-playbook playbooks/site.yml
```

Jeder Lauf ist wiederholbar — der zweite meldet `changed=0`.

## Anwendungen

Verwaltet mit `argocd-autopilot`. Details in [`apps/README.md`](apps/README.md).
