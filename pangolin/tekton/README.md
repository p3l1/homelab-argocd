# Tekton

## Ablauf

```
Push nach main (pangolin/blueprints/**)
  └─ GitHub stellt das Ereignis an pac.cloud.p3l1.de zu
     └─ Pipelines-as-Code prüft Signatur und Repository
        └─ liest .tekton/pangolin-blueprints.yaml
           └─ erzeugt einen PipelineRun und meldet den Status zurück
```

Der frühere Weg über eine GitHub Action und den Machine Client ist damit
abgelöst. Der EventListener und die private Ressource bleiben bestehen: Sie
erlauben es, die Pipeline von außerhalb GitHubs anzustoßen, ohne einen
öffentlichen Endpunkt zu benötigen.

Der Webhook ist **keine öffentliche Ressource**: Er ist nur über einen
Pangolin-Client erreichbar. Zusätzlich prüft der GitHub-Interceptor eine
HMAC-Signatur — Erreichbarkeit allein genügt also nicht.

## Benötigte GitHub-Secrets

| Secret | Herkunft |
|---|---|
| `PANGOLIN_CLIENT_ID` | Client-ID des Machine Client `homelab-argocd CI` |
| `PANGOLIN_CLIENT_SECRET` | zugehöriges Geheimnis |
| `TEKTON_WEBHOOK_SECRET` | gemeinsames Geheimnis mit dem EventListener |

Die Namensgebung folgt `p3l1/homelab-monitoring`, wo derselbe Aufbau bereits
im Einsatz ist.

## Warum der Container und nicht das Binary

Der Client läuft als `fosrl/pangolin-cli` im Docker-Container mit
`--network host`, `NET_ADMIN` und `/dev/net/tun`. `fosrl/olm` ist laut eigener
Beschreibung eine **interne Bibliothek** für Pangolin-Clients, kein Werkzeug
für diesen Zweck.

Entscheidend ist der Schritt danach: `--network host` teilt zwar den
Netzwerk-Namensraum, aber nicht `/etc`. Der Resolver, den der Container
einträgt, gilt deshalb nur dort — `curl` löst auf dem Host auf und braucht ihn
ebenfalls. Ohne diesen Schritt steht der Tunnel, der Alias löst aber nicht
auf.

## Cluster-Seite

```bash
kubectl apply -f pangolin/tekton/task.yaml \
              -f pangolin/tekton/pipeline.yaml \
              -f pangolin/tekton/eventlistener.yaml
```

Das Secret für die Signaturprüfung:

```bash
./scripts/secret.sh tekton-webhook-secret tekton-pipelines secret
```

Derselbe Wert gehört als `TEKTON_WEBHOOK_SECRET` zu den GitHub-Secrets.

## Von Hand auslösen

```bash
kubectl create -f pangolin/tekton/pipelinerun.yaml
```

Läufe und Protokolle zeigt das Tekton Dashboard unter
`https://tekton.homelab.internal`.
