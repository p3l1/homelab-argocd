# Secrets

SOPS-verschlüsselt mit dem PGP-Schlüssel `7954EC02CDDF896536DFDCDE056C6FDDF9E15CF2`.
Verschlüsselt wird nur `data`/`stringData` — Art, Name und Namensraum bleiben
lesbar, sodass Diffs aussagekräftig sind.

Diese Secrets verwaltet **nicht** ArgoCD; sie werden einmalig von Hand
angewandt:

```bash
sops -d secrets/<datei>.sops.yaml | kubectl apply -f -
```

| Datei | Zweck |
|---|---|
| `arcane-secrets.sops.yaml` | `ENCRYPTION_KEY` und `JWT_SECRET` für Arcane |
| `newt-credentials.sops.yaml` | Zugangsdaten für den Pangolin-Tunnel |

`newt-credentials` fehlt noch — die Werte kommen aus Pangolin.
