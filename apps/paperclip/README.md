# Paperclip

Agenten-Harness unter `https://paperclip.cloud.p3l1.de`. Hermes (`apps/hermes`)
ist dort als Agent mit dem Adapter `hermes_gateway` eingebunden.

## Zugang

Zwei Schranken hintereinander:

1. Pangolin-SSO (Pocket ID, Rolle `Member`).
2. Paperclips eigenes Login mit E-Mail und Passwort. OIDC kann Paperclip
   (Stand `2026.1005.0`) nicht.

Neue Konten sind gesperrt (`PAPERCLIP_AUTH_DISABLE_SIGN_UP`). Weitere Menschen
kommen über einen Invite aus dem Board hinzu.

Den ersten Admin legt ein Bootstrap-Invite an. Die CLI braucht dafür eine
Konfigurationsdatei, der Server läuft aber nur mit Umgebungsvariablen:

```bash
kubectl -n paperclip exec deploy/paperclip -- gosu node sh -c 'cd /app &&
  echo "{\"\$meta\":{\"version\":1,\"updatedAt\":\"2026-01-01T00:00:00Z\",\"source\":\"onboard\"},
  \"database\":{\"mode\":\"postgres\"},\"logging\":{\"mode\":\"file\"},
  \"server\":{\"deploymentMode\":\"authenticated\",\"exposure\":\"public\",\"host\":\"0.0.0.0\",\"port\":3100},
  \"auth\":{\"baseUrlMode\":\"explicit\",\"publicBaseUrl\":\"https://paperclip.cloud.p3l1.de\"}}" > /tmp/b.json &&
  pnpm -s paperclipai auth bootstrap-ceo --config /tmp/b.json [--force]; rm -f /tmp/b.json'
```

## Hermes als Agent

Beide Richtungen haben einen eigenen Schlüssel:

| Richtung | Weg | Schlüssel |
|---|---|---|
| Paperclip → Hermes | `http://hermes.hermes.svc:8642` (`/v1/runs`, SSE) | `API_SERVER_KEY` aus `hermes-secrets`, in Paperclip verschlüsselt abgelegt |
| Hermes → Paperclip | `http://paperclip.paperclip.svc:3100/api` | Agent-Key aus dem Join, steht in `/opt/data/.env` im Hermes-Volume |

Port 8642 ist per NetworkPolicy nur aus dem Namespace `paperclip`
erreichbar. Der Verkehr ist Klartext-HTTP, darum braucht der Adapter
`dangerouslyAllowInsecureRemoteHttp: true`. Er verlässt den Cluster nicht.

Den Agent neu verbinden (etwa nach Verlust des Hermes-Volumes):

1. Im Board einen Agent-Invite erzeugen.
2. `paperclip-join.py accept <invite-token>` im Hermes-Pod ausführen.
   Das Skript liest den `API_SERVER_KEY` dort aus der Umgebung.
3. Den Join-Request im Board freigeben.
4. `paperclip-join.py claim` im Hermes-Pod ausführen. Das Skript schreibt
   `PAPERCLIP_API_URL` und `PAPERCLIP_API_KEY` nach `/opt/data/.env`.
5. Hermes neu starten.

```bash
kubectl -n hermes exec -i deploy/hermes -c hermes -- python3 - accept <token> < apps/paperclip/scripts/paperclip-join.py
```

## Daten

- Postgres über CloudNativePG (`paperclip-db`), eine Instanz.
- `/paperclip` auf Longhorn: Anhänge, Instanzdaten und Paperclips eigene
  stündliche DB-Dumps (`instances/default/data/backups`, 7 Tage).

## Offen

- Keine Sicherung außerhalb des Clusters; die Dumps liegen auf demselben Longhorn.
- Klartext-HTTP zwischen Paperclip und Hermes. Der Ausweg wäre ein TLS-Proxy vor der Hermes-API.
