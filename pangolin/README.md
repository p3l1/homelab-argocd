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

## Sites in dieser Pangolin-Instanz

| Site (`niceId`) | Name | Zweck |
|---|---|---|
| `intent-anniella-pulchra` | Homelab Services | **dieser k3s-Cluster** |
| `sore-zebra-tailed-lizard` | Homelab Documents | Docker-Host mit Paperless, Home Assistant, Komodo |
| `weary-uperodon-taprobanicus` | Homelab Monitoring | der abgeschaltete Talos-Cluster |
| `selfish-gray-marmot` | cloud.p3l1.de | Pangolin selbst |

Die Blueprints hier fassen ausschließlich `intent-anniella-pulchra` an.

## Was beim Anwenden geschieht

Blueprints sind **additiv**, kein deklarativer Abgleich: Zu jedem Eintrag
sucht Pangolin über den Schlüssel — er entspricht dem `niceId` der API — eine
bestehende Ressource. Wird es fündig, aktualisiert es sie, sonst legt es an.
Ressourcen, die **nicht** in der Datei stehen, bleiben unberührt; es gibt
keine Prune-Logik.

Das gilt für den Weg über die CLI, den diese Pipeline nutzt. Zwei andere
Betriebsarten verhalten sich anders: Newt mit `--blueprint-file` und
Docker-Labels setzen die Datei **fortlaufend** durch und überschreiben dabei
Änderungen, die im Dashboard gemacht wurden. Wer den Newt in `apps/newt`
später um diesen Schalter ergänzt, ändert damit die Semantik.

Praktische Folge: Ein Eintrag, den man hier entfernt, verschwindet nicht aus
Pangolin — das muss im Dashboard geschehen.

## Paperless fehlt bewusst

Unter `documents.cloud.p3l1.de` läuft bereits eine Paperless-Instanz auf dem
Docker-Host. Der Cluster hat inzwischen eine eigene — beide gleichzeitig zu
veröffentlichen ergibt keinen Sinn. Umgestellt wird **nach der Migration der
Dokumente**; bis dahin bleibt Paperless aus dem Blueprint heraus.
