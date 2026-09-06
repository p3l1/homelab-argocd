# Paperless-ngx v3 und Cluster-Umzug — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Paperless-Installation von 2.20.14 unter Docker auf 3.1.3 heben
und anschließend in den k3s-Cluster umziehen, mit zwei vollständigen
Sicherungen und einer Sicherung, die sich danach selbst anlegt.

**Architecture:** Der Aufstieg geschieht auf dem Docker-Host, weil dort ein
Rückweg über `pg_dump` existiert. Erst danach wandern die Daten als
`document_exporter`-Verzeichnis in den bereits vorbereiteten, leeren
Cluster-Dienst — dieselbe Datei dient als Sicherung und als Umzugsgut. Der
Docker-Stack bleibt anschließend unangetastet als Rückfalloption stehen.

**Tech Stack:** Docker Compose (über Komodo), paperless-ngx 3.1.3, PostgreSQL
17, k3s auf arm64, ArgoCD, Helm-Chart `zekker6/paperless` 11.8.0,
CloudNativePG, Longhorn, SOPS, rclone.

**Spec:** [`../specs/2026-09-06-paperless-v3-k8s-design.md`](../specs/2026-09-06-paperless-v3-k8s-design.md)

## Global Constraints

- **Referenzzahl: 788 Dokumente.** Zum Zeitpunkt der Planung, vor jeder
  Änderung erhoben. Jede Abnahme in diesem Plan misst sich daran.
- **Reihenfolge 2.20.14 → 2.20.15 → 3.1.3 ist zwingend.** Der
  v3-Migrationsleitfaden lässt den Aufstieg nur von 2.20.15 aus zu.
- **Der Cluster muss 3.1.3 erreichen, bevor importiert wird.** Ein Export aus
  v3 lässt sich in eine 2.x-Instanz nicht einlesen.
- **`PAPERLESS_DBENGINE: postgresql` ist ab v3 Pflicht** — an beiden Orten,
  Docker wie Cluster.
- **`PAPERLESS_SECRET_KEY` ist ab v3 Pflicht** und muss über beide
  Installationen hinweg derselbe bleiben, sonst verfallen alle Sitzungen und
  Token.
- **Der Docker-Host ist `root@10.35.99.168`.** Container heißen
  `documents-webserver-1` und `documents-db-1`, das Komodo-Repository liegt
  unter `/etc/komodo/repos/p3l1/documents/`.
- **Der Branch von `p3l1/documents` heißt `main`**, nicht `master` — die
  README dort behauptet etwas anderes.
- **Commits werden GPG-signiert** (`git commit -S`), Nachrichten auf Englisch
  nach Conventional Commits.
- **Nichts wird auf dem Docker-Host von Hand deployt.** Änderungen gehen über
  `p3l1/documents`; Komodo zieht sie per Webhook.

---

### Task 1: Referenz erheben und vollständig sichern

Die Sicherung vor jeder Änderung. Sie ist die einzige Absicherung gegen den
unumkehrbaren Datenbankumbau in Task 3.

**Files:**
- Keine Repository-Änderung. Diese Aufgabe erzeugt Artefakte auf dem Host und
  auf dem Mac.

**Interfaces:**
- Produziert: `~/backups/paperless/2026-09-06-pre-v3/` auf dem Mac mit
  `export/` (Verzeichnis-Export), `paperless-2.20.14.dump` (pg_dump, Format
  `custom`) und `data.tar.gz`. Task 3 greift im Rückweg darauf zurück.

- [x] **Step 1: Referenzzahl und Ausgangsversion festhalten**

```bash
ssh root@10.35.99.168 'docker exec documents-webserver-1 python3 manage.py shell -c \
  "from documents.models import Document; print(Document.objects.count())"' | tail -1
ssh root@10.35.99.168 'docker inspect --format "{{.Config.Image}}" documents-webserver-1'
```

Erwartet: `788` und `ghcr.io/paperless-ngx/paperless-ngx:2.20.14`.

Weicht die Zahl ab, ist seit der Planung konsumiert worden. Das ist kein
Fehler — die neue Zahl wird ab hier zur Referenz und ersetzt die 788 in allen
folgenden Abnahmen.

- [x] **Step 2: Freien Speicher prüfen**

```bash
ssh root@10.35.99.168 'df -h /opt | tail -1'
```

Erwartet: mindestens 5 GB frei. Der Export wird rund 1 GB groß.

- [x] **Step 3: Zielverzeichnis anlegen**

`document_exporter` legt sein Ziel **nicht** selbst an, sondern bricht mit
`CommandError: That path doesn't exist` ab. Anlegen und dabei gleich dem
Benutzer übereignen, dem der übrige Export-Baum gehört:

```bash
ssh root@10.35.99.168 'docker exec documents-webserver-1 mkdir -p /usr/src/paperless/export/pre-v3'
ssh root@10.35.99.168 'chown 1000:1000 /opt/paperless/export/pre-v3 && ls -ldn /opt/paperless/export/pre-v3'
```

Erwartet: `drwxr-xr-x 2 1000 1000 … /opt/paperless/export/pre-v3`.

`docker exec` läuft als root, das Verzeichnis gehörte sonst root — anders als
alles andere unter `/opt/paperless/export`.

- [x] **Step 4: Export erzeugen**

```bash
ssh root@10.35.99.168 'docker exec documents-webserver-1 \
  document_exporter /usr/src/paperless/export/pre-v3 --no-progress-bar'; echo "exit=$?"
```

Läuft einige Minuten. Erwartet: `exit=0` und kein Traceback.

Den Exit-Code ausdrücklich ausgeben und **nicht** durch `| tail` schicken —
eine Pipe maskiert ihn, und ein gescheiterter Export sähe dann aus wie ein
gelungener.

- [x] **Step 5: Export gegen die Referenz prüfen**

```bash
ssh root@10.35.99.168 'python3 -c "
import json
m = json.load(open(\"/opt/paperless/export/pre-v3/manifest.json\"))
docs = [e for e in m if e[\"model\"] == \"documents.document\"]
print(\"Dokumente im Manifest:\", len(docs))
"'
```

Erwartet: `788` — dieselbe Zahl wie in Step 1.

Weicht sie ab, nicht weitermachen. Der Export ist unvollständig, und alles
Folgende baut darauf auf.

- [x] **Step 6: Datenbank und data-Verzeichnis sichern**

```bash
ssh root@10.35.99.168 'mkdir -p /opt/paperless/backup && \
  docker exec documents-db-1 pg_dump -U paperless -Fc paperless \
    > /opt/paperless/backup/paperless-2.20.14.dump'
ssh root@10.35.99.168 'tar -C /opt/paperless -czf /opt/paperless/backup/data.tar.gz data'
ssh root@10.35.99.168 'ls -lh /opt/paperless/backup/'
```

Erwartet: Dump rund 2 MB (`custom`-Format ist gzip-komprimiert),
`data.tar.gz` rund 50 MB aus 104 MB Rohdaten.

- [x] **Step 7: Prüfen, dass der Dump zurückspielbar ist**

Die Größe allein sagt nichts. `pg_restore --list` liest das Inhaltsverzeichnis
und beweist damit, dass die Datei nicht abgeschnitten ist:

```bash
ssh root@10.35.99.168 'docker exec -i documents-db-1 pg_restore --list \
  < /opt/paperless/backup/paperless-2.20.14.dump' | head -12
ssh root@10.35.99.168 'docker exec -i documents-db-1 pg_restore --list \
  < /opt/paperless/backup/paperless-2.20.14.dump' | grep -c "TABLE DATA"
```

Erwartet: ein Kopf mit `Format: CUSTOM` und `TOC Entries: 850`, dann rund 72
Tabellen mit Daten. Eine Fehlermeldung statt des Inhaltsverzeichnisses
bedeutet, dass der Dump unbrauchbar ist — dann nicht weitermachen.

- [x] **Step 8: Alles auf den Mac holen**

```bash
mkdir -p ~/backups/paperless/2026-09-06-pre-v3/export
rsync -a root@10.35.99.168:/opt/paperless/export/pre-v3/ \
  ~/backups/paperless/2026-09-06-pre-v3/export/; echo "exit=$?"
rsync -a root@10.35.99.168:/opt/paperless/backup/ \
  ~/backups/paperless/2026-09-06-pre-v3/; echo "exit=$?"
```

Ohne `--info=progress2`: Auf dem Mac liegt `openrsync`, das sich als
rsync 2.6.9 ausgibt und die `--info`-Familie nicht kennt. Es bricht sonst mit
einer Usage-Meldung ab.

- [x] **Step 9: Abnahme — die Sicherung liegt außerhalb des Hosts**

```bash
du -sh ~/backups/paperless/2026-09-06-pre-v3/*
python3 -c "
import json, pathlib
m = json.load(open(pathlib.Path.home()/'backups/paperless/2026-09-06-pre-v3/export/manifest.json'))
print('Dokumente:', len([e for e in m if e['model']=='documents.document']))
"
ssh root@10.35.99.168 'find /opt/paperless/export/pre-v3 -type f | wc -l'
find ~/backups/paperless/2026-09-06-pre-v3/export -type f | wc -l
python3 -c "
p = '$HOME/backups/paperless/2026-09-06-pre-v3/paperless-2.20.14.dump'
h = open(p,'rb').read(5)
print('Magic:', h, '-> gueltig' if h == b'PGDMP' else '-> DEFEKT')
"
```

Erwartet: `export/` rund 934 MB, `paperless-2.20.14.dump` 2,3 MB,
`data.tar.gz` 52 MB, `Dokumente: 788`, beide Dateizahlen `2356`, und
`Magic: b'PGDMP' -> gueltig`.

- [x] **Step 10: Den Export gegen die Prüfsummen der Datenbank halten**

Dateizahl und Größe sagen nichts über den Inhalt. Das Manifest führt zu jedem
Dokument die MD5-Summe von Original und Archivfassung, wie sie in der
Datenbank steht:

```bash
cd ~/github/homelab-argocd
./scripts/verify-paperless-backup.py ~/backups/paperless/2026-09-06-pre-v3/export
```

Erwartet: `Pruefsummen korrekt: 1566`, keine abweichende, keine fehlende
Datei. Die 1566 sind 788 Originale plus 778 Archivfassungen — zehn Dokumente
haben keine, was bei bereits durchsuchbaren PDFs normal ist.

- [x] **Step 11: Prüfen, dass Archiv und Dump unterwegs heil geblieben sind**

```bash
gzip -t ~/backups/paperless/2026-09-06-pre-v3/data.tar.gz && echo "gzip-CRC OK"
for f in paperless-2.20.14.dump data.tar.gz; do
  h_host=$(ssh root@10.35.99.168 "sha256sum /opt/paperless/backup/$f | cut -d' ' -f1")
  h_mac=$(shasum -a 256 ~/backups/paperless/2026-09-06-pre-v3/$f | cut -d' ' -f1)
  [ "$h_host" = "$h_mac" ] && echo "$f: identisch" || echo "$f: ABWEICHUNG"
done
```

Erwartet: `gzip-CRC OK` und beide Dateien `identisch`.

- [x] **Step 12: Den Rückweg wirklich gehen — Dump in eine Wegwerf-Datenbank**

Der `pg_dump` ist der Rückweg aus Task 3. Ungeprüft ist er eine Annahme. Der
Test spielt die **Kopie vom Mac** ein — die, die im Ernstfall benutzt würde —
und lässt die Produktivdatenbank unberührt:

```bash
ssh root@10.35.99.168 'docker exec documents-db-1 createdb -U paperless paperless_verify'
cat ~/backups/paperless/2026-09-06-pre-v3/paperless-2.20.14.dump \
  | ssh root@10.35.99.168 'docker exec -i documents-db-1 pg_restore -U paperless \
      -d paperless_verify --no-owner --no-privileges'
for db in paperless_verify paperless; do
  ssh root@10.35.99.168 "docker exec documents-db-1 psql -U paperless -d $db -t -A -c \
    'select md5(string_agg(checksum, chr(44) order by id)) from documents_document;'"
done
ssh root@10.35.99.168 'docker exec documents-db-1 dropdb -U paperless paperless_verify'
```

Erwartet: beide Zeilen liefern **dieselbe** Prüfsumme. Damit ist bewiesen,
dass der Dump alle 788 Dokumentdatensätze unverfälscht enthält.

`chr(44)` statt eines Kommas in Anführungszeichen: Das Quoting müsste sonst
durch ssh, `docker exec` und `psql` hindurch und zerbricht dabei.

Die Wegwerf-Datenbank am Ende wirklich löschen — sie liegt sonst neben der
produktiven auf demselben Postgres.

Erst wenn das steht, darf Task 2 beginnen.

---

### Task 2: Docker-Stack auf 2.20.15

Der Pflichtzwischenschritt. Klein, aber ohne ihn verweigert v3 den Dienst.

**Files:**
- Modify: `~/github/documents/compose.yaml` (Zeile mit
  `ghcr.io/paperless-ngx/paperless-ngx:2.20.14`)

**Interfaces:**
- Konsumiert: die Sicherung aus Task 1 als Rückweg.
- Produziert: einen laufenden Stack auf 2.20.15, Voraussetzung für Task 3.

- [x] **Step 1: Fassung anheben**

```bash
cd ~/github/documents
sed -i '' 's|paperless-ngx:2\.20\.14|paperless-ngx:2.20.15|' compose.yaml
git diff compose.yaml
```

Erwartet: genau eine geänderte Zeile.

- [x] **Step 2: Committen und schieben**

```bash
cd ~/github/documents
git add compose.yaml
git commit -S -m "chore: bump paperless to 2.20.15

Required stepping stone: the v3 migration guide only allows upgrading
from 2.20.15, not from 2.20.14."
git push origin main
```

- [x] **Step 3: Warten, bis Komodo ausgerollt hat**

```bash
for i in $(seq 1 30); do
  img=$(ssh root@10.35.99.168 'docker inspect --format "{{.Config.Image}}" documents-webserver-1 2>/dev/null')
  echo "$(date +%H:%M:%S) $img"
  case "$img" in *2.20.15) echo "ausgerollt"; break;; esac
  sleep 20
done
```

Erwartet: innerhalb weniger Minuten `…paperless-ngx:2.20.15`.

**Wenn nichts passiert:** Der Webhook stand ursprünglich auf
`content_type: form`, Komodo erwartet JSON. Er war damit seit jeher
wirkungslos — GitHub bekommt `200 OK` und meldet ihn als gesund, während
Komodo den Body verwirft. Prüfen lässt sich beides:

```bash
gh api repos/p3l1/documents/hooks --jq '.[0].config.content_type'
ssh root@10.35.99.168 'docker logs --tail 30 komodo-core-1 2>&1 | grep -i webhook | tail -3'
```

Erwartet: `json`. Steht dort `form`, in den Repository-Einstellungen unter
Settings → Webhooks den Komodo-Hook auf `application/json` umstellen. Im Log
zeigt sich der Fehlerfall als `Failed to parse github request body`.

Den Hook nicht per `gh api` umstellen: Ein PATCH ersetzt das ganze
`config`-Objekt, und das Secret ist nicht auslesbar — es ginge dabei
verloren.

- [x] **Step 4: Abnahme**

```bash
ssh root@10.35.99.168 'docker ps --filter name=documents-webserver-1 --format "{{.Status}}"'
ssh root@10.35.99.168 'docker exec documents-webserver-1 python3 manage.py shell -c \
  "from documents.models import Document; print(Document.objects.count())"' | tail -1
```

Erwartet: `Up … (healthy)` und `788`.

Der Container braucht nach dem Start eine Weile bis `healthy`. Erscheint
stattdessen `unhealthy` oder ein Neustartzyklus, in die Logs sehen:
`ssh root@10.35.99.168 'docker logs --tail 80 documents-webserver-1'`.

---

### Task 3: Docker-Stack auf 3.1.3

Der eigentliche Versionssprung, zusammen mit den beiden Änderungen, die v3
verlangt beziehungsweise die währenddessen nicht offen bleiben sollten.

**Files:**
- Modify: `~/github/documents/compose.yaml` — Image-Tag, `PAPERLESS_DBENGINE`
  in der `environment`-Sektion des Dienstes `webserver`, Tika-Tag

**Interfaces:**
- Konsumiert: laufende 2.20.15 aus Task 2.
- Produziert: laufende 3.1.3, Voraussetzung für den Export in Task 4.

- [x] **Step 1: Die drei Änderungen eintragen**

```bash
cd ~/github/documents
sed -i '' 's|paperless-ngx:2\.20\.15|paperless-ngx:3.1.3|' compose.yaml
sed -i '' 's|image: docker.io/apache/tika:latest|image: docker.io/apache/tika:3.3.1.0|' compose.yaml
sed -i '' 's|^\( *\)PAPERLESS_DBHOST: db$|\1PAPERLESS_DBENGINE: postgresql\
\1PAPERLESS_DBHOST: db|' compose.yaml
git diff compose.yaml
```

Erwartet: drei Änderungen — Paperless-Tag auf `3.1.3`, Tika von `latest` auf
`3.3.1.0`, und eine neue Zeile `PAPERLESS_DBENGINE: postgresql` direkt über
`PAPERLESS_DBHOST: db`.

Ohne `PAPERLESS_DBENGINE` leitet v3 die Datenbank nicht mehr aus
`PAPERLESS_DBHOST` ab und fällt auf SQLite zurück — die Installation käme
scheinbar leer hoch.

- [x] **Step 2: Prüfen, dass die Einrückung stimmt**

```bash
cd ~/github/documents && python3 -c "
import yaml
c = yaml.safe_load(open('compose.yaml'))
env = c['services']['webserver']['environment']
print('DBENGINE:', env.get('PAPERLESS_DBENGINE'))
print('DBHOST  :', env.get('PAPERLESS_DBHOST'))
print('image   :', c['services']['webserver']['image'])
print('tika    :', c['services']['tika']['image'])
"
```

Erwartet:

```
DBENGINE: postgresql
DBHOST  : db
image   : ghcr.io/paperless-ngx/paperless-ngx:3.1.3
tika    : docker.io/apache/tika:3.3.1.0
```

Steht bei `DBENGINE` `None`, hat `sed` die Zeile nicht an der richtigen Stelle
eingefügt — von Hand nachziehen, bevor es weitergeht.

- [x] **Step 3: Committen und schieben**

```bash
cd ~/github/documents
git add compose.yaml
git commit -S -m "feat: upgrade paperless to 3.1.3

PAPERLESS_DBENGINE is mandatory from v3 on: the engine is no longer
inferred from PAPERLESS_DBHOST, and without it the install would fall
back to SQLite and come up empty.

Also pins Tika, which ran on a floating latest tag, to the 3.3.1.0 the
cluster already uses."
git push origin main
```

- [x] **Step 4: Ausrollen abwarten**

```bash
for i in $(seq 1 30); do
  img=$(ssh root@10.35.99.168 'docker inspect --format "{{.Config.Image}}" documents-webserver-1 2>/dev/null')
  echo "$(date +%H:%M:%S) $img"
  case "$img" in *3.1.3) echo "ausgerollt"; break;; esac
  sleep 20
done
```

- [x] **Step 5: Den Neuaufbau des Suchindex abwarten**

v3 ersetzt Whoosh durch Tantivy und baut den Index beim ersten Start neu auf.
Auf dem Pi dauert das bei 788 Dokumenten spürbar — der Container meldet
solange nicht `healthy`. Nicht blockierend abwarten:

```bash
for i in $(seq 1 45); do
  st=$(ssh root@10.35.99.168 'docker ps --filter name=documents-webserver-1 --format "{{.Status}}"')
  echo "$(date +%H:%M:%S) $st"
  case "$st" in *healthy*) echo "bereit"; break;; esac
  sleep 20
done
```

Erwartet: innerhalb von etwa 15 Minuten `Up … (healthy)`.

Meldet er stattdessen `unhealthy` oder startet wiederholt neu, in die Logs
sehen — dort steht, woran es liegt:

```bash
ssh root@10.35.99.168 'docker logs --tail 100 documents-webserver-1'
```

- [x] **Step 6: Abnahme**

```bash
ssh root@10.35.99.168 'docker exec documents-webserver-1 cat /usr/src/paperless/src/paperless/version.py | head -3'
ssh root@10.35.99.168 'docker exec documents-webserver-1 python3 manage.py shell -c \
  "from documents.models import Document; print(Document.objects.count())"' | tail -1
ssh root@10.35.99.168 'docker logs --tail 200 documents-webserver-1 2>&1 | grep -iE "deprecat|removed setting|no longer supported"' || echo "keine Warnungen zu entfernten Variablen"
```

Erwartet: Version `(3, 1, 3)`, weiterhin `788`, und keine Warnungen über
entfernte Variablen.

- [ ] **Step 7: Abnahme in der Oberfläche**

`https://documents.cloud.p3l1.de` aufrufen und dreierlei prüfen:

1. Die Anmeldung über OIDC gelingt
2. Eine Volltextsuche nach einem Begriff, der in mehreren Dokumenten
   vorkommt, liefert Treffer — das beweist den neu gebauten Tantivy-Index
3. Ein beliebiges Dokument lässt sich öffnen, Original und Archiv-PDF laden

Scheitert die Anmeldung mit `invalid_client`, verlangt der OIDC-Anbieter unter
v3 ein ausdrückliches `token_auth_method`. Dann in `docker-compose.env` im
JSON von `OIDC_CONFIG` innerhalb von `settings` ergänzen:
`"token_auth_method": "client_secret_basic"`. Die Datei liegt auf dem Host
unter `/etc/komodo/repos/p3l1/documents/docker-compose.env` und wird von
Komodo verwaltet, nicht aus dem Repository.

**Rückweg, falls die Abnahme scheitert:**

```bash
cd ~/github/documents && git revert --no-edit HEAD && git push origin main
# Ausrollen abwarten, dann Datenbank und data zurückspielen:
ssh root@10.35.99.168 'docker compose -p documents stop webserver'
ssh root@10.35.99.168 'docker exec -i documents-db-1 pg_restore -U paperless -d paperless --clean --if-exists \
  < /opt/paperless/backup/paperless-2.20.14.dump'
ssh root@10.35.99.168 'rm -rf /opt/paperless/data && tar -C /opt/paperless -xzf /opt/paperless/backup/data.tar.gz'
ssh root@10.35.99.168 'docker compose -p documents start webserver'
```

Der Revert bringt die Compose-Datei auf 2.20.15 zurück; für 2.20.14 zusätzlich
den Commit aus Task 2 rückgängig machen.

---

### Task 4: Sicherung nach dem Aufstieg — zugleich das Umzugsgut

**Files:**
- Keine Repository-Änderung.

**Interfaces:**
- Konsumiert: laufende 3.1.3 aus Task 3.
- Produziert: `/opt/paperless/export/v3-final/` auf dem Host, das Task 7
  überträgt, und eine Kopie unter `~/backups/paperless/2026-09-06-post-v3/`
  auf dem Mac.

- [ ] **Step 1: Zielverzeichnis anlegen und exportieren**

Wie in Task 1: `document_exporter` legt sein Ziel nicht selbst an, und
`docker exec` läuft als root — deshalb das `chown` auf den Benutzer, dem der
übrige Export-Baum gehört.

```bash
ssh root@10.35.99.168 'docker exec documents-webserver-1 mkdir -p /usr/src/paperless/export/v3-final'
ssh root@10.35.99.168 'chown 1000:1000 /opt/paperless/export/v3-final'
ssh root@10.35.99.168 'docker exec documents-webserver-1 \
  document_exporter /usr/src/paperless/export/v3-final --no-progress-bar'; echo "exit=$?"
```

Erwartet: `exit=0`. Die Meldung `No passphrase was given, sensitive fields
will be in plaintext` ist normal — die Installation nutzt keine
Verschlüsselung.

- [ ] **Step 2: Gegen die Referenz prüfen**

```bash
ssh root@10.35.99.168 'python3 -c "
import json
m = json.load(open(\"/opt/paperless/export/v3-final/manifest.json\"))
print(\"Dokumente im Manifest:\", len([e for e in m if e[\"model\"] == \"documents.document\"]))
"'
```

Erwartet: `788`.

- [ ] **Step 3: Auf den Mac holen**

```bash
mkdir -p ~/backups/paperless/2026-09-06-post-v3
rsync -a root@10.35.99.168:/opt/paperless/export/v3-final/ \
  ~/backups/paperless/2026-09-06-post-v3/; echo "exit=$?"
du -sh ~/backups/paperless/2026-09-06-post-v3
```

Erwartet: `exit=0` und rund 1 GB. Kein `--info=progress2` — siehe Task 1,
Step 8.

- [ ] **Step 4: Abnahme**

```bash
python3 -c "
import json
m = json.load(open('$HOME/backups/paperless/2026-09-06-post-v3/manifest.json'))
print('Dokumente:', len([e for e in m if e['model']=='documents.document']))
"
cd ~/github/homelab-argocd
./scripts/verify-paperless-backup.py ~/backups/paperless/2026-09-06-post-v3
```

Erwartet: `Dokumente: 788`, `Verfahren: sha256` und
`Pruefsummen korrekt: 1566`, keine abweichende und keine fehlende Datei —
dieselbe inhaltliche Prüfung wie in Task 1, Step 10, diesmal gegen den
v3-Export.

**`sha256`, nicht `md5`:** Die Migration `documents.0016_sha256_checksums`
rechnet beim Aufstieg alle Prüfsummen um. Das Skript wählt das Verfahren
anhand der Länge des hinterlegten Werts und kommt mit beiden Fassungen
zurecht; steht dort trotzdem `md5`, stammt der Export nicht aus v3.

Weicht die Zahl der Prüfsummen leicht ab, ist das für sich kein Fehler: v3
kann beim Aufstieg Archivfassungen neu erzeugt haben. Eine **abweichende**
oder **fehlende** Datei ist dagegen immer ein Abbruchgrund.

Das Verzeichnis auf dem Host bleibt liegen — Task 7 überträgt es von dort,
nicht vom Mac.

---

### Task 5: Cluster-Secret anlegen

Der Schlüssel und die Zugangsdaten, die nicht im Klartext ins Repository
dürfen. Muss vor Task 6 stehen: Das neue Chart verweist darauf, und ohne das
Secret bleibt der Pod im `CreateContainerConfigError` hängen.

**Files:**
- Create: `secrets/paperless-secrets.sops.yaml` (erzeugt `scripts/secret.sh`)
- Modify: `secrets/README.md` (Tabelleneintrag)

**Interfaces:**
- Produziert: Secret `paperless-secrets` im Namensraum `paperless` mit den
  Schlüsseln `PAPERLESS_SECRET_KEY`, `PAPERLESS_SOCIALACCOUNT_PROVIDERS`,
  `PAPERLESS_EMAIL_HOST_USER`, `PAPERLESS_EMAIL_HOST_PASSWORD`. Task 6
  referenziert alle vier per `secretKeyRef`, Task 8 ergänzt die
  rclone-Schlüssel in derselben Datei.

- [ ] **Step 1: Die Werte aus der Compose-Installation holen**

Jeweils in die Zwischenablage, damit sie nicht im Terminal stehen bleiben. Ein
Wert nach dem anderen, direkt vor der jeweiligen Eingabeaufforderung in
Step 2:

```bash
ssh root@10.35.99.168 'grep "^PAPERLESS_SECRET_KEY=" /etc/komodo/repos/p3l1/documents/docker-compose.env | cut -d= -f2-' | tr -d "\n" | pbcopy
```

Analog für `OIDC_CONFIG` (der Wert gehört auf den Schlüssel
`PAPERLESS_SOCIALACCOUNT_PROVIDERS`), `PAPERLESS_EMAIL_HOST_USER` und
`PAPERLESS_EMAIL_HOST_PASSWORD`.

Der Schlüssel muss derselbe bleiben wie unter Docker — sonst verfallen alle
Sitzungen und API-Token, die der Import mitbringt.

- [ ] **Step 2: Secret anlegen**

```bash
cd ~/github/homelab-argocd
./scripts/secret.sh paperless-secrets paperless \
  PAPERLESS_SECRET_KEY \
  PAPERLESS_SOCIALACCOUNT_PROVIDERS \
  PAPERLESS_EMAIL_HOST_USER \
  PAPERLESS_EMAIL_HOST_PASSWORD
```

Das Skript fragt die Werte einzeln ab, ohne sie anzuzeigen, legt das Secret im
Cluster an und hinterlegt es verschlüsselt unter `secrets/`.

- [ ] **Step 3: Abnahme — ohne die Werte auszugeben**

```bash
export KUBECONFIG=~/.kube/config
kubectl -n paperless get secret paperless-secrets \
  -o jsonpath='{range .data.*}{@}{"\n"}{end}' | wc -l
kubectl -n paperless get secret paperless-secrets -o jsonpath='{.data}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
for k,v in sorted(d.items()): print(f'{k}: {len(v)} Zeichen (base64)')
"
```

Erwartet: vier Schlüssel, alle mit einer Länge deutlich über null. Ein
Schlüssel mit null Zeichen bedeutet, dass die Eingabe leer war.

- [ ] **Step 4: Prüfen, dass die verschlüsselte Datei lesbar bleibt**

```bash
cd ~/github/homelab-argocd
sops -d secrets/paperless-secrets.sops.yaml | head -6
```

Erwartet: `apiVersion`, `kind: Secret`, Name und Namensraum im Klartext, die
Nutzlast entschlüsselt. Das bestätigt, dass der PGP-Schlüssel greift und die
Datei nach einem Neuaufbau wieder einspielbar ist.

- [ ] **Step 5: README ergänzen und committen**

In `secrets/README.md` die Tabelle um eine Zeile erweitern:

```markdown
| `paperless-secrets.sops.yaml` | Secret Key, OIDC und Mail für Paperless |
```

```bash
cd ~/github/homelab-argocd
git add secrets/paperless-secrets.sops.yaml secrets/README.md
git commit -S -m "feat(paperless): add secret for key, OIDC and mail

The secret key is carried over from the Compose install so sessions and
API tokens survive the move; a fresh one would invalidate everything the
import brings along."
```

---

### Task 6: Chart-Wechsel auf zekker6 und Fassung 3.1.3

**Files:**
- Modify: `apps/paperless-ngx/base/application.yaml` (die erste Quelle,
  Zeilen 12–66 — der gesamte `chart`-Block)

**Interfaces:**
- Konsumiert: Secret `paperless-secrets` aus Task 5.
- Produziert: einen Cluster-Dienst auf 3.1.3 unter demselben Service-Namen
  `paperless-ngx:8000`, den HTTPRoute und Newt-`ExternalName` bereits
  ansprechen. Task 7 importiert hinein.

Die vier PVC-Namen bleiben unverändert (`paperless-ngx-data`, `-media`,
`-consume`, `-export`) — geprüft durch Rendern beider Charts. Deshalb prunet
ArgoCD sie beim Wechsel nicht, und `export` wächst durch dieselbe Änderung von
5 auf 10 GiB.

- [ ] **Step 1: Den bestehenden Zustand festhalten**

```bash
export KUBECONFIG=~/.kube/config
kubectl -n paperless get pvc -o custom-columns=NAME:.metadata.name,SIZE:.spec.resources.requests.storage --no-headers
kubectl -n paperless get deploy paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Erwartet: vier PVCs (`consume` 5Gi, `data` 5Gi, `export` 5Gi, `media` 20Gi)
und Image `…paperless-ngx:2.20.14`.

- [ ] **Step 2: Die erste Quelle in der Application ersetzen**

In `apps/paperless-ngx/base/application.yaml` den gesamten ersten
`sources`-Eintrag (von `- chart: paperless-ngx` bis einschließlich der letzten
Zeile des `valuesObject`) durch diesen ersetzen. Der zweite Eintrag mit
`repoURL: …/homelab-argocd.git` und `path: apps/paperless-ngx/config` bleibt
unverändert:

```yaml
    - chart: paperless
      repoURL: https://zekker6.github.io/helm-charts
      targetRevision: 11.8.0
      helm:
        valuesObject:
          image:
            tag: 3.1.3
          env:
            PAPERLESS_URL: https://paperless.homelab.internal
            PAPERLESS_TIME_ZONE: Europe/Berlin
            PAPERLESS_OCR_LANGUAGE: deu+eng
            PAPERLESS_OCR_LANGUAGES: deu eng
            # Ab v3 wird die Engine nicht mehr aus DBHOST abgeleitet; ohne
            # diese Zeile faellt Paperless auf SQLite zurueck.
            PAPERLESS_DBENGINE: postgresql
            PAPERLESS_DBHOST: paperless-db-rw
            PAPERLESS_DBNAME: paperless
            PAPERLESS_DBUSER:
              valueFrom:
                secretKeyRef:
                  name: paperless-db-app
                  key: username
            PAPERLESS_DBPASS:
              valueFrom:
                secretKeyRef:
                  name: paperless-db-app
                  key: password
            PAPERLESS_SECRET_KEY:
              valueFrom:
                secretKeyRef:
                  name: paperless-secrets
                  key: PAPERLESS_SECRET_KEY
            PAPERLESS_REDIS: redis://valkey:6379
            PAPERLESS_TIKA_ENABLED: "1"
            PAPERLESS_TIKA_ENDPOINT: http://tika:9998
            PAPERLESS_TIKA_GOTENBERG_ENDPOINT: http://gotenberg:3000
            PAPERLESS_APPS: allauth.socialaccount.providers.openid_connect
            PAPERLESS_SOCIALACCOUNT_PROVIDERS:
              valueFrom:
                secretKeyRef:
                  name: paperless-secrets
                  key: PAPERLESS_SOCIALACCOUNT_PROVIDERS
            PAPERLESS_EMAIL_HOST: ha01s025.org-dns.com
            PAPERLESS_EMAIL_PORT: "465"
            PAPERLESS_EMAIL_USE_SSL: "true"
            PAPERLESS_EMAIL_HOST_USER:
              valueFrom:
                secretKeyRef:
                  name: paperless-secrets
                  key: PAPERLESS_EMAIL_HOST_USER
            PAPERLESS_EMAIL_HOST_PASSWORD:
              valueFrom:
                secretKeyRef:
                  name: paperless-secrets
                  key: PAPERLESS_EMAIL_HOST_PASSWORD
          service:
            main:
              ports:
                http:
                  port: 8000
          persistence:
            data:
              enabled: true
              size: 5Gi
              storageClass: longhorn
              accessMode: ReadWriteOnce
            media:
              enabled: true
              size: 20Gi
              storageClass: longhorn
              accessMode: ReadWriteOnce
            consume:
              enabled: true
              size: 5Gi
              storageClass: longhorn
              accessMode: ReadWriteOnce
            export:
              # 10 statt 5 GiB: Der Export ist rund 1 GB gross, entpackt
              # nochmal so viel.
              enabled: true
              size: 10Gi
              storageClass: longhorn
              accessMode: ReadWriteOnce
```

Auch den Kommentarkopf der Datei anpassen: Er nennt bislang das Chart als
Quelle für Redis, was seit dem Valkey-Wechsel nicht mehr stimmt.

- [ ] **Step 3: Vor dem Committen lokal rendern**

```bash
cd ~/github/homelab-argocd
helm repo add zekker6 https://zekker6.github.io/helm-charts >/dev/null 2>&1
helm repo update zekker6 >/dev/null
python3 -c "
import yaml
a = yaml.safe_load(open('apps/paperless-ngx/base/application.yaml'))
yaml.safe_dump(a['spec']['sources'][0]['helm']['valuesObject'], open('/tmp/pv.yaml','w'))
"
helm template paperless-ngx zekker6/paperless --version 11.8.0 -n paperless -f /tmp/pv.yaml \
  | python3 -c "
import sys,yaml
for d in yaml.safe_load_all(sys.stdin):
    if not d: continue
    if d['kind']=='PersistentVolumeClaim':
        print('PVC ', d['metadata']['name'], d['spec']['resources']['requests']['storage'])
    if d['kind']=='Service':
        print('SVC ', d['metadata']['name'], [p['port'] for p in d['spec']['ports']])
    if d['kind']=='Deployment':
        c=d['spec']['template']['spec']['containers'][0]
        print('IMG ', c['image'])
        miss=[e['name'] for e in c['env'] if 'value' not in e and 'valueFrom' not in e]
        print('ENV ohne Wert:', miss or 'keine')
"
```

Erwartet:

```
PVC  paperless-ngx-consume 5Gi
PVC  paperless-ngx-data 5Gi
PVC  paperless-ngx-export 10Gi
PVC  paperless-ngx-media 20Gi
SVC  paperless-ngx [8000]
IMG  ghcr.io/paperless-ngx/paperless-ngx:3.1.3
ENV ohne Wert: keine
```

Die PVC-Namen müssen exakt denen aus Step 1 entsprechen. Weicht einer ab,
nicht committen — ArgoCD würde beim Sync die alte PVC prunen und eine neue
anlegen. Der Service muss `paperless-ngx` auf Port 8000 bleiben, sonst laufen
HTTPRoute und Newt-`ExternalName` ins Leere.

- [ ] **Step 4: Committen und schieben**

```bash
cd ~/github/homelab-argocd
git add apps/paperless-ngx/base/application.yaml
git commit -S -m "feat(paperless): move to zekker6 chart and v3.1.3

The gabe565 chart has been unchanged since Feb 2025 at appVersion
2.14.7. The WrenIX chart that ArtifactHub lists as paperless-ngx is
unusable under ArgoCD: it derives PAPERLESS_SECRET_KEY via lookup with
randAlphaNum as a fallback, so every sync renders a different key.

zekker6/paperless keeps the four PVC names identical, so nothing is
pruned on the switch, and grows export from 5 to 10 GiB for the import."
git push origin main
```

- [ ] **Step 5: Sync abwarten und prüfen, dass nichts geprunt wurde**

```bash
export KUBECONFIG=~/.kube/config
for i in $(seq 1 30); do
  img=$(kubectl -n paperless get deploy paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)
  echo "$(date +%H:%M:%S) $img"
  case "$img" in *3.1.3) break;; esac
  sleep 20
done
kubectl -n paperless get pvc
kubectl -n argocd get application paperless-ngx
```

Erwartet: Image auf `3.1.3`, weiterhin genau vier `paperless-ngx-*`-PVCs plus
die drei `paperless-db-*` und `valkey-data`, `export` nun mit 10Gi, und die
Application `Synced/Healthy`.

Greift ArgoCD nicht von selbst: `kubectl -n argocd patch application
paperless-ngx --type merge -p '{"operation":{"sync":{}}}'`.

- [ ] **Step 6: Abnahme**

```bash
kubectl -n paperless get pods
kubectl -n paperless logs deploy/paperless-ngx --tail 40
kubectl -n paperless exec deploy/paperless-ngx -- python3 manage.py shell -c \
  "from documents.models import Document; print('Dokumente:', Document.objects.count())" 2>&1 | tail -2
```

Erwartet: Pod `Running` und `1/1`, im Log kein `CreateContainerConfigError`
und keine Meldung über eine fehlende Datenbank, und `Dokumente: 0` — die
Instanz ist weiterhin leer, aber nun auf v3.

Meldet der Pod `CreateContainerConfigError`, fehlt ein Schlüssel im Secret aus
Task 5: `kubectl -n paperless describe pod -l app.kubernetes.io/name=paperless`
nennt den Namen.

---

### Task 7: Übertragen und einlesen

**Files:**
- Keine Repository-Änderung.

**Interfaces:**
- Konsumiert: `/opt/paperless/export/v3-final/` auf dem Host aus Task 4, der
  Cluster-Dienst auf 3.1.3 aus Task 6.
- Produziert: 788 Dokumente im Cluster.

- [ ] **Step 1: Zieldatenbank auf Leere prüfen**

```bash
export KUBECONFIG=~/.kube/config
kubectl -n paperless exec deploy/paperless-ngx -- python3 manage.py shell -c "
from documents.models import Document
from django.contrib.auth.models import User
print('Dokumente:', Document.objects.count())
print('Benutzer:', User.objects.count())
" 2>&1 | tail -3
```

Erwartet: `Dokumente: 0`. Die Benutzerzahl darf über null liegen; der Importer
sagt in Step 4, ob ihn das stört.

- [ ] **Step 2: Platz in der export-PVC prüfen**

```bash
kubectl -n paperless exec deploy/paperless-ngx -- df -h /usr/src/paperless/export
```

Erwartet: rund 10 GB Kapazität, nahezu vollständig frei. Steht dort noch 5 GB,
ist die Vergrößerung aus Task 6 nicht durchgelaufen — dann dort nachsehen,
bevor die Übertragung beginnt.

- [ ] **Step 3: Übertragen**

Als Strom, ohne Zwischenlandung auf dem Mac:

```bash
ssh root@10.35.99.168 'tar -C /opt/paperless/export -cf - v3-final' \
  | kubectl -n paperless exec -i deploy/paperless-ngx -- \
      tar -C /usr/src/paperless/export -xf -
```

Läuft bei rund 1 GB über das Heimnetz einige Minuten und gibt nichts aus.

- [ ] **Step 4: Vollständigkeit der Übertragung prüfen**

```bash
ssh root@10.35.99.168 'find /opt/paperless/export/v3-final -type f | wc -l'
kubectl -n paperless exec deploy/paperless-ngx -- \
  sh -c 'find /usr/src/paperless/export/v3-final -type f | wc -l'
```

Erwartet: beide Zahlen identisch. Weichen sie ab, ist der Strom abgerissen —
Step 3 wiederholen, `tar` überschreibt.

- [ ] **Step 5: Einlesen**

```bash
kubectl -n paperless exec deploy/paperless-ngx -- \
  document_importer /usr/src/paperless/export/v3-final --no-progress-bar
```

Das dauert: Der Importer prüft jede Prüfsumme und erzeugt Vorschaubilder neu.

Beschwert er sich, die Installation sei nicht leer, die Tabellen räumen und
erneut einlesen — im Cluster geht dabei nichts verloren:

```bash
kubectl -n paperless exec deploy/paperless-ngx -- python3 manage.py flush --no-input
kubectl -n paperless exec deploy/paperless-ngx -- \
  document_importer /usr/src/paperless/export/v3-final --no-progress-bar
```

- [ ] **Step 6: Suchindex neu aufbauen lassen**

```bash
kubectl -n paperless exec deploy/paperless-ngx -- python3 manage.py document_index reindex
```

Der Import füllt die Datenbank, der Tantivy-Index wird davon nicht zwingend
mitgezogen. Ohne diesen Schritt findet die Volltextsuche nichts, obwohl alle
Dokumente da sind.

- [ ] **Step 7: Abnahme gegen die Referenz**

```bash
kubectl -n paperless exec deploy/paperless-ngx -- python3 manage.py shell -c "
from documents.models import Document, Correspondent, Tag
print('Dokumente:', Document.objects.count())
print('Korrespondenten:', Correspondent.objects.count())
print('Tags:', Tag.objects.count())
print('ohne Archivdatei:', Document.objects.filter(archive_filename__isnull=True).count())
" 2>&1 | tail -5
```

Erwartet: `Dokumente: 788`. Korrespondenten und Tags müssen den Werten aus der
Docker-Installation entsprechen — dieselbe Abfrage dort laufen lassen und
vergleichen:

```bash
ssh root@10.35.99.168 'docker exec documents-webserver-1 python3 manage.py shell -c "
from documents.models import Document, Correspondent, Tag
print(Document.objects.count(), Correspondent.objects.count(), Tag.objects.count())
"' | tail -1
```

- [ ] **Step 8: Abnahme in der Oberfläche**

`https://paperless.homelab.internal` aufrufen und prüfen:

1. Anmeldung mit einem lokalen Konto aus dem Import gelingt. OIDC funktioniert
   hier noch nicht — die Rückrufadresse beim Anbieter zeigt auf
   `documents.cloud.p3l1.de`, nicht auf den internen Namen. Das ist erwartet
   und kein Fehler.
2. Die Dokumentenliste zeigt 788 Einträge mit Vorschaubildern
3. Eine Volltextsuche liefert Treffer
4. Ein Dokument öffnet sich, Original und Archiv-PDF laden

Fehlt das Zertifikat im Browser, einmalig `./scripts/trust-ca.sh --install`.

**Rückweg:** Es gibt keinen, der nötig wäre — der Docker-Stack läuft
unverändert weiter und trägt weiterhin `documents.cloud.p3l1.de`. Im Cluster
wird bei Bedarf mit `flush` geräumt und erneut eingelesen.

---

### Task 8: Die Sicherung, die sich selbst anlegt

Schließt die Lücke zwischen dem, was `BACKUP.md` behauptet, und dem, was
existiert.

**Files:**
- Create: `apps/paperless-ngx/config/backup-cronjob.yaml`
- Modify: `secrets/paperless-secrets.sops.yaml` (rclone-Schlüssel ergänzen)
- Modify: `~/github/documents/BACKUP.md`
- Modify: `~/github/documents/.github/workflows/backup-restore-test.yml`

**Interfaces:**
- Konsumiert: Secret `paperless-secrets` aus Task 5, den laufenden Dienst aus
  Task 7.
- Produziert: täglich um 03:00 Uhr ein `latest-backup.zip` im Scaleway-Bucket,
  das der wöchentliche GitHub-Workflow erwartet.

- [ ] **Step 1: Scaleway-Zugangsdaten ergänzen**

Zugangsschlüssel, Bucket und Endpunkt aus der Scaleway-Konsole holen — die
GitHub-Secrets in `p3l1/documents` lassen sich nicht zurücklesen. Dann in
dieselbe Datei nachtragen; leere Eingaben lassen die vorhandenen Schlüssel
unberührt:

```bash
cd ~/github/homelab-argocd
./scripts/secret.sh paperless-secrets paperless \
  RCLONE_CONFIG_SCW_ACCESS_KEY_ID \
  RCLONE_CONFIG_SCW_SECRET_ACCESS_KEY \
  SCW_BUCKET
```

- [ ] **Step 2: Prüfen, dass die alten Schlüssel erhalten sind**

```bash
export KUBECONFIG=~/.kube/config
kubectl -n paperless get secret paperless-secrets -o jsonpath='{.data}' | python3 -c "
import json,sys
print(sorted(json.load(sys.stdin).keys()))
"
```

Erwartet: alle sieben Schlüssel — die vier aus Task 5 und die drei neuen.
Fehlt einer der alten, hat das Skript die Datei nicht als Grundlage genommen;
dann aus `sops -d` wiederherstellen, bevor es weitergeht.

- [ ] **Step 3: Den CronJob anlegen**

`apps/paperless-ngx/config/backup-cronjob.yaml`:

```yaml
# Taeglich um 03:00: Export in die export-PVC, Upload nach Scaleway.
# Beide Volumes sind ReadWriteOnce und haengen am Paperless-Pod, deshalb
# muss der Job auf demselben Node landen - das erzwingt die podAffinity.
apiVersion: batch/v1
kind: CronJob
metadata:
  name: paperless-backup
  namespace: paperless
spec:
  schedule: "0 3 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          affinity:
            podAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                - labelSelector:
                    matchLabels:
                      app.kubernetes.io/name: paperless
                  topologyKey: kubernetes.io/hostname
          initContainers:
            - name: export
              image: ghcr.io/paperless-ngx/paperless-ngx:3.1.3
              command:
                - sh
                - -c
                - |
                  set -e
                  # document_exporter legt sein Ziel nicht an, sondern
                  # bricht mit "That path doesn't exist" ab.
                  mkdir -p /usr/src/paperless/export/backup
                  exec document_exporter /usr/src/paperless/export/backup \
                    --zip --zip-name latest-backup --delete --no-progress-bar
              env:
                - name: PAPERLESS_DBENGINE
                  value: postgresql
                - name: PAPERLESS_DBHOST
                  value: paperless-db-rw
                - name: PAPERLESS_DBNAME
                  value: paperless
                - name: PAPERLESS_DBUSER
                  valueFrom:
                    secretKeyRef:
                      name: paperless-db-app
                      key: username
                - name: PAPERLESS_DBPASS
                  valueFrom:
                    secretKeyRef:
                      name: paperless-db-app
                      key: password
                - name: PAPERLESS_SECRET_KEY
                  valueFrom:
                    secretKeyRef:
                      name: paperless-secrets
                      key: PAPERLESS_SECRET_KEY
                - name: PAPERLESS_REDIS
                  value: redis://valkey:6379
              volumeMounts:
                - name: media
                  mountPath: /usr/src/paperless/media
                - name: data
                  mountPath: /usr/src/paperless/data
                - name: export
                  mountPath: /usr/src/paperless/export
              resources:
                requests:
                  cpu: 100m
                  memory: 256Mi
                limits:
                  memory: 1Gi
          containers:
            - name: upload
              image: docker.io/rclone/rclone:1.71.0
              command:
                - sh
                - -c
                - |
                  set -e
                  rclone copyto \
                    /export/backup/latest-backup.zip \
                    "scw:${SCW_BUCKET}/latest-backup.zip"
                  rclone copyto \
                    /export/backup/latest-backup.zip \
                    "scw:${SCW_BUCKET}/daily/paperless-$(date +%F).zip"
                  rclone delete --min-age 14d "scw:${SCW_BUCKET}/daily"
              env:
                - name: RCLONE_CONFIG_SCW_TYPE
                  value: s3
                - name: RCLONE_CONFIG_SCW_PROVIDER
                  value: Other
                - name: RCLONE_CONFIG_SCW_REGION
                  value: fr-par
                - name: RCLONE_CONFIG_SCW_ENDPOINT
                  value: s3.fr-par.scw.cloud
                - name: RCLONE_CONFIG_SCW_ACCESS_KEY_ID
                  valueFrom:
                    secretKeyRef:
                      name: paperless-secrets
                      key: RCLONE_CONFIG_SCW_ACCESS_KEY_ID
                - name: RCLONE_CONFIG_SCW_SECRET_ACCESS_KEY
                  valueFrom:
                    secretKeyRef:
                      name: paperless-secrets
                      key: RCLONE_CONFIG_SCW_SECRET_ACCESS_KEY
                - name: SCW_BUCKET
                  valueFrom:
                    secretKeyRef:
                      name: paperless-secrets
                      key: SCW_BUCKET
              volumeMounts:
                - name: export
                  mountPath: /export
              resources:
                requests:
                  cpu: 100m
                  memory: 128Mi
                limits:
                  memory: 512Mi
          volumes:
            - name: media
              persistentVolumeClaim:
                claimName: paperless-ngx-media
            - name: data
              persistentVolumeClaim:
                claimName: paperless-ngx-data
            - name: export
              persistentVolumeClaim:
                claimName: paperless-ngx-export
```

`--delete` räumt den vorherigen Lauf aus dem Exportverzeichnis, sonst wächst
die PVC mit jeder Nacht.

- [ ] **Step 4: Vor dem Committen lokal prüfen**

```bash
cd ~/github/homelab-argocd
kubectl apply --dry-run=client -f apps/paperless-ngx/config/backup-cronjob.yaml
```

Erwartet: `cronjob.batch/paperless-backup created (dry run)`.

- [ ] **Step 5: Den Selektor der podAffinity gegen die Wirklichkeit prüfen**

```bash
export KUBECONFIG=~/.kube/config
kubectl -n paperless get pods -l app.kubernetes.io/name=paperless \
  -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName --no-headers
```

Erwartet: genau der Paperless-Pod mit seinem Node. Kommt nichts zurück, trägt
das Chart ein anderes Label — dann mit
`kubectl -n paperless get pod <name> --show-labels` das richtige ablesen und
im `matchLabels` des CronJob eintragen. Ein Selektor, der nichts trifft, lässt
den Job dauerhaft `Pending` bleiben.

- [ ] **Step 6: Committen und schieben**

```bash
cd ~/github/homelab-argocd
git add apps/paperless-ngx/config/backup-cronjob.yaml secrets/paperless-secrets.sops.yaml
git commit -S -m "feat(paperless): back up to Scaleway nightly

BACKUP.md described a backup to S3 that never existed: no cron, no
timer, no upload tooling on the host, and the last export was from
April. The weekly restore test pulled a latest-backup.zip that nobody
ever put there.

Both volumes are ReadWriteOnce and already mounted by the deployment, so
podAffinity pins the job to the same node instead of moving them to
ReadWriteMany."
git push origin main
```

- [ ] **Step 7: Einen Lauf von Hand auslösen**

Nicht bis 03:00 Uhr warten:

```bash
export KUBECONFIG=~/.kube/config
kubectl -n paperless create job --from=cronjob/paperless-backup backup-probe
kubectl -n paperless wait --for=condition=complete job/backup-probe --timeout=30m
kubectl -n paperless logs job/backup-probe --all-containers --tail 30
```

Erwartet: der Job endet `Complete`, im Log des Init-Containers der
abgeschlossene Export, im Upload-Container keine Fehlermeldung von rclone.

Bleibt der Pod `Pending`, greift die podAffinity nicht — Step 5.

- [ ] **Step 8: Abnahme — die Datei liegt im Bucket**

```bash
kubectl -n paperless run rclone-check --rm -i --restart=Never \
  --image=docker.io/rclone/rclone:1.71.0 \
  --overrides='{"spec":{"containers":[{"name":"rclone-check","image":"docker.io/rclone/rclone:1.71.0","command":["sh","-c","rclone ls scw:$SCW_BUCKET"],"envFrom":[{"secretRef":{"name":"paperless-secrets"}}],"env":[{"name":"RCLONE_CONFIG_SCW_TYPE","value":"s3"},{"name":"RCLONE_CONFIG_SCW_PROVIDER","value":"Other"},{"name":"RCLONE_CONFIG_SCW_REGION","value":"fr-par"},{"name":"RCLONE_CONFIG_SCW_ENDPOINT","value":"s3.fr-par.scw.cloud"}]}]}}'
```

Erwartet: `latest-backup.zip` mit rund 1 GB und ein Eintrag unter `daily/`.

- [ ] **Step 9: Probejob aufräumen**

```bash
kubectl -n paperless delete job backup-probe
```

- [ ] **Step 10: Die Altlasten in `p3l1/documents` beseitigen**

In `BACKUP.md` den Abschnitt „Automation" ersetzen: Die Sicherung läuft nicht
mehr auf dem Docker-Host, sondern als CronJob `paperless-backup` im Namensraum
`paperless` des Clusters, täglich um 03:00 Uhr, mit 14 Tagen Aufbewahrung
unter `daily/` und einem stets aktuellen `latest-backup.zip`. Der Verweis auf
`docker compose exec webserver document_exporter` beschreibt dann den
Handbetrieb, nicht den Regelfall.

In `.github/workflows/backup-restore-test.yml` die festgenagelte Fassung
richtigstellen:

```bash
cd ~/github/documents
sed -i '' 's|PAPERLESS_VERSION: "2.17.1"|PAPERLESS_VERSION: "3.1.3"|' .github/workflows/backup-restore-test.yml
grep -n "PAPERLESS_VERSION" .github/workflows/backup-restore-test.yml
```

Erwartet: `PAPERLESS_VERSION: "3.1.3"`.

- [ ] **Step 11: Committen**

```bash
cd ~/github/documents
git add BACKUP.md .github/workflows/backup-restore-test.yml
git commit -S -m "docs: point backup at the cluster cronjob

The backup now runs as a CronJob in the cluster, not on this host. The
restore test was pinned to 2.17.1 and pulled a latest-backup.zip that
nothing produced; both are fixed."
git push origin main
```

- [ ] **Step 12: Den Restore-Test laufen lassen**

```bash
cd ~/github/documents
gh workflow run backup-restore-test.yml
sleep 30 && gh run list --workflow=backup-restore-test.yml --limit 1
```

Erwartet: der Lauf startet und endet grün. Das ist die eigentliche Abnahme
des ganzen Vorhabens — sie beweist, dass die Sicherung nicht nur entsteht,
sondern sich auch zurückspielen lässt.

- [ ] **Step 13: Das Umzugsgut aus der export-PVC räumen**

Erst jetzt, nachdem der Restore-Test grün ist. Bis dahin bleibt `v3-final`
liegen: Solange nicht bewiesen ist, dass die neue Sicherung trägt, ist es die
einzige Kopie im Cluster.

```bash
export KUBECONFIG=~/.kube/config
kubectl -n paperless exec deploy/paperless-ngx -- df -h /usr/src/paperless/export
kubectl -n paperless exec deploy/paperless-ngx -- rm -rf /usr/src/paperless/export/v3-final
kubectl -n paperless exec deploy/paperless-ngx -- df -h /usr/src/paperless/export
```

Erwartet: rund 1 GB weniger belegt. Die Kopie auf dem Mac unter
`~/backups/paperless/2026-09-06-post-v3/` bleibt erhalten, ebenso die auf dem
Docker-Host.

Ohne diesen Schritt liegen dauerhaft das Umzugsgut und die nächtliche ZIP
nebeneinander in derselben 10-GiB-PVC.

---

## Was dieser Plan bewusst offen lässt

Drei Dinge stehen ausdrücklich nicht darin, weil sie voraussetzen, dass sich
der Cluster erst im Betrieb bewährt:

- der Umschwenk von `documents.cloud.p3l1.de` auf den Cluster. Dazu gehört,
  `PAPERLESS_URL` auf den externen Namen zu ändern, die Pangolin-Ressource auf
  den Cluster-Newt zu zeigen und die OIDC-Rückrufadresse zu prüfen
- der Abbau des Docker-Stacks und das Aufräumen von `/opt/paperless`
- die Aufnahme der beiden dann freien Pi 5 als `kube-07` und `kube-08`

Bis dahin läuft die Docker-Installation weiter und trägt den externen Namen.
