# Regenalarm für den Arbeitsweg

Meldet über Gotify, wenn werktags auf dem Weg Bornheimer Straße 144 →
Konrad-Zuse-Platz Regen vorhergesagt ist.

Entwurf und Plan: `docs/superpowers/specs/2026-09-16-regenalarm-arbeitsweg-design.md`

## Woher die Daten kommen

Das Radarkomposit **RV** des DWD, alle fünf Minuten neu, 25 Zeitschritte bis
+2 Stunden im 1-km-Raster:

```
https://opendata.dwd.de/weather/radar/composite/rv/DE1200_RV<JJMMTThhmm>.tar.bz2
```

Das sind dieselben Daten, die hinter jedem deutschen Regenradar stecken —
Wetteronline eingeschlossen, das automatisierte Abrufe mit 403 beantwortet.

## Die Seite

Unter `/` liegt die Bedienseite: **Datumswahl plus Zeitregler** über den
gewählten Tag. 30 Tage sind 8640 Zeitschritte — ein einzelner Regler dafür
wäre unbedienbar. Vor/Zurück, Abspielen, „Zurück zu jetzt"; Pfeiltasten und
Leertaste bedienen mit.

Das Bild beschriftet sich als **„Gemessen — vor 3 Tagen"** oder
**„Vorhersage — in 45 Minuten"**. Beim Blick zurück darf keine Prognose
vorgetäuscht werden.

## Die Ablage

30 Tage Beobachtung in einer SQLite-Datei auf einem Longhorn-Volume, rund
10 MB. **Kein PostgreSQL:** Ein Treiber wäre die erste Laufzeitabhängigkeit
überhaupt und bräuchte ein eigenes Image — für 10 MB, die sich jederzeit aus
dem DWD-Archiv wiederherstellen lassen.

Zwei Quellen speisen sie:

- **RV** liefert die Gegenwart. Das Verzeichnis reicht nur zwei Tage zurück.
- **YW** aus dem Klimaarchiv liefert alles Ältere — 1098 Tagesdateien, je 288
  Schritte. Der Nachlauf holt fehlende Tage einzeln im Hintergrund, damit der
  Dienst benutzbar bleibt; ein Tag dauert rund drei Sekunden.

YW liegt auf dem **900×900-Gitter mit Kugelerde**, nicht auf DE1200. Beim
Einlesen wird es über eine feste Zuordnungstabelle umgerechnet, sonst lägen
Vergangenheit und Vorhersage um Hunderte Meter auseinander. Geprüft an einem
Punkt, der in beiden Gittern gleich fallen muss: Bonn liegt 23,8 km südlich
und 7,8 km östlich von Köln — in DE1200 wie in RADOLAN-900.

YW ist geeicht, RV eine reine Radarschätzung. Zwischen Vergangenheit und
Gegenwart sind deshalb kleine Sprünge möglich; beide Größen sind mm je fünf
Minuten.

Zwei Kniffe halten das leichtgewichtig:

- **Der Ausschnitt wird beim Laden zugeschnitten.** 49 volle Zeitschritte
  wären 130 MB; gebraucht werden 24 × 24 Zellen, also 400 Werte statt 1,32
  Millionen. `Composite.crop()` behält dabei die globalen Koordinaten, damit
  der Rest des Programms nichts davon wissen muss.
- **Die Karte liegt auf der Seite als eigenes Bild**, die Zeitschritte kommen
  als `radar.svg?t=<minuten>&bare=1` ohne eingebettete Karte — rund 2 kB statt
  186. Sonst würde jeder Reglerschritt 138 kB Karte neu laden.

Der Link aus der Gotify-Nachricht zeigt weiter auf `radar.svg` **mit**
eingebetteter Karte: Er muss für sich allein funktionieren.

## Die Nachricht

Der Exporter verschickt die Regenmeldung **selbst**, nicht über eine
Alarmregel. Grund ist der Text: Eine VMRule kann nur `$value` einsetzen und
käme über „bis zu 0,3 mm pro 5 Minuten" nicht hinaus — eine Einheit, die
niemand im Kopf hat, ohne Anfang und ohne Dauer. Der Exporter kennt alle 25
Zeitschritte und formuliert daraus:

> **Regen ab 07:20 — mäßiger Regen**
> Ab 07:20 fällt auf dem Arbeitsweg mäßiger Regen, bis etwa 07:50 (30 Minuten).
> Spitze 6 mm/h.

Der Titel allein trägt die Entscheidung; er ist alles, was auf dem
Sperrbildschirm sicher ankommt. Gemeldet wird **einmal je Pendelfenster**.

Der Versand läuft über die vorhandene `alertmanager-gotify-bridge`, nicht
direkt zu Gotify: Dort liegt der App-Token bereits, und so bleibt er an genau
einer Stelle im Cluster. Preis dafür ist unformatierter Text — die Bridge
reicht Markdown nicht durch.

In der VMRule steht deshalb nur noch `StaleRadarData`. Die Betriebsüberwachung
gehört ins Monitoring, die Regenmeldung in die Anwendung.

## Die Karte

Das Bild liegt auf einer echten Karte, nicht auf schwarzem Grund. Sie wurde
**einmalig** aus OpenStreetMap gerendert, auf das DE1200-Raster reprojiziert
(Web-Mercator und polarstereografisch decken sich nicht) und abgedunkelt.
`src/karte.webp` kommt als `binaryData` in dieselbe ConfigMap und wird als
Data-URI ins SVG eingebettet — kein Kartendienst zur Laufzeit, keine
Nachladeabhängigkeit im Bild.

Die Karte ist **1536 px breit bei 640 Anzeigepixeln**, damit sie beim Zoomen
scharf bleibt. WebP mit Qualität 80 statt PNG: ein Fünftel der Dateigröße
(138 statt 662 kB), und die Ortsnamen überstehen das sichtbar unbeschadet.
Ohne diesen Faktor 2,4 verschwimmt die Karte, sobald man hineinzoomt.

Die Regenzellen bleiben dabei bewusst kantig — 1 km ist die Auflösung des
Radars, und eine Glättung würde Genauigkeit vortäuschen, die die Daten nicht
hergeben.

Neu erzeugen mit `tools/build_karte.py`, nötig bei geänderter Route oder
geändertem Ausschnitt. Das Werkzeug braucht Pillow und pyproj — der Exporter
selbst kennt beide nicht.

Die Farbskala bricht bei Starkregen bewusst aus dem Blau aus: Gelb und Rot
liest man als „heute lieber Bahn", helleres Blau nicht.

## Warum kein eigenes Image

Der Exporter kommt mit der Standardbibliothek aus, deshalb genügt ein
`python:3.13-slim` mit dem Code aus einer ConfigMap. Zwei Entscheidungen
erkaufen das:

- **Die Projektion ist von Hand gerechnet.** Rund 25 Zeilen statt `pyproj`,
  gegen dieses über 2000 Zufallspunkte geprüft: 0,000000 m Abweichung.
- **Das Kartenbild ist SVG.** Ein Raster aus `<rect>` ist Text; `Pillow`
  wäre nur für die Bildkodierung nötig gewesen.

Der Namenshash des `configMapGenerator` rollt das Deployment bei jeder
Code-Änderung neu aus.

## Die zwei Fallstricke

**Die Zeilenachse des DE1200-Gitters zählt nach Süden.** Zeile 0 liegt im
Norden, `zeile = -y/1000`. Kursierende Codebeispiele rechnen teils andersherum.

**Die Zeitfenster liegen im Exporter, nicht in PromQL.** `hour()` rechnet in
UTC — 07:00 Berliner Zeit ist im Sommer 05:00 UTC und im Winter 06:00. Eine
Regel darauf wäre ein halbes Jahr lang unauffällig falsch. Der Exporter kennt
`Europe/Berlin` und liefert `commute_window_active` fertig als 0/1.

## Metriken

| Metrik | Bedeutung |
|---|---|
| `commute_rain_forecast_mm{horizon_min="0".."120"}` | Regen auf der Route je Horizont, mm/5 min |
| `commute_rain_expected_mm` | Maximum über die Horizonte 0–45 min |
| `commute_window_active` | 1, während ein Pendelfenster läuft |
| `commute_radar_age_seconds` | Alter des jüngsten Radarbilds |

Der Service heißt seinen Port `metrics`; allein deshalb greift ihn die
`k8s-endpoints`-Discovery des OTel-Gateways ab. `StaleRadarData` warnt, wenn
die Daten altern — ein stiller Exporter wäre sonst von schönem Wetter nicht zu
unterscheiden.

## Stellschrauben

Alles in `base/src/commute.py`: `WINDOWS` (Pendelzeiten), `TRAVEL_MINUTES`
(Fahrtdauer samt Puffer), `ROUTE_CELLS` (die elf Rasterzellen). Die
Regenschwelle steht bewusst nur in `base/vmrule.yaml` — dort lässt sie sich
ohne Pod-Neustart ändern.

## Dashboard

`Regenalarm → Regenalarm Arbeitsweg` in Grafana. Das Dashboard liegt beim
Grafana-Operator (`apps/grafana-operator/base/dashboard-regenalarm.yaml`), nicht
hier — dort stehen alle anderen auch.

## Tests

```bash
cd apps/rain-commute && python -m pytest tests/ -v
```

31 Tests, ohne Netzzugriff: Die Fixtures bauen synthetische Komposit-Dateien.
Echte Radardateien sind 2,6 MB groß und gehören nicht ins Repository.
