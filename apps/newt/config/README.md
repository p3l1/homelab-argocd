# Newt

Die Zugangsdaten für den Pangolin-Endpunkt liegen **nicht** hier: Das Secret
`newt-credentials` wird von Hand angelegt, SOPS-verschlüsselt im Repo unter
`secrets/` und nicht von ArgoCD verwaltet.

```bash
sops -d secrets/newt-credentials.secret.yaml | kubectl apply -f -
```

In diesem Verzeichnis stehen später die `Service`-Objekte der Dienste, die
durch den Tunnel erreichbar sein sollen.
