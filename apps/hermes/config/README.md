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
1,7-fach gegenüber der interaktiven Nutzung.

**`ANTHROPIC_API_KEY` darf dabei nicht in der Umgebung stehen.** Die CLI nimmt
einen Key aus der Umgebung und meldet dann „Invalid API key · Fix external API
key", statt zur Anmeldung zu kommen; ohne ihn sagt sie „Not logged in · Please
run /login". Der Wert liegt im Secret, aber nicht im Deployment — wer vom
Abo-Weg auf Abrechnung pro Token wechseln will, trägt die Variable dort wieder
ein und stellt `hermes model` um. Das Plugin heißt ausdrücklich „Experimental".

## Signal hat ein eigenes Konto

Der Sidecar hält den Daemon auf `127.0.0.1:8080` — nur innerhalb des Pods
erreichbar, deshalb auch ohne Probe. Das Image stammt aus
[`p3l1/docker-signal-cli`](https://github.com/p3l1/docker-signal-cli): Upstream
bündelt die native libsignal nur für x86_64, auf arm64 muss sie nachgezogen
werden.

Hermes hat eine **eigene Nummer**, kein verknüpftes Gerät an einem fremden
Konto. Damit sieht er ausschließlich seine eigenen Unterhaltungen. Man schreibt
ihm wie jedem anderen Kontakt; `SIGNAL_ALLOWED_USERS` entscheidet, wem er
antwortet, `SIGNAL_HOME_CHANNEL`, wohin ungefragte Nachrichten gehen.

Registriert wird einmalig im Sidecar. Ohne Captcha verweigert Signal:

```bash
kubectl -n hermes exec deploy/hermes -c signal-cli -- \
  signal-cli --config /data/signal-cli -a +49... register --captcha '<token>'
kubectl -n hermes exec deploy/hermes -c signal-cli -- \
  signal-cli --config /data/signal-cli -a +49... verify <code>
```

Den Token liefert `signalcaptchas.org/registration/generate.html`, den Code
eine SMS an die Nummer. Beide Befehle schweigen bei Erfolg; ob es geklappt hat,
zeigt `uuid` in `/data/signal-cli/data/accounts.json`.

Bis zur Registrierung bricht der Daemon ab; eine Schleife im Sidecar hält den
Container deshalb am Leben, sonst wäre der nötige `exec` nicht möglich.

Die Anmeldung lebt allein auf dem Volume: ist es weg, muss neu registriert
werden — und eine Nummer lässt sich nicht beliebig oft neu registrieren.

## GitHub

Der Agent bekommt einen Token **in seiner eigenen Umgebung** — anders als das
Postfach-Passwort, das nur im MCP-Container liegt. Er kann ihn also lesen. Das
ist bewusst so gewählt, weil `git` und `gh` ihn dort erwarten; die Folge ist,
dass der Token eng gehalten gehört: fine-grained, nur die vorgesehenen Repos,
`contents: write` und `pull_requests: write`, mit Ablaufdatum. Ein geschütztes
`main` verhindert, dass aus „Pull Request" ein direkter Push wird.

`gh` fehlt im Image und wird vom initContainer auf das Volume gelegt, nach
`/opt/data/.local/bin` — das liegt bereits auf dem PATH. Die Identität und der
Credential-Helper stehen in `/opt/data/home/.gitconfig`, das aus der ConfigMap
kommt und bei jedem Start neu geschrieben wird. Der Helper reicht
`$GITHUB_TOKEN` durch, statt ihn in eine Datei zu schreiben.

Commits tragen `Hermes <hermes@cloud.p3l1.de>` — eine eigene Identität, damit
sie von deinen eigenen unterscheidbar bleiben. GitHub ordnet sie dadurch keinem
Konto zu; wer das will, trägt eine verifizierte Adresse ein.

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
