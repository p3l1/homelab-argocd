# Newt

Die Zugangsdaten für den Pangolin-Endpunkt liegen **nicht** hier: Das Secret
`newt-credentials` wird von Hand angelegt und SOPS-verschlüsselt unter
[`secrets/`](../../../secrets) abgelegt:

```bash
./scripts/secret.sh newt-credentials newt PANGOLIN_ENDPOINT NEWT_ID NEWT_SECRET
```

## services/

`ExternalName`-Dienste, über die Newt die Anwendungen erreicht. Sie liegen im
Namensraum `newt` und verweisen auf den eigentlichen Dienst — Newt kennt so
nur einen Namen je Anwendung, unabhängig davon, in welchem Namensraum sie
läuft.

| Dienst | Ziel | Port |
|---|---|---|
| `newt-argocd-service` | `argocd-server.argocd` | 443 |
| `newt-paperless-service` | `paperless-ngx.paperless` | 8000 |
| `newt-umami-service` | `umami.umami` | 3000 |
| `newt-arcane-service` | `arcane.arcane` | 3552 |
| `newt-whoami-service` | `whoami.whoami` | 80 |
| `newt-tekton-service` | `tekton-dashboard.tekton-pipelines` | 9097 |
