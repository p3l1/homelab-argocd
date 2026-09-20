# Taktwerk Preview

Eine vollständige Taktwerk-Instanz je Pull Request mit dem Label `preview`,
erreichbar unter `pr-<n>.taktwerk.cloud.p3l1.de`.

## Ablauf

1. Das Label `preview` an einer PR in `p3l1/taktwerk` lässt dort die
   `Preview`-Aktion laufen: sie baut beide Images und eine Chart-Vorabversion
   `0.0.0-pr<n>.<sha7>` und legt alles in ghcr ab.
2. Der `pullRequest`-Generator sieht die PR binnen 120 Sekunden und erzeugt die
   Application `taktwerk-pr-<n>`.
3. Das Chart bringt Namensraum, CloudNativePG-Datenbank, Anwendung, Scheduler,
   Postfach und zwei HTTPRoutes mit.
4. `pangolin-gateway` veröffentlicht die Routen, der Benachrichtigungsdienst
   kommentiert die Adresse an die PR.

Label entfernt oder PR geschlossen: ArgoCD löscht die Application, mit ihr den
Namensraum samt Datenträgern, und die Aktion `Preview cleanup` räumt ghcr.

## Warum der Commit im Chart-Namen steht

`targetRevision` und `image.tag` tragen beide den Commit. Jeder Push erzeugt so
eine neue Spezifikation und löst den Redeploy aus, ohne dass irgendwo ein
veränderliches Tag verfolgt werden müsste. Die Vorabversion des Charts sorgt
zugleich dafür, dass eine PR **ihre eigenen** Chart-Änderungen erprobt und nicht
die zuletzt veröffentlichte Fassung.

Bis die Aktion beides gepusht hat, findet ArgoCD die Chart-Version nicht und
meldet einen ComparisonError — das `retry`-Backoff im Template fängt das Fenster
ab.

## Voraussetzungen

| | |
|---|---|
| `secrets/taktwerk-github-app.sops.yaml` | GitHub-App, aus der der Generator die PRs liest |
| `secrets/argocd-notifications.sops.yaml` | dieselbe App für den Kommentar |
| `secrets/taktwerk-preview-secrets.sops.yaml` | `SECRET_KEY` und Freunde, geteilt über alle Previews |
| `secrets/ghcr-pull.sops.yaml` | Zugriff auf die privaten Images |
| `apps/preview-secrets` | verteilt die letzten beiden in die Namensräume |

Secrets werden von Hand angewandt, nicht von ArgoCD.

## Anmeldung

Die Instanzen stehen **offen im Netz** — kein SSO davor. Angemeldet wird in der
Anwendung selbst, über Pocket ID: Entra bürgt nur für den Tenant des Chors, die
Konten dieses Homelabs liegen in Pocket ID.

**Registriert wird nichts.** Jede Instanz liefert unter ihrer eigenen Adresse ein
Client-ID-Metadaten-Dokument aus, das Pocket ID beim ersten Anmelden holt:

```
https://pr-<n>.taktwerk.cloud.p3l1.de/oidc-client.json
```

Erlaubt ist das über einen Platzhalter in Pocket IDs Einstellungen unter
*OIDC → Metadaten-Dokumente zur Kunden-ID*:

```
https://*.taktwerk.cloud.p3l1.de/oidc-client.json
```

Der einfache Platzhalter ersetzt genau ein Namenssegment — jede PR-Nummer, aber
kein zweiter Punkt. Ein Secret gibt es nicht: solche Clients sind öffentlich,
und an die Stelle des Secrets tritt PKCE.

`seed.adminEmail` muss die Adresse sein, für die Pocket ID bürgt. Trifft sie
nicht, legt die erste Anmeldung einen frischen Benutzer ohne Rechte an, statt
auf dem vorangelegten Superuser zu landen.

Die Passwortanmeldung schaltet sich dabei von selbst ab: Taktwerk lässt sie nur
zu, solange kein Anmeldedienst konfiguriert ist. Eine offene Instanz bietet also
Pocket ID und sonst nichts.

## Kosten im Blick behalten

Jede Instanz belegt eine Datenbank mit eigenem Datenträger, drei Deployments und
zwei Pangolin-Ressourcen. Wie viele parallel laufen, steuert allein das Label.
