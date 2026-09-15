# Home Assistant

Umgezogen vom abgelösten Raspberry Pi 5 (HA OS) in den Cluster. Läuft fest auf
dem Node mit dem Label `homelab.p3l1.de/workload=home` — dort steckt der
Bluetooth-Adapter.

## Warum `hostNetwork`

HomeKit-Bridge, Sonos, Apple TV und Thread finden ihre Gegenstellen über mDNS
und SSDP. Beides bleibt im Pod-Netz stecken. Dieselbe Begründung gilt für den
Matter-Server: Matter spricht ausschließlich IPv6 und arbeitet mit
Link-Local-Adressen.

Folge davon: Der Node braucht Vorbereitung, die in der Ansible-Rolle
`node_base` steht und über zwei Schalter im Inventar angefordert wird.

| Schalter | Wirkung |
|---|---|
| `node_bluetooth: true` | BlueZ bleibt installiert, `dtoverlay=disable-bt` entfällt, eine Unit hebt die rfkill-Sperre auf |
| `node_ipv6: true` | `method6` des NetworkManager-Profils steht auf `auto` statt `disabled` |

## Konfiguration

Zweigleisig. Was unter `config/hass/` liegt, kommt als ConfigMap read-only
nach `/config/iac` in den Pod:

```
automation git: !include iac/automations.yaml   # aus diesem Verzeichnis
automation ui:  !include automations.yaml       # vom UI-Editor beschrieben
```

Home Assistant schreibt ausschließlich nach `/config/automations.yaml`,
`scripts.yaml` und `scenes.yaml`. Der UI-Editor bleibt damit benutzbar; was
dort entsteht, gehört anschließend hierher ins Repository.

`configuration.yaml` wird vom Init-Container **kopiert**, nicht verlinkt:
`!include` löst relativ zum Namen der einlesenden Datei auf, und ein Symlink
behielte `/config/configuration.yaml` als Namen — die Pfade zeigten dann ins
Leere.

Nach einer Änderung an `config/hass/` prüft und lädt die Pipeline aus
`tekton/` die Konfiguration neu. `configuration.yaml` selbst braucht einen
Neustart des Pods, die übrigen Dateien nicht.

### Was nicht ins Repository kann

`.storage` (Geräte-, Entitäts- und Benutzerregister, Tokens, API-Schlüssel),
`custom_components` (65 MB, von HACS verwaltet) und `deps`. Das ist
Laufzeitzustand und liegt im Longhorn-Volume.

Dazu gehört seit 2026.8 auch die **HTTP-Konfiguration**: Home Assistant hat
den `http:`-Abschnitt nach `.storage/http` übernommen und liest ihn seitdem
von dort — ein `http:` in der YAML bleibt wirkungslos. Dort stehen die
vertrauenswürdigen Proxys: `10.42.0.0/16` für das Pod-Netz und
`10.35.99.0/24`, weil `hostNetwork` die Adresse des Nodes durchreicht, auf
dem Traefik oder Newt läuft, und nicht die des Pods.

Geändert wird das unter Einstellungen → System → Netzwerk. Die Datei von Hand
zu bearbeiten geht schief: Home Assistant schreibt seinen Stand beim Beenden
zurück. Der Ablauf ist zweistufig — die neue Fassung landet erst als
`pending`, ein Neustart probiert sie aus, und erst das Festschreiben macht sie
zu `stable`. Nur `stable` benutzt der Wiederherstellungsmodus.

## Datenbank

Der Recorder liegt auf CloudNativePG (`home-assistant-db`, zwei Instanzen).
Die Verbindung kommt über `HA_DB_URL` aus dem `uri`-Schlüssel des von CNPG
erzeugten Secrets — `configuration.yaml` liest sie mit `!env_var`.

Zwei Instanzen statt drei wie bei Paperless: Der Recorder schreibt jeden
Zustandswechsel mit, eine dritte Replik kostet mehr Schreiblast, als sie an
Sicherheit bringt.

## Erreichbarkeit

| Weg | Adresse |
|---|---|
| im LAN | `https://home.homelab.internal` über die `HTTPRoute` |
| von außen | `https://home.cloud.p3l1.de`, **private** Pangolin-Ressource |

Privat heißt: nur mit aktivem Pangolin-Client erreichbar, nie aus dem offenen
Netz. Kein vorgeschaltetes SSO — Home Assistant meldet selbst an, über
Pocket ID via `auth_oidc`. Ein zweiter Anmeldebildschirm davor würde die
Companion-App und alle Webhooks aussperren.

Praktische Folge: Ohne laufenden Olm-Client erreicht das Telefon von unterwegs
weder Standortmeldungen noch Push.

## Matter

`matter-server` ersetzt das Add-on `core_matter_server`. Version 8.1.2, weil
das Add-on 8.4.0 laut seinem Changelog genau diesen Python Matter Server fuhr.
Die Parameter `--fabricid 2 --vendorid 4939` stehen so in der
wiederhergestellten `chip.json` (`caList`); mit der Voreinstellung landet der
Server in einer zweiten, leeren Fabric.

Ab Add-on 9.0.0 steht matter.js dahinter und migriert die Daten selbst. Der
Umstieg ist ein eigener Schritt.
