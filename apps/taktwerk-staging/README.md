# Taktwerk Staging

Eine dauerhafte Taktwerk-Instanz mit dem Stand, der als Nächstes released wird,
unter `staging.taktwerk.cloud.p3l1.de`. Das Postfach liegt auf
`staging-mailpit.taktwerk.cloud.p3l1.de`.

Anders als eine Preview hängt sie an keiner Pull Request: Name und Namensraum
stehen fest, also überlebt die Datenbank jeden Release-Zyklus.

## Ablauf

1. Jeder Push auf `main` in `p3l1/taktwerk` lässt dort den Job `staging` laufen.
2. Der Job baut den `release-please`-Branch, solange dessen PR offen ist, sonst
   `main` — und legt Images und Chart unter `<version>-pre.<n>` in ghcr ab.
3. ArgoCD löst `targetRevision: ">=0.1.0-0"` neu auf und zieht die höchste
   Chart-Version.

Es gibt keinen Schalter und kein Label. Die Instanz ist immer da.

## Warum ein Semver-Range und kein fester Wert

Die Version steht erst zur Buildzeit fest, und diese Datei soll sie nicht
kennen müssen. Der Range nimmt die höchste passende Chart-Version; der
Image-Tag reist als `appVersion` **im Chart** mit, statt hier zu stehen.

Dass das trägt, liegt an der Ordnung der Versionen — jeder Staging-Chart
gehört zur *nächsten* Version und liegt damit über dem letzten Release:

```
0.33.0-pre.2 < 0.33.0-pre.3 < 0.33.0 < 0.33.1-pre.0 < 0.34.0-pre.3 < 0.34.0
   RP-PR         RP-PR       Release    Lücke          RP-PR         Release
```

Die Preview-Charts heißen `0.0.0-pr<n>.<sha>` und fallen unter die Untergrenze
des Ranges.

## Scharfe Kante

Fällt der `staging`-Job aus, während ein Release-Chart schon liegt, nimmt ArgoCD
den Release-Chart. Dessen `appVersion` zeigt auf ein **amd64**-Image, der
Cluster ist arm64: die Pods laufen in einen Crashloop mit `exec format error`.
Laut und mit dem nächsten erfolgreichen Build von selbst behoben.

## Voraussetzungen

| | |
|---|---|
| `secrets/taktwerk-preview-secrets.sops.yaml` | `SECRET_KEY` und die Seed-Passwörter, geteilt mit den Previews |
| `secrets/ghcr-pull.sops.yaml` | Zugriff auf die privaten Images |
| `apps/preview-secrets` | kopiert beide in jeden Namensraum mit dem Label `p3l1.de/preview-secrets` |
| Pocket ID | deckt den Host über den Platzhalter `https://*.taktwerk.cloud.p3l1.de/oidc-client.json` ab |

## Das Präfix in `sentry.environment`

`preview-staging`, nicht `staging`. Die Anwendung schaltet das Panel mit den
Seed-Zugangsdaten daran frei — sie prüft den Teil vor dem Bindestrich. Ohne das
Präfix käme niemand ohne Kenntnis der Passwörter aus dem Secret hinein.
