# kubectl-Anmeldung über Pocket ID

Beide Cluster — `homelab` (k3s) und `homelab-monitoring` (Talos) — nehmen
ID-Token von Pocket ID unter `https://id.cloud.p3l1.de` an. Die
Client-Zertifikate aus `k3s.yaml` bzw. der Talos-kubeconfig bleiben
daneben gültig; OIDC ist ein zweiter Weg, kein Ersatz.

## Pocket ID

| Objekt | Wert |
|---|---|
| Gruppe | `kubernetes_admins` („Kubernetes Administratoren") |
| Gruppe | `kubernetes_read_only` („Kubernetes Read Only") |
| Client `homelab` | „Kubernetes Homelab", `e0524f83-fe1f-41d7-8403-31e611458c56` |
| Client `homelab-monitoring` | „Kubernetes Monitoring", `07e030b4-1ec1-4bad-a167-abb6b0e892c8` |

Beide Clients sind **öffentlich mit PKCE** — kubelogin trägt kein Geheimnis
auf dem Mac. Als Callback stehen `http://localhost:8000` und
`http://localhost:18000` eingetragen, die beiden Ports von kubelogin. Beide
Clients lassen nur die beiden Gruppen oben zu; wer in keiner ist, bekommt
schon von Pocket ID kein Token.

Je Cluster ein eigener Client: Das `aud` eines Token ist die Client-ID, ein
Token für den einen Cluster taugt also nicht für den anderen.

## Apiserver

Gleiche sechs Flags in beiden Clustern, nur die Client-ID unterscheidet sich:

```
oidc-issuer-url=https://id.cloud.p3l1.de
oidc-client-id=<Client-ID des Clusters>
oidc-username-claim=preferred_username
oidc-username-prefix=oidc:
oidc-groups-claim=groups
oidc-groups-prefix=oidc:
```

Der Benutzer `p3l1` erscheint im Cluster damit als `oidc:p3l1`, seine Gruppe
als `oidc:kubernetes_admins`. Ohne die Präfixe könnten OIDC-Namen bestehende
Konten und Gruppen überdecken.

| Cluster | Ablage | Anwenden |
|---|---|---|
| `homelab` | `ansible/inventory/group_vars/all/main.yml`, Schlüssel `server_config_yaml` | `ansible-playbook playbooks/site.yml --limit server --ask-become-pass` |
| `homelab-monitoring` | `talos/patches/oidc.yaml` im Repo `homelab-monitoring` | `talosctl patch machineconfig --nodes <ip> --patch @talos/patches/oidc.yaml` |

Der k3s-Lauf startet k3s auf den drei Servern neu, der Talos-Patch den
Apiserver-Static-Pod — in beiden Fällen ist die API kurz weg.

`--ask-become-pass` ist einmalig nötig: kube-01 bis kube-03 fehlt der
`pam_ssh_agent_auth`-Eintrag, den `node_base` im selben Lauf nachzieht.
Danach genügt der YubiKey am weitergereichten Agent.

## Rechte

`bootstrap/cluster-resources/in-cluster/rbac-oidc.yaml` bindet
`oidc:kubernetes_admins` an `cluster-admin` und `oidc:kubernetes_read_only`
an `view`. Die Datei liegt in beiden Repos und wird von der
ArgoCD-Application `cluster-resources-in-cluster` ausgerollt.

Prüfen, ohne sich anzumelden:

```bash
kubectl auth can-i --as=oidc:p3l1 --as-group=oidc:kubernetes_admins get nodes
kubectl auth can-i --as=oidc:x --as-group=oidc:kubernetes_read_only get secrets
```

## Mac

`kubelogin-oidc` steckt in `hosts/private/default.nix` des Repos `nix` und
liefert `kubectl-oidc_login`. Nach `darwin-rebuild switch` stehen die
Kontexte bereit:

```bash
kubectl --context oidc@homelab get nodes
kubectl --context oidc@homelab-monitoring get nodes
```

Der erste Aufruf öffnet den Browser, danach liegt das Token unter
`~/.kube/cache/oidc-login/`. Läuft es ab, holt kubelogin über den
Refresh-Token stillschweigend ein neues.

Die Exec-Argumente der beiden Benutzer stehen in der kubeconfig und tragen
`--oidc-pkce-method=S256`. Das ältere `--oidc-use-pkce` tut es auch, warnt
aber bei jedem Aufruf.

Geprüft am 2026-10-01 gegen `homelab-monitoring`: `kubectl auth whoami`
meldet `oidc:p3l1` mit `oidc:kubernetes_admins`.

## Fallstricke

- Der Apiserver holt den JWKS-Satz selbst von `id.cloud.p3l1.de`. Steht
  Pangolin, scheitert die Anmeldung — die Client-Zertifikate bleiben der
  Weg zurück in den Cluster.
- kubelogin bindet standardmäßig `127.0.0.1:8000` und fällt auf `:18000`
  zurück. Beide sind als Callback eingetragen; ein drittes Programm auf
  beiden Ports bringt `redirect_uri is not registered`.
- Nach einer Gruppenänderung in Pocket ID erst den Token-Cache leeren,
  sonst wirkt sie bis zum Ablauf nicht: `rm -rf ~/.kube/cache/oidc-login`.
