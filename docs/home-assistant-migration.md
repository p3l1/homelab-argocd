# Home Assistant vom Pi 5 in den Cluster

Der Raspberry Pi 5 mit HA OS ist abgelöst. Grundlage war das verschlüsselte
Supervisor-Backup `Automatic_backup_2026.8.3_2026-09-13`; der Schlüssel steht
im Notfallkit, nicht hier.

Aufbau und Betrieb der Anwendung stehen in
[`apps/home-assistant/README.md`](../apps/home-assistant/README.md). Dieses
Dokument beschreibt den einmaligen Umzug — damit er nachvollziehbar bleibt und
sich wiederholen ließe.

## Was das Backup enthielt

Ein Supervisor-Backup ist ein TAR aus TARs. Die inneren Archive sind mit
`SecureTar` verschlüsselt, erkennbar am Magic `SecureTar\x03`; `tar -tzf`
scheitert daran. Entschlüsseln geht mit der Bibliothek, die auch der
Supervisor benutzt:

```python
from securetar import SecureTarFile
with SecureTarFile(pfad, gzip=True, password=SCHLUESSEL) as tar:
    tar.extractall(path=ziel, filter="fully_trusted")
```

Der Schlüssel aus dem Notfallkit wird mitsamt Bindestrichen übergeben.

| Archiv | Inhalt |
|---|---|
| `homeassistant.tar.gz` | das Konfigurationsverzeichnis, 174 MB entpackt |
| `core_matter_server.tar.gz` | die Matter-Fabric |
| `core_piper.tar.gz` | Piper — in HA auf „ignorieren", siehe unten |
| `core_ssh.tar.gz` | Terminal-Add-on, im Cluster gegenstandslos |
| `ssl.tar.gz` | Zertifikate |

## Änderungen an `.storage` vor dem Einspielen

`.storage` ist Laufzeitzustand und geht unverändert ins Volume — mit vier
Ausnahmen, die auf dem Pi hingen:

| Datei | Änderung | Grund |
|---|---|---|
| `core.config_entries` | `matter.url` → `ws://127.0.0.1:5580/ws` | Das Add-on hieß `core-matter-server`; jetzt läuft der Server mit `hostNetwork` auf demselben Node |
| `core.config_entries` | `bluetooth.unique_id` → MAC des neuen Adapters | HA ordnet Adapter über die `unique_id` zu; sonst legt es einen Ermittlungsvorgang an |
| `core.config_entries` | `hassio`, `raspberry_pi`, `rpi_power` deaktiviert | Supervisor und Pi-Hardware gibt es im Container nicht. Deaktivieren statt löschen, damit Geräte- und Entitätsregister unberührt bleiben |
| `core.config` | `internal_url` → `https://home.homelab.internal` | War leer; `external_url` stand schon richtig |

Die YAML-Dateien aus dem Wurzelverzeichnis wanderten **nicht** ins Volume,
sondern nach `apps/home-assistant/config/hass` — sie kommen als ConfigMap.
Lägen sie zusätzlich im Volume, würde alles doppelt geladen.

## Der Node

Die Rolle `node_base` räumt auf jedem Node Funk und Zeroconf weg. Für diesen
einen Node muss das Gegenteil gelten, dafür stehen im Inventar zwei Schalter:
`node_bluetooth` und `node_ipv6`.

Dabei sind zwei Dinge aufgefallen, die ohne Prüfung still fehlschlagen:

- **rfkill.** Der USB-Adapter kam soft-gesperrt hoch; `hciconfig hci0 up`
  meldete „Operation not possible due to RF-kill (132)", und Home Assistant
  drehte in einer Wiederherstellungsschleife. Die Unit
  `bluetooth-unblock.service` hebt die Sperre nach `systemd-rfkill` auf.
- **IPv6.** `method6` stand auf `disabled`, wodurch `eth0` nicht einmal eine
  Link-Local-Adresse hatte. Matter spricht ausschließlich IPv6 — ohne das
  erreicht der Server kein Gerät. Das Ändern des Profils reicht nicht, die
  Verbindung muss neu hochgezogen werden.

## Die Historie

Home Assistant legt das Postgres-Schema beim ersten Start selbst an. Die
104 MB SQLite-Historie kommt danach mit
[`scripts/ha-history-to-postgres.py`](../scripts/ha-history-to-postgres.py)
hinterher, bei angehaltenem Home Assistant:

```bash
kubectl -n home-assistant scale deploy/home-assistant --replicas=0
kubectl -n home-assistant port-forward svc/home-assistant-db-rw 5432:5432 &
./scripts/ha-history-to-postgres.py home-assistant_v2.db "postgresql://…"
kubectl -n home-assistant scale deploy/home-assistant --replicas=1
```

Nicht `pgloader`: Die Recorder-Tabellen haben Boolean-Spalten, die SQLite als
0/1 ablegt, `recorder_runs` hat eine Spalte `end` — in SQL ein reserviertes
Wort —, und `states.old_state_id` zeigt auf dieselbe Tabelle. Das Skript
stellt die Fremdschlüssel für die Dauer der Transaktion zurück und zieht
anschließend die Sequenzen nach.

## Matter war schon vorher kaputt

Der Matter-Server lud nach dem Einspielen null Knoten, obwohl im
Geräteregister 18 Matter-Geräte stehen. Die Ursache liegt nicht am Umzug:

- Der Speicher des Servers heißt nach der *compressed fabric id*. Im Backup
  liegen zwei solcher Dateien: `16469315225219412808.json` mit 18 Knoten,
  zuletzt geschrieben am **6. September 11:01**, und
  `1241080542531001858.json` ohne einen einzigen Knoten, geschrieben am
  **6. September 21:37**.
- `chip.json` verzeichnet nur noch eine Fabric (`fabricId 2`,
  `vendorId 4939`) — und die zeigt auf die leere Datei.
- Die Historie bestätigt es: Alle 143 Matter-Entitäten gingen am
  **6. September um 23:35** auf `unavailable` und kamen nie zurück.

Am 6. September hat der Server also eine neue Fabric angelegt und die alte
verwaist. Der Schlüssel der alten Fabric steckt nicht mehr in `chip.json`; die
18 Geräte lassen sich daraus nicht zurückholen. Sie müssen neu angelernt
werden.

## Piper entfällt

Das Add-on war installiert, der Wyoming-Eintrag in HA steht aber auf
`source: "ignore"` — Piper wurde nie eingebunden, TTS läuft über
`google_translate`. Ein eigenes Deployment wäre Ballast gewesen.

## Was in der Konfiguration auffiel

Drei Dinge, die auf dem Pi schon schief lagen:

- `configuration.yaml` band `homekit: !include homekit.yaml` ein, aber
  `homekit.yaml` begann selbst mit `homekit:`. Doppelt verschachtelt fiel der
  Abschnitt durch die Prüfung; die beiden Bridges laufen aus ihren
  Config-Entries. Der Einbindung wurde deshalb gestrichen.
- `rest.yaml` schrieb `Authorization: "Bearer !secret ha_token"`. In
  Anführungszeichen wertet Home Assistant den Tag nicht aus — der Sensor
  schickte den Text wörtlich. Der vollständige Header liegt jetzt als
  `ha_auth_header` im Secret.
- `automations.yaml` hat in einer Automation den Schlüssel `mode` doppelt
  (Zeilen 536/537). Home Assistant warnt beim Start darüber.
