# Pangolin

Welche Dienste durch den Tunnel erreichbar sind, steht in
[`blueprints/`](blueprints). Angewendet werden sie von einer Tekton-Pipeline,
**nicht** von ArgoCD — Pangolin läuft außerhalb des Clusters, seine
Ressourcen entstehen über die Integration API.

## Warum kein Operator

Es gibt keinen, der in diese Richtung arbeitet:

- `bovf/pangolin-operator` wäre der richtige Ansatz gewesen, ist aber
  **archiviert** und hatte nie ein Release.
- `fosrl/pangolin-kube-controller` ist offiziell und aktiv, läuft jedoch
  **umgekehrt**: Er liest Pangolins Konfiguration und erzeugt daraus
  Traefik-`IngressRoute`-Objekte im Cluster. Er definiert keine CRDs und legt
  keine Pangolin-Ressourcen an. Für dieses Setup zudem unpassend, weil hier
  die Gateway API verwendet wird.

Blueprints sind der Weg, den Fossorial für deklarative Verwaltung vorsieht.

## Einrichten

Zugangsdaten hinterlegen:

```bash
./scripts/secret.sh pangolin-credentials tekton-pipelines \
  PANGOLIN_ENDPOINT PANGOLIN_INTEGRATION_API_KEY PANGOLIN_ORG_ID
```

`PANGOLIN_ENDPOINT` ist die **Integration-API**-Adresse, nicht die des
Dashboards — bei einer selbst betriebenen Instanz typischerweise
`https://<host>/v1`.

Tekton-Objekte anlegen:

```bash
kubectl apply -f pangolin/tekton/task.yaml -f pangolin/tekton/pipeline.yaml
```

## Anwenden

```bash
kubectl create -f pangolin/tekton/pipelinerun.yaml
kubectl -n tekton-pipelines logs -l tekton.dev/pipeline=pangolin-blueprints -f
```

Die Pipeline holt das Repository, lädt die Pangolin-CLI passend zur
Architektur und wendet jede Datei aus `blueprints/` an. Die CLI kommt als
Binary statt als Image: `ghcr.io/fosrl/cli` steht bei `0.6.2`, während die
CLI selbst bei `0.16.0` ist und `apply blueprint` dort noch fehlt.

## Ziele der Ressourcen

Die Blueprints verweisen auf die `ExternalName`-Dienste aus
`apps/newt/config/services`. Damit steht je Anwendung ein Name, unabhängig
vom Namensraum, in dem sie läuft.
