# external-dns

**Derzeit nicht ausgerollt.** Die Datei `overlays/infrastructure/config.json`
ist nach `config.json.disabled` umbenannt, damit der Generator des Projekts
sie nicht findet.

## Grund

Der Webhook spricht die UniFi Network Integration API und braucht dafür einen
API-Schlüssel; Benutzername und Passwort akzeptiert er ausdrücklich nicht.
Diese Schlüssel gibt es erst ab **UniFi OS 4.1 / Network 9.0** — der Express
läuft auf **4.0.17**, wo der Menüpunkt fehlt.

## Wieder einschalten

Nach dem Update des Routers (Console Settings → Updates):

```bash
mv apps/external-dns/overlays/infrastructure/config.json.disabled \
   apps/external-dns/overlays/infrastructure/config.json
./scripts/secret.sh unifi-credentials external-dns UNIFI_HOST UNIFI_API_KEY
```

Den Schlüssel gibt es dann unter Settings → Control Plane → Admins & Users →
Benutzer → Control Plane API Key. `UNIFI_HOST` ist `https://10.35.99.1`.

## Solange von Hand

Im Router unter Settings → Routing & Firewall → DNS → Local DNS Records, alle
auf die Adresse des Traefik-Gateway:

| Name | Ziel |
|---|---|
| `argocd.homelab.internal` | `10.35.99.230` |
| `paperless.homelab.internal` | `10.35.99.230` |
| `umami.homelab.internal` | `10.35.99.230` |
| `arcane.homelab.internal` | `10.35.99.230` |
| `whoami.homelab.internal` | `10.35.99.230` |
