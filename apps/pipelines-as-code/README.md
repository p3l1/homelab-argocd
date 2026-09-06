# Pipelines-as-Code

Führt Pipelines aus, die im jeweiligen Repository unter `.tekton/` liegen —
ausgelöst durch Pushes und Pull Requests, mit Statusrückmeldung an GitHub.
Das Tekton-Gegenstück zu Woodpecker CI.

Gilt für **alle** Repositories, in denen die GitHub App installiert ist.

## Warum der Webhook öffentlich ist

GitHub stellt Events unaufgefordert zu und kann keinen Tunnel aufbauen. Der
Controller ist daher als öffentliche Pangolin-Ressource unter
`pac.cloud.p3l1.de` erreichbar, ohne SSO — eine Anmeldeseite würde GitHub nur
abweisen.

Abgesichert ist er anders: GitHub unterschreibt jeden Aufruf per HMAC mit dem
Webhook-Geheimnis, und der Controller weist alles zurück, was nicht passt.
Zusätzlich prüft er, ob das Repository überhaupt bei ihm bekannt ist.

Das unterscheidet ihn vom Tekton-Webhook in `pangolin/tekton`, der privat
bleibt: Dort baut die GitHub Action den Tunnel selbst auf.

## Einrichten

### 1. GitHub App anlegen

```bash
kubectl -n pipelines-as-code exec deployment/pipelines-as-code-controller -- \
  /usr/bin/pipelines-as-code-controller --help
```

Einfacher über `tkn pac`:

```bash
brew install tektoncd/tools/tektoncd-cli
tkn pac bootstrap github-app
```

Der Assistent legt die App an und fragt nach der Webhook-Adresse — dort
`https://pac.cloud.p3l1.de` eintragen.

### 2. Zugangsdaten hinterlegen

Die App liefert `App ID`, `Private Key` und `Webhook Secret`:

```bash
kubectl -n pipelines-as-code create secret generic pipelines-as-code-secret \
  --from-literal=github-application-id=<App-ID> \
  --from-literal=webhook.secret=<Webhook-Secret> \
  --from-file=github-private-key=<pfad-zur-pem-datei>
```

### 3. Repository anmelden

Je Repository ein `Repository`-Objekt im Cluster:

```yaml
apiVersion: pipelinesascode.tekton.dev/v1alpha1
kind: Repository
metadata:
  name: homelab-argocd
  namespace: pipelines-as-code
spec:
  url: https://github.com/p3l1/homelab-argocd
```

Danach greift jede Pipeline aus `.tekton/` dieses Repositories.
