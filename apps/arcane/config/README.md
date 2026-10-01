# Arcane

Verwaltet die Docker-Hosts ausserhalb des Clusters. Der Docker-Socket wird
**nicht** eingehängt — die Hosts melden sich über den Arcane-Agent
(`ghcr.io/getarcaneapp/agent`), der von dort nach aussen verbindet.

Zwei Volumes: `arcane-data` für die Anwendungsdaten, `arcane-backups` für die
Sicherungen. Getrennt, damit die Backups unabhängig wachsen können.

Die Hosts richtet die Ansible-Rolle `arcane_agent` ein, siehe
[`../../../ansible/README.md`](../../../ansible/README.md). Das Token je Host
erzeugt der Manager beim Anlegen des Environments — der Agent allein kann
sich nicht anmelden.

`ADMIN_STATIC_API_KEY` hält einen festen Admin-API-Key für die REST-API
vor. Arcane legt ihn beim Start an, rotiert ihn bei geändertem Wert und
entfernt ihn, wenn die Variable wegfällt. Er hat Vollzugriff und gehört
nicht in Werkzeuge, denen ein eigener Schlüssel genügt.

Der Wert muss mit `arc_` beginnen und mindestens zwölf Zeichen haben, sonst
verwirft Arcane ihn beim Start mit `Failed to reconcile default admin API
key` und jede Anfrage bleibt bei `401`:

```bash
printf 'arc_%s\n' "$(openssl rand -hex 32)"
```

Das Secret `arcane-secrets` (`encryption-key`, `jwt-secret`, je 32 Zeichen)
liegt SOPS-verschlüsselt unter `secrets/` und wird von Hand angewandt:

```bash
sops -d secrets/arcane-secrets.sops.yaml | kubectl apply -f -
```
