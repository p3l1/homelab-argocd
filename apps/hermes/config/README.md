# Hermes

Agent von Nous Research, erreichbar über das Dashboard unter
`hermes.cloud.p3l1.de` und über Signal. Ein Pod, zwei Container: Hermes selbst
und ein `signal-cli`-Daemon als Sidecar.

Nur **ein** Pod, immer. Zwei Gateways auf demselben Datenverzeichnis zerstören
den Zustand, darum `replicas: 1` und `strategy: Recreate`.

## Das Modell kommt aus dem Claude-Abo

Das offizielle Plugin
[`claude-subscription-directsdk`](https://github.com/NousResearch/hermes-plugin-claude-subscription-directsdk)
treibt die unveränderte Claude-Code-CLI als Modell-Client; Hermes behält Tools,
Erinnerungen und Freigaben. Weder CLI noch Plugin stecken im Image, deshalb
legt der initContainer `claude-cli` beides bei jedem Start auf dem Volume ab.

Die Anmeldung braucht ein TTY und ist ein einmaliger Handgriff:

```bash
kubectl -n hermes exec -it deploy/hermes -- /opt/data/home/.npm-global/bin/claude
# dort /login
```

Danach erneuert die CLI ihr Token selbst. Jeder Zug zieht gegen das
Agent-SDK-Kontingent des Abos, zur Rate von `claude -p` — laut Doku etwa
1,7-fach gegenüber der interaktiven Nutzung. Das Plugin heißt ausdrücklich
„Experimental"; fällt der Weg aus, stellt `hermes model` auf den
`ANTHROPIC_API_KEY` aus demselben Secret um.

## Signal läuft als verknüpftes Gerät

Der Sidecar hält den Daemon auf `127.0.0.1:8080` — nur innerhalb des Pods
erreichbar, deshalb auch ohne Probe. Das Image stammt aus
[`p3l1/docker-signal-cli`](https://github.com/p3l1/docker-signal-cli): Upstream
bündelt die native libsignal nur für x86_64, auf arm64 muss sie nachgezogen
werden.

Bis zur Verknüpfung bricht der Daemon ab; eine Schleife im Sidecar hält den
Container deshalb am Leben, sonst wäre der nötige `exec` nicht möglich. Das
Verknüpfen kommt also **nach** dem ersten Sync — der QR-Code erscheint im
Terminal:

```bash
kubectl -n hermes exec -it deploy/hermes -c signal-cli -- \
  signal-cli --config /data/signal-cli link -n HermesAgent
```

Gesprochen wird über „Nachricht an mich" — Hermes hängt als Zweitgerät am
eigenen Konto. Das heißt auch: **der gesamte Signal-Eingang läuft durch den
Hermes-Prozess.** Die Allowlist steuert, auf wen er antwortet, nicht, was er
sieht. Und die Anmeldung lebt allein auf dem Volume: ist es weg, muss das
Gerät neu verknüpft werden.

## Pocket ID

Das Dashboard verweigert den Start, sobald es auf einer Nicht-Loopback-Adresse
lauscht und kein Auth-Provider steht. Hier ist das Pocket ID als **öffentlicher
PKCE-Client ohne Secret**, Callback `https://hermes.cloud.p3l1.de/auth/callback`,
beschränkt auf die Gruppe `hermes_admins`. Clients legt nur die REST-API
zuverlässig an, nicht der Dialog in der Oberfläche.

Greift `HERMES_DASHBOARD_PUBLIC_URL` hinter Pangolin nicht
([#42780](https://github.com/NousResearch/hermes-agent/issues/42780)), ist
`HERMES_DASHBOARD_BASIC_AUTH_USERNAME`/`_PASSWORD` der Rückfall.

## Rechte

`ServiceAccount hermes` mit der eingebauten ClusterRole `view`: lesender
Zugriff auf den Cluster einschließlich `pods/log`, ohne Secrets. ConfigMaps
schließt `view` mit ein — soll das auch raus, braucht es eine eigene Rolle.

Im Container selbst darf der Agent alles: Shell, Browser, Netz. Eine
NetworkPolicy, die nur API-Server, DNS und ausgehendes HTTPS zulässt, ist noch
nicht gesetzt.

## Secret

```bash
./scripts/secret.sh hermes-secrets hermes \
  SIGNAL_ACCOUNT OIDC_CLIENT_ID API_SERVER_KEY ANTHROPIC_API_KEY
```

`SIGNAL_ACCOUNT` ist die eigene Nummer in E.164 und versorgt auch
`SIGNAL_ALLOWED_USERS` und `SIGNAL_HOME_CHANNEL`; sie steht im Secret, damit
sie nicht im öffentlichen Repository landet. Das Secret muss **vor** dem ersten
Sync liegen, sonst bleibt der Pod in `CreateContainerConfigError`.
