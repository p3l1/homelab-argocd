# Tekton

## Ablauf

```
Push nach main (pangolin/blueprints/**)
  └─ GitHub Action baut mit dem Machine Client einen Tunnel zu Pangolin auf
     └─ ruft die private Ressource unter tekton.homelab.private:8080
        └─ EventListener prüft die HMAC-Signatur
           └─ erzeugt einen PipelineRun
              └─ wendet die Blueprints an
```

Der Webhook ist **keine öffentliche Ressource**: Er ist nur über einen
Pangolin-Client erreichbar. Zusätzlich prüft der GitHub-Interceptor eine
HMAC-Signatur — Erreichbarkeit allein genügt also nicht.

## Benötigte GitHub-Secrets

| Secret | Herkunft |
|---|---|
| `PANGOLIN_OLM_ID` | Client-ID des Machine Client `homelab-argocd CI` |
| `PANGOLIN_OLM_SECRET` | zugehöriges Geheimnis |
| `PANGOLIN_ENDPOINT` | `https://cloud.p3l1.de` |
| `TEKTON_WEBHOOK_SECRET` | gemeinsames Geheimnis mit dem EventListener |

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
