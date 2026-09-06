# Arcane

Verwaltet die Docker-Hosts ausserhalb des Clusters. Der Docker-Socket wird
**nicht** eingehängt — die Hosts melden sich über den Arcane-Agent
(`ghcr.io/getarcaneapp/agent`), der von dort nach aussen verbindet.

Zwei Volumes: `arcane-data` für die Anwendungsdaten, `arcane-backups` für die
Sicherungen. Getrennt, damit die Backups unabhängig wachsen können.

Das Secret `arcane-secrets` (`encryption-key`, `jwt-secret`, je 32 Zeichen)
liegt SOPS-verschlüsselt unter `secrets/` und wird von Hand angewandt:

```bash
sops -d secrets/arcane-secrets.sops.yaml | kubectl apply -f -
```
