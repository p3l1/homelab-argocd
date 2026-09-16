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

## Warum 196 Entitäten nicht verfügbar sind

Nach dem Umzug meldeten 196 von 411 Entitäten `unavailable`. Im Backup waren
es 203 — der Umzug hat die Lage also nicht verschlechtert. Aufgeschlüsselt
nach Integration:

| Anzah| Integration | Ursache |
|---:|---|---|
| 143 | `matter` | verwaiste Fabric, siehe unten |
| 18 | `homekit_controller` | drei von vier Eve Thermo außer Bluetooth-Reichweite |
| 6 | `hassio` | Supervisor gibt es im Container nicht, bewusst deaktiviert |
| 6 | ohne Eintrag | Reste gelöschter Integrationen |
| 6 | `unifi` | Geräte, die gerade nicht im Netz sind |
| 5 | `xiaomi_ble` | BLE-Sensoren außer Reichweite |
| 4 | `mobile_app` | Telefone ohne Verbindung |
| 3 | `fritz`, 3 `plant`, 2 Pi-Hardware | teils offline, teils bewusst abgeschaltet |

Zwei davon lohnen den genaueren Blick, und beide gehen auf denselben Abend
zurück: Am **6. September um 23:35** gingen 143 Matter-Entitäten und drei der
vier Thermostate gleichzeitig auf `unavailable` — sichtbar in der Historie,
also lange vor dem Umzug.

### Die Eve Thermostate hängen an Bluetooth, nicht an Thread

Naheliegend wäre Thread gewesen. Die Pairings sagen etwas anderes: In allen
vier Config-Entries steht `"Connection": "BLE"`. Ein Scan über die
`bluetooth`-Integration findet 35 Geräte, darunter genau eines der vier:

```
DA:16:85:02:E0:A2  rssi=-52  Eve Thermo BD54     gefunden
C5:4C:3A:8D:E0:4C                                fehlt
E0:A3:95:97:30:6A                                fehlt
FC:EC:0C:83:9B:11                                fehlt
```

Der Adapter steckt am Rack, wo vorher der Pi 5 stand. Drei Thermostate liegen
außerhalb seiner Reichweite oder haben leere Batterien. Abhilfe: Batterien
prüfen, und falls die Reichweite das Problem ist, einen ESPHome-Bluetooth-Proxy
in ihre Nähe stellen — die `bluetooth`-Integration nimmt dessen Funde
entgegen, ohne dass sich an der Einrichtung hier etwas ändert.

### Das Thread-Netz steht, aber die Zugangsdaten sind veraltet

Der Node kennt die Route ins Thread-Netz — sie kommt per Router Advertisement
von den beiden Apple-TV-Border-Routern:

```
fd2a:dd59:adbf::/64 proto ra  nexthop via fe80::...  dev eth0  (3 Border Router)
```

Über mDNS melden beide dasselbe Netz, das auch in Home Assistant steht:
`MyHome2132015047`, Extended PAN ID `daae142a100f44d6`. Name und PAN-ID passen
also — die hinterlegten Zugangsdaten trotzdem nicht, weshalb das Teilen mit
„Thread network credentials does not match with any of the active thread
networks around" scheitert.

Nachweisbar veraltet ist der Datensatz an einer anderen Stelle: Er stammt vom
26. Mai und nennt als bevorzugten Border Agent `d26e27d8c452b71f`. Im Netz
sind heute `baf13c7c9ffcca50` (Schreibtisch) und `52b08664bc6efd5d`
(Fernseher) — der dritte ist verschwunden. Als Active Timestamp führen beide
Seiten 0, Apple setzt ihn nicht; über den lässt sich nichts vergleichen.
Welches Feld genau abweicht, verrät Apple nicht — dem Ablauf nach ist es der
Netzwerkschlüssel.

Zu beheben in der **Home-Assistant-App auf dem iPhone**: Einstellungen →
Geräte & Dienste → Thread → *Zugangsdaten des Thread-Netzwerks importieren*.
Das holt den aktuellen Schlüssel aus dem Apple-Schlüsselbund. Der umgekehrte
Weg — Home Assistants Datensatz in den Schlüsselbund schreiben — ist der, der
die Fehlermeldung erzeugt.

Das muss **vor** dem Neuanlernen der Matter-Geräte geschehen: Ohne gültigen
Schlüssel kann der Matter-Server kein Thread-Gerät in Betrieb nehmen.

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

## Der Reverse Proxy steht nicht mehr in der YAML

Der erste Zugriff über Traefik endete mit `400 Bad Request` und
„Received X-Forwarded-For header from an untrusted proxy 10.35.99.214".

Zwei Dinge dahinter:

- Durch `hostNetwork` sieht Home Assistant nicht die Adresse des Traefik-Pods,
  sondern die des Nodes, auf dem er läuft. Zum Pod-Netz muss deshalb
  `10.35.99.0/24` dazu.
- Home Assistant 2026.8 hat den `http:`-Abschnitt nach `.storage/http`
  übernommen (`"yaml_migration_done": true`) und liest die YAML dafür nicht
  mehr. Der Abschnitt wurde deshalb aus `configuration.yaml` entfernt.

Geändert wird das über die WebSocket-API bzw. Einstellungen → System →
Netzwerk: `http/config/configure` legt die Fassung als `pending` ab und
startet neu, `http/config/promote` macht sie zu `stable`. Die Datei direkt zu
bearbeiten funktioniert nicht — beim Beenden schreibt Home Assistant seinen
eigenen Stand zurück.

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
