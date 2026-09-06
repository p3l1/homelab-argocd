# Secrets

SOPS-verschlüsselt mit dem PGP-Schlüssel `7954EC02CDDF896536DFDCDE056C6FDDF9E15CF2`.
Verschlüsselt wird nur `data`/`stringData` — Art, Name und Namensraum bleiben
lesbar, sodass Diffs aussagekräftig sind.

Diese Secrets verwaltet **nicht** ArgoCD; sie werden einmalig von Hand
angewandt:

```bash
sops -d secrets/<datei>.sops.yaml | kubectl apply -f -
```

## Ein neues Secret anlegen

`scripts/secret.sh` fragt die Werte einzeln ab (ohne sie anzuzeigen), legt das
Secret im Cluster an und hinterlegt es verschlüsselt hier:

```bash
./scripts/secret.sh newt-credentials newt PANGOLIN_ENDPOINT NEWT_ID NEWT_SECRET
```

Existiert die Datei bereits, übernimmt ein leeres Eingabefeld den bisherigen
Wert — so lassen sich einzelne Schlüssel nachtragen, ohne die übrigen erneut
einzugeben.

| Datei | Zweck |
|---|---|
| `arcane-secrets.sops.yaml` | `ENCRYPTION_KEY` und `JWT_SECRET` für Arcane |
| `newt-credentials.sops.yaml` | Zugangsdaten für den Pangolin-Tunnel |
| `unifi-credentials.sops.yaml` | API-Schlüssel des Routers für external-dns |

`newt-credentials` fehlt noch — die Werte kommen aus Pangolin.
