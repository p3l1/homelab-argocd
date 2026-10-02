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

## Machine Client

Für dieses Repository existiert der Client **`homelab-argocd CI`**
(`fine-mastigoproctus-giganteus`, clientId 17). Er ist der privaten Ressource
`tekton-webhook` zugeordnet und damit der einzige Weg, den EventListener zu
erreichen — der Alias `tekton-webhook.homelab.internal` löst nur innerhalb des Tunnels
auf.

Angelegt wurde er über die API; `pick-client-defaults` liefert dafür
passende Werte. Die Zugangsdaten liegen als GitHub-Secrets
(`PANGOLIN_OLM_ID`, `PANGOLIN_OLM_SECRET`).

Ein **zweiter Client fehlt noch**: `cloud.p3l1.de` selbst braucht einen, damit
der Arcane-Edge-Agent dort die private Ressource `arcane-manager` erreicht. Die
öffentliche Route `arcane.cloud.p3l1.de` liegt hinter SSO, bei dem sich ein
Agent nicht anmelden kann. Seine `niceId` gehört in die `machines`-Liste von
`arcane-manager`, seine Zugangsdaten auf den Host — siehe die Rolle
`pangolin_client` in [`../ansible/README.md`](../ansible/README.md).

Auf dem Host läuft die **Pangolin-CLI**, nicht olm: olm ist laut eigenem
README abgekündigt und ausdrücklich nicht mehr für Maschinen-Clients gedacht.

### Clients entstehen nur über die API

Das Dashboard kann in dieser Instanz **keine** Maschinen-Clients anlegen.
`PUT /org/<org>/client` antwortet der angemeldeten Sitzung mit `403`, obwohl
der Benutzer `isOwner` und `isAdmin` ist: `checkUserActionPermission` liest
ausschließlich die Tabelle `roleActions` und kennt keine Owner-Ausnahme, und
dort fehlt die Zeile für `createClient`. Nachrüsten lässt sie sich nicht —
die Routen `/role/:roleId/action(s)` sind in Pangolin auskommentiert.

Der Weg ist die Integration-API, deren Prüfung über die Aktionen des
API-Schlüssels läuft statt über die Rolle. Der Schlüssel braucht dafür
zusätzlich `createClient`:

```bash
./scripts/pangolin-client.sh "cloud.p3l1.de Arcane Agent"
```

Das Skript holt über `pick-client-defaults` eine freie Adresse aus dem
Org-Netz samt `olmId` und `olmSecret`, legt den Client an (`type: olm`) und
gibt `niceId`, Client-ID und Secret aus. Das Secret zeigt Pangolin nur
einmal.

Nebenbei: Im Dashboard schickt der Knopf „Create Client" das Formular gar
nicht ab, die Eingabetaste im Namensfeld schon. Der `403` wird also erst
sichtbar, wenn man Enter drückt.

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
