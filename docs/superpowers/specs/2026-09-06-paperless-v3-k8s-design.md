# Paperless-ngx: Aufstieg auf v3 und Umzug in den Cluster

Datum: 2026-09-06
Status: freigegeben

## Ziel

Die Paperless-Installation läuft als Docker-Compose-Stack auf einem einzelnen
Host und steht auf Version 2.20.14. Am Ende dieses Vorhabens läuft sie als
Version 3.1.3 im k3s-Cluster, mit CloudNativePG als Datenbank, Longhorn als
Speicher und einer Sicherung, die sich selbst anlegt.

Gesichert wird zweimal: einmal vor dem Versionssprung, einmal danach. Die
zweite Sicherung ist zugleich das Umzugsgut.

## Ausgangslage

### Der Docker-Host

`10.35.99.168`, DietPi auf Debian 12. Der Stack stammt aus `p3l1/documents`
und wird von Komodo per GitHub-Webhook ausgerollt.

| Dienst | Fassung |
|---|---|
| paperless-ngx | 2.20.14 |
| PostgreSQL | 17 |
| Redis | 8 |
| Apache Tika | `latest`, ungepinnt |
| Gotenberg | 8.31 |

Die Daten liegen unter `/opt/paperless`: `data` 104 MB, `media` 928 MB,
`consume` leer. Erreichbar ist der Dienst von außen unter
`documents.cloud.p3l1.de` über einen Newt-Tunnel nach Pangolin, die Anmeldung
läuft über OIDC.

### Der Cluster

`apps/paperless-ngx` ist bereits vollständig ausgerollt und meldet
`Synced/Healthy`: CloudNativePG mit drei Instanzen, Valkey, Tika 3.3.1.0,
Gotenberg 8.31, vier Longhorn-PVCs, eine HTTPRoute auf
`paperless.homelab.internal` und ein `ExternalName` für Newt.

**Die Instanz ist leer — null Dokumente.** Es ist also keine Installation zu
bauen, sondern eine fertige, leere Hülle zu füllen.

### Die Sicherung, die es nicht gibt

`BACKUP.md` in `p3l1/documents` beschreibt eine Sicherung nach Scaleway S3.
Auf dem Host existiert dafür nichts: kein Cron-Eintrag, kein systemd-Timer,
weder `aws` noch `rclone`. Im Export-Verzeichnis liegt eine einzige Datei,
`export-2026-04-26.zip`, vier Monate alt.

Der GitHub-Workflow `backup-restore-test.yml` zieht wöchentlich ein
`latest-backup.zip` aus S3, das niemand dort ablegt. Er kann nie grün gewesen
sein. Zusätzlich steht dort `PAPERLESS_VERSION: "2.17.1"` fest verdrahtet.

## Entscheidungen

| Thema | Entscheidung |
|---|---|
| Zielversion | paperless-ngx 3.1.3 |
| Weg dorthin | 2.20.14 → 2.20.15 → 3.1.3, in dieser Reihenfolge |
| Umzugsverfahren | `document_exporter` / `document_importer` |
| Helm-Chart | `zekker6/paperless` 11.8.0 statt `gabe565` 0.24.1 |
| Datenbank | CloudNativePG, bestehender Cluster `paperless-db` |
| Suchindex | wird von Paperless selbst neu gebaut, kein Eingriff |
| Secret Key | SOPS-Secret, Wert aus der Compose-Installation übernommen |
| Erreichbarkeit | zunächst nur intern über `paperless.homelab.internal` |
| Docker-Stack | bleibt nach dem Umzug unangetastet stehen |
| Sicherung | CronJob im Cluster, Ziel Scaleway S3 |

### Warum der Umweg über 2.20.15

Der Migrationsleitfaden des Projekts lässt den Aufstieg auf v3 ausschließlich
von 2.20.15 aus zu. Ein Sprung von 2.20.14 direkt auf 3.1.3 ist nicht
vorgesehen. Der Zwischenschritt ist klein — zwischen den beiden Fassungen
liegt ein Wartungsrelease — aber er ist nicht verhandelbar.

### Warum Export und Import statt Dump und Kopie

Ein `pg_dump` samt kopierter Medienverzeichnisse wäre schneller. Der Export
prüft dafür beim Einlesen die Prüfsummen jedes Dokuments, baut Vorschaubilder
und Suchindex neu auf und ist gegen Versionsunterschiede unempfindlich. Vor
allem aber ist das Ergebnis dasselbe Artefakt, das ohnehin als Sicherung
gebraucht wird: Sicherung und Umzugsgut fallen zusammen, statt zweimal
erzeugt zu werden.

### Warum `zekker6` und nicht `wrenix`

Auf ArtifactHub firmiert das Chart von WrenIX unter dem Namen `paperless-ngx`
und wirkt dadurch wie die offizielle Wahl. Ein offizielles Chart gibt es
nicht; das Projekt veröffentlicht keines.

Das WrenIX-Chart ist mit ArgoCD unbrauchbar. Es liest `PAPERLESS_SECRET_KEY`
per `lookup` aus dem bereits bestehenden Secret und fällt auf
`randAlphaNum 64` zurück. ArgoCD rendert ohne Cluster-Zugriff, `lookup`
liefert dort nichts. Zwei Renderläufe hintereinander, gegen unsere Werte
geprüft:

```
Lauf 1: PAPERLESS_SECRET_KEY = crVgGdGULsAyz4YRVNoNgh4Z…
Lauf 2: PAPERLESS_SECRET_KEY = NXAq3J0peiTiGAxntFxUAkNo…
```

Bei jedem Sync ein anderer Schlüssel: die Application bliebe dauerhaft
`OutOfSync`, Sitzungen und signierte Token würden fortlaufend ungültig. Der
naheliegende Ausweg, den Schlüssel per `secretKeyRef` zu setzen, bricht das
Template ab:

```
Error: template: paperless-ngx/templates/secrets.yaml:68:6:
  executing … at <b64enc>: wrong type for value; expected string;
  got map[string]interface {}
```

Hinzu kommt, dass es alle vier Verzeichnisse als `subPath` in ein einzelnes
PVC legt — ein Bruch mit der bestehenden Aufteilung ohne Gegenwert.

`zekker6/paperless` 11.8.0 rendert dagegen genau das Gewünschte. Gegen unsere
Gegebenheiten geprüft: Image `3.1.3`, `PAPERLESS_SECRET_KEY` und die
Datenbank-Zugangsdaten sauber über `secretKeyRef`, und alle vier vorhandenen
PVCs über `existingClaim` weiterverwendet. Das Chart dokumentiert die
v3-Umstellung in seinen eigenen Werten, inklusive des alten eingebauten
Standardschlüssels von 2.x, mit dem sich bestehende Sitzungen über den
Versionssprung retten lassen.

Das bisherige Chart von gabe565 steht seit Februar 2025 unverändert bei
`appVersion` 2.14.7. Für einen Hauptversionssprung ist das keine Grundlage.

## Was v3 von uns verlangt

Der Migrationsleitfaden nennt eine Reihe von Änderungen. Betroffen sind wir
nur an wenigen Stellen:

| Forderung | Betrifft uns |
|---|---|
| `PAPERLESS_SECRET_KEY` ist Pflicht | gesetzt, bleibt unverändert |
| `PAPERLESS_DBENGINE` ist Pflicht | **fehlt, wird ergänzt** |
| Suchindex Whoosh → Tantivy | Neuaufbau beim ersten Start, dauert |
| Aufgabenverlauf wird verworfen | hinnehmbar |
| `OCR_MODE` / `OCR_SKIP_ARCHIVE_FILE` neu | nicht gesetzt, nichts zu tun |
| `CONSUMER_*` umbenannt | nicht gesetzt, nichts zu tun |
| `CONSUMER_BARCODE_SCANNER` entfernt | nicht gesetzt, nichts zu tun |
| Dokumentverschlüsselung entfernt | nicht genutzt |
| OIDC braucht ggf. `token_auth_method` | erst bei Fehler nachziehen |

Der Neuaufbau des Suchindex ist auf einem Raspberry Pi der Punkt, an dem
Geduld nötig ist. Er läuft selbsttätig, verlangt aber, dass man ihn abwartet,
bevor man das Ergebnis beurteilt.

## Ablauf

### 1 — Sicherung vor dem Aufstieg

Auf dem Docker-Host, vor jeder Änderung. Zuerst die Referenzzahl der
Dokumente notieren — sie ist der Maßstab für jede spätere Abnahme.

Drei Dinge werden gesichert:

- `document_exporter` in das Verzeichnis `/opt/paperless/export/pre-v3/`
- `pg_dump` der Datenbank
- eine Kopie von `/opt/paperless/data`

Der Export allein genügt nicht. v3 wandelt die Datenbank unumkehrbar um; ohne
Dump führt der Rückweg auf 2.x über einen stundenlangen Reimport statt über
ein Einspielen von Minuten.

Wohin die Sicherung geht: auf den Host und von dort auf den Mac. Der Weg nach
Scaleway steht in diesem Schritt noch nicht offen — auf dem Host ist weder
`aws` noch `rclone` installiert, und die Zugangsdaten liegen in den
GitHub-Secrets von `p3l1/documents`, die sich nicht auslesen lassen. Sie
kommen aus der Scaleway-Konsole und werden in Schritt 5 hinterlegt; ab dann
bedient der CronJob S3 selbsttätig. Liegen sie früher vor, geht die Sicherung
zusätzlich sofort dorthin, über einen `rclone`-Container statt einer
Installation auf dem Host.

Eine Kopie außerhalb des Hosts ist dabei das Entscheidende, nicht deren Ort:
Solange die Sicherung nur auf derselben Maschine liegt, deren Datenbank
gleich unumkehrbar umgewandelt wird, ist sie keine.

**Abnahme:** Die Zahl im Export-Manifest stimmt mit der Datenbank überein,
Export, Dump und `data`-Kopie liegen auf dem Mac und haben plausible Größe.

### 2 — Der Docker-Stack auf 3.1.3

Über `p3l1/documents`, nicht von Hand auf dem Host: Komodo zieht per Webhook,
also bleibt die Compose-Datei die Quelle der Wahrheit.

**2a — auf 2.20.15.** Fassung anheben. Verifiziert wird, dass der Container
gesund meldet, die Version stimmt und die Dokumentenzahl der Referenz
entspricht — mehr braucht dieser Zwischenschritt nicht.

**2b — auf 3.1.3.** Zusammen damit fällig:

- `PAPERLESS_DBENGINE: postgresql` ergänzen
- `apache/tika:latest` auf `3.3.1.0` festnageln, dieselbe Fassung wie im
  Cluster — ein ungepinntes `latest` ist genau die Sorte Überraschung, die
  man während eines Hauptversionssprungs nicht braucht

Danach den Neuaufbau des Suchindex abwarten. Der Dienst ist währenddessen
nicht verfügbar; die Unterbrechung ist eingeplant.

**Abnahme:** Version meldet 3.1.3, Dokumentenzahl unverändert gegenüber der
Referenz, Volltextsuche liefert Treffer, im Log keine Warnungen über
entfernte Variablen.

**Rückweg:** Compose-Datei auf 2.20.14 zurück, `pg_dump` einspielen, `data`
zurückkopieren.

### 3 — Sicherung nach dem Aufstieg

Erneut `document_exporter`, diesmal aus v3, nach
`/opt/paperless/export/v3-final/`. Gesichert wie in Schritt 1: auf den Mac,
nach Scaleway sobald die Zugangsdaten vorliegen.

Dieses Verzeichnis ist zugleich das Umzugsgut für Schritt 4. Es bleibt
deshalb als Verzeichnis liegen und wird nur zum Wegsichern zusätzlich
gepackt — so entsteht es nur einmal.

**Abnahme:** Manifest-Zahl gleich Datenbank-Zahl.

### 4 — Cluster auf 3.1.3 und Einlesen

**4a — Secret anlegen.** Der Wert von `PAPERLESS_SECRET_KEY` wird aus
`docker-compose.env` des Hosts übernommen, damit bestehende Sitzungen und
Token gültig bleiben. Angelegt über das vorhandene `scripts/secret.sh`, damit
er verschlüsselt im Repository landet und einen Neuaufbau überlebt.

**4b — Export-PVC vergrößern.** 5 GiB reichen nicht: Das Export-ZIP wird bei
928 MB Medien rund 1 GiB groß, entpackt noch einmal so viel. Longhorn kann im
Betrieb erweitern; die PVC geht auf 10 GiB.

**4c — Chart wechseln.** `apps/paperless-ngx/base/application.yaml` auf
`zekker6/paperless` 11.8.0 mit Image 3.1.3. Die vier PVCs werden über
`existingClaim` weiterverwendet, nicht neu angelegt. Mit übernommen werden
OIDC- und Mail-Konfiguration, damit sie beim späteren Umschwenk nach außen
nicht fehlen. `PAPERLESS_URL` zeigt vorerst auf
`https://paperless.homelab.internal`.

Die eigenen Manifeste für Tika, Gotenberg und Valkey in
`apps/paperless-ngx/config` bleiben unverändert — das Chart bringt keine
davon mit, und sie laufen.

**4d — Zieldatenbank prüfen.** Der Importer verlangt eine leere Installation.
Die Datenbank enthält null Dokumente, aber möglicherweise bereits einen
angelegten Benutzer. Meldet der Importer sie als nicht leer, wird sie mit
`manage.py flush --no-input` geleert; das räumt die Tabellen, lässt das
Migrationsschema aber stehen. Im Cluster geht dabei nichts verloren.

**4e — Übertragen.** Als Strom, ohne Zwischenlandung auf dem Mac:

```bash
ssh root@10.35.99.168 'tar -C /opt/paperless/export -cf - v3-final' \
  | kubectl -n paperless exec -i deploy/paperless-ngx -- \
      tar -C /usr/src/paperless/export -xf -
```

**4f — Einlesen.** `document_importer` gegen das übertragene Verzeichnis.

**Abnahme:** Dokumentenzahl gleich der Referenz, Volltextsuche liefert
Treffer, ein Original und ein Archiv-PDF lassen sich öffnen, Vorschaubilder
sind vorhanden. Geprüft wird über `paperless.homelab.internal`.

**Rückweg:** Der Docker-Stack läuft unverändert weiter und trägt weiterhin
den externen Namen. Im Cluster wird die Datenbank geleert und erneut
eingelesen.

### 5 — Die Sicherung, die sich selbst anlegt

Ein CronJob im Namensraum `paperless`, täglich um 03:00 Uhr:

1. Ein Init-Container mit dem Paperless-Image führt `document_exporter` aus
2. Der Hauptcontainer lädt das Ergebnis mit `rclone` nach Scaleway S3 und
   verwirft dort alles, was älter als 14 Tage ist

`rclone` statt `aws-cli`, weil es Aufbewahrungsfrist und Übertragung in zwei
Befehlen erledigt; das Image trägt ein arm64-Manifest. Die Zugangsdaten für
Scaleway kommen über `scripts/secret.sh` in dasselbe verschlüsselte Secret
wie der Schlüssel aus Schritt 4a.

Beide Container brauchen `media` lesend und `export` schreibend. Beide PVCs
sind `ReadWriteOnce` und bereits vom Deployment eingebunden, der Job muss
also auf demselben Node landen. Das löst eine `podAffinity` auf den
Paperless-Pod — ohne Umbau auf `ReadWriteMany`.

Dazu gehört das Aufräumen der Altlasten in `p3l1/documents`: `BACKUP.md`
beschreibt dann wieder die Wirklichkeit, und der Workflow
`backup-restore-test.yml` bekommt die richtige Fassung eingetragen und
endlich ein `latest-backup.zip` zu sehen.

## Änderungen an den Repositories

### `p3l1/homelab-argocd`

```
apps/paperless-ngx/
├── base/application.yaml        Chart-Wechsel, Fassung 3.1.3
└── config/
    ├── backup-cronjob.yaml      neu
    └── (services.yaml, database.yaml, httproute.yaml unverändert)
secrets/
└── paperless-secrets.sops.yaml  neu: SECRET_KEY, Scaleway-Zugang
docs/superpowers/specs/
└── 2026-09-06-paperless-v3-k8s-design.md
```

### `p3l1/documents`

```
compose.yaml                     3.1.3, DBENGINE, Tika gepinnt
BACKUP.md                        beschreibt den Cluster-CronJob
.github/workflows/               PAPERLESS_VERSION richtiggestellt
```

## Offene Punkte

Zugangsschlüssel, Bucket-Name und Endpunkt für Scaleway sind zwar als
GitHub-Secrets in `p3l1/documents` hinterlegt, von dort aber nicht wieder
auslesbar. Sie kommen aus der Scaleway-Konsole. Bis sie vorliegen, liegen die
Sicherungen aus Schritt 1 und 3 auf dem Mac; der Weg nach S3 wird mit dem
CronJob in Schritt 5 eingerichtet.

Ob OIDC nach dem Aufstieg ein ausdrückliches `token_auth_method` braucht,
zeigt sich erst beim ersten Anmeldeversuch gegen v3. Nachgezogen wird es nur,
wenn der Rückruf mit `invalid_client` scheitert.

`PAPERLESS_URL` zeigt zunächst nach innen. Beim späteren Umschwenk auf
`documents.cloud.p3l1.de` ist der Wert anzupassen — sonst weist Django die
Anfragen wegen CSRF zurück.

## Abgrenzung

Nicht Teil dieses Vorhabens:

- der Umschwenk von `documents.cloud.p3l1.de` auf den Cluster
- der Abbau des Docker-Stacks und das Aufräumen von `/opt/paperless`
- die Aufnahme der beiden freiwerdenden Pi als `kube-07` und `kube-08`

Alle drei setzen voraus, dass der Cluster sich im Betrieb bewährt hat. Sie
sind eigene Entscheidungen mit eigenem Zeitpunkt.
