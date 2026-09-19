# pangolin-gateway

Veröffentlicht HTTPRoutes als Pangolin-Ressourcen. Ersetzt damit schrittweise die
handgeschriebenen `public-resources` aus `pangolin/blueprints/homelab.yaml`.

Quelle: [p3l1/pangolin-gateway](https://github.com/p3l1/pangolin-gateway)

## Warum

Der Blueprint in `pangolin/blueprints/homelab.yaml` ist additiv: Ein dort entfernter
Eintrag verschwindet nicht aus Pangolin, sondern bleibt bestehen, bis jemand ihn von Hand
löscht. Wildcards gibt es nur für Zertifikate, jede Domain braucht also einen eigenen
Eintrag.

Der Controller schließt beides: Er übersetzt jede HTTPRoute, die auf die GatewayClass
`pangolin` zeigt, in eine Ressource — und löscht die, deren Route verschwunden ist.

## Zuständigkeit

Der Controller fasst **ausschließlich** Ressourcen mit dem Präfix `gw-` an. Alles andere in
`homelab.yaml` — die `private-resources`, ArgoCD, Umami, Tekton, PAC, Arcane, VersaTiles —
bleibt unberührt, auch während der Umstellung. Die Tekton-Pipeline aus `pangolin/tekton`
pflegt diese Einträge weiter wie bisher.

## Einmalige Einrichtung

Der Controller braucht einen Integration-API-Schlüssel in seinem eigenen Namensraum. Das
vorhandene `pangolin-credentials` liegt in `tekton-pipelines` und gehört der Pipeline;
ein zweites Secret hält beide Nutzungen auseinander.

```bash
./scripts/secret.sh pangolin-gateway-credentials pangolin-gateway PANGOLIN_API_KEY
```

Der Schlüssel hat die Form `<key_id>.<key_secret>` und braucht **vier Aktionen**:

| Aktion | Wofür |
|---|---|
| `applyBlueprint` | die Ressourcen anlegen und aktualisieren |
| `listResources` | Waisen finden, die keine Route mehr haben |
| `deleteResource` | sie löschen |
| `listSites` | Site-Namen prüfen, bevor der Apply daran scheitert |

Fehlt eine, kommt für genau diesen Aufruf 401 oder 403 zurück — was wie ein falscher
Schlüssel aussieht. Ohne `listSites` arbeitet der Controller weiter, prüft dann aber keine
Site-Namen mehr.

Danach in `base/application.yaml` die beiden Platzhalter ersetzen:

- `PLATZHALTER_ENDPOINT` — die Integration-API **einschließlich Versionspfad**, also
  `…/v1` bzw. `…/api/v1`. Nicht die interne API: dann kommt jeder Aufruf als 401 zurück.
  Der Wert steht als `PANGOLIN_ENDPOINT` in `secrets/pangolin-credentials.sops.yaml`.
- `PLATZHALTER_ORG_ID` — dort als `PANGOLIN_ORG_ID`.

## Eine Anwendung umstellen

Die Reihenfolge ist wichtig. `full-domain` muss instanzweit eindeutig sein, und ein
fehlgeschlagener Apply betrifft **alle** Routen, nicht nur die neue.

1. **Route anlegen**, die auf `pangolin` zeigt — siehe
   `apps/rain-commute/base/httproute-pangolin.yaml` als Vorlage.
2. **Im Trockenlauf prüfen.** Solange `dryRun: true` gesetzt ist, protokolliert der
   Controller jeden Schreibvorgang und führt keinen aus:
   ```bash
   kubectl -n pangolin-gateway logs -l app.kubernetes.io/name=pangolin-gateway | grep "dry run"
   ```
   Dort muss der erwartete Schlüssel auftauchen, und der Status an der Route muss
   `Accepted=True` mit Reason `DryRun` tragen.
3. **Alte Ressource in Pangolin von Hand löschen.** Das ist der Schritt, den nichts
   automatisieren kann: Der Blueprint löscht nicht, und der Controller fasst nur `gw-`
   an. Solange die alte Ressource die Domain hält, scheitert jeder Apply.
4. **Eintrag aus `pangolin/blueprints/homelab.yaml` entfernen**, sonst legt die
   Tekton-Pipeline ihn beim nächsten Lauf wieder an.
5. **`dryRun: false`** setzen und den Status an der Route prüfen.

Schritt 3 und 4 gehören zusammen und müssen vor Schritt 5 erledigt sein.

## Annotationen

Alle optional, alle an der HTTPRoute:

| Annotation | Vorgabe | Wirkung |
|---|---|---|
| `pangolin.p3l1.de/display-name` | `<namespace>/<name>` | Name im Pangolin-Dashboard |
| `pangolin.p3l1.de/sso` | `"true"` | SSO davor. Wer sie vergisst, veröffentlicht nicht versehentlich offen. |
| `pangolin.p3l1.de/site` | `--default-site` | Ziel-Site, als niceId |
| `pangolin.p3l1.de/healthcheck-path` | *(keine)* | schaltet die Prüfung ein, z. B. `/healthz` |
| `pangolin.p3l1.de/healthcheck-interval` | `"30"` | Sekunden |
| `pangolin.p3l1.de/healthcheck-timeout` | `"5"` | Sekunden |

Hostname und Port der Prüfung erbt der Controller vom Ziel — eine Prüfung gegen eine
andere Adresse beschriebe das Ziel nicht.

## Grenzen von v0.3

Eine Route wird nur veröffentlicht, wenn sie genau einen Hostnamen, eine Regel, einen
`backendRef` auf einen Service im eigenen Namensraum und keine Filter hat. Alles andere
meldet der Controller an der Route mit `Accepted: False` und einem Grund, statt es still
als etwas anderes zu veröffentlichen.

Nicht abgedeckt: TCPRoute, TLSRoute, `private-resources`, Policies, mehrere Hostnamen je
Route, namensraumübergreifende Backends über ReferenceGrant.

**Die `private-resources` bleiben damit auf absehbare Zeit im handgeschriebenen
Blueprint** — Paperless MCP, Home Assistant und der Tekton-Webhook sind keine
`public-resources` und haben in der Gateway API kein Gegenstück.

## Ziele und Newt

Der Controller bildet den `backendRef` direkt auf
`<service>.<namespace>.svc.cluster.local` ab, nicht auf die ExternalName-Dienste aus
`apps/newt/config/services`. Newt löst beides im Cluster auf, das Ergebnis ist dasselbe —
die ExternalName-Dienste werden für umgestellte Routen also nicht mehr gebraucht.
