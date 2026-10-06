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

Der Agent arbeitet unter **eigener Identität**, nicht unter deiner: eine GitHub
App namens `hermes`, installiert auf den Repositories, die er anfassen darf.
Das ist dieselbe Linie wie bei Signal, wo er eine eigene Nummer hat statt eines
verknüpften Geräts an deinem Konto.

Der Unterschied ist nicht kosmetisch. Ein Personal Access Token trägt die
Identität seines Besitzers; GitHub unterscheidet dann nicht mehr zwischen dir
am Rechner und dem Token im Pod. Ein Ruleset, das dich als Owner durchlässt,
lässt damit auch den Agenten durch — der Schutz wäre keiner. Eine App ist ein
eigener Akteur und steht in keiner Bypass-Liste.

### Der Token wird fortlaufend erneuert

Apps authentifizieren sich nicht mit einem festen Token, sondern tauschen ihren
Private Key gegen einen Installation-Token, der nach einer Stunde verfällt. Das
erledigt der Sidecar `github-token`:

```
Secret (App-ID, Installation-ID, Private Key)
  └─> Sidecar: JWT (RS256, 10 min) ─> POST /app/installations/<id>/access_tokens
        └─> /opt/data/github/token   alle 45 Minuten neu, 0600
```

Er ist als **nativer Sidecar** deklariert (`initContainers` mit
`restartPolicy: Always`), startet also vor Hermes und läuft danach weiter — der
Token liegt bereit, bevor der Agent seinen ersten Zug macht.

Der Private Key liegt **nur in diesem Container**, entpackt auf einem tmpfs,
nie auf der Platte. Hermes sieht allein den Token auf dem geteilten Volume. Ein
Leck aus seinem Container heraus kostet damit höchstens eine Stunde Zugriff,
nicht den Schlüssel zur App.

Im Secret steht der Key **base64-kodiert**, weil `scripts/secret.sh` je
Schlüssel eine Zeile liest und PEM mehrzeilig ist.

### Wie git und gh an den Token kommen

Keiner von beiden kann mit einer App umgehen, und eine Umgebungsvariable lässt
sich im laufenden Container nicht nachziehen. Beide lesen deshalb die Datei:

| | |
|---|---|
| `git` | Credential-Helper in `/opt/data/home/.gitconfig`, aus der ConfigMap |
| `gh` | Wrapper unter `/opt/data/.local/bin/gh`, Binary daneben in `libexec` |

`gh` fehlt im Image und wird vom initContainer auf das Volume gelegt;
`/opt/data/.local/bin` liegt bereits auf dem PATH.

### Wo er schreiben darf

Nur dort, wo die App installiert ist — alles andere bleibt für ihn unerreichbar.
Welche Repositories das sind, sagt die Installation selbst, nicht diese Datei:

```bash
gh api /installation/repositories --jq '.repositories[].full_name'
```

Jedes davon braucht ein Ruleset `protect-main`: auf dem Standard-Branch nur über
Pull Request, kein Löschen, kein Force-Push. Als Repository-Admin hast du einen
Bypass und pushst weiter direkt; die App hat keinen. „Pull Request" ist für sie
also keine Konvention, sondern die einzige Möglichkeit.

**Beides gehört zusammen.** Ein Repository in der Installation ohne Ruleset ist
eines, in das der Agent direkt auf `main` schreiben kann:

```bash
gh api -X POST /repos/p3l1/<repo>/rulesets --input docs/github-ruleset.json
```

Commits tragen `Hermes <hermes@cloud.p3l1.de>`, damit sie von deinen eigenen
unterscheidbar bleiben. Pull Requests erscheinen unter dem Bot-Konto der App.

### Einrichtung

1. App anlegen unter **Settings → Developer settings → GitHub Apps → New**:
   Name `hermes`, Webhook aus, Berechtigungen `Contents: Read and write`,
   `Pull requests: Read and write`, `Metadata: Read-only`.

   Soll er auch CI-Dateien ändern können, kommt `Workflows: Read and write`
   hinzu: ohne diese Berechtigung weist GitHub jeden Push zurück, der
   `.github/workflows/` anfasst — mit einer Fehlermeldung, die nach einem
   Rechteproblem am Repository aussieht, nicht nach einer fehlenden
   App-Berechtigung.
2. Private Key erzeugen und herunterladen, `App ID` notieren.
3. App installieren („Install App"), **Only select repositories**, die Liste
   oben.
4. Zugangsdaten hinterlegen:

```bash
./scripts/secret.sh \
  -f GITHUB_APP_PRIVATE_KEY="$HOME/Downloads/p3l1-hermes.2026-10-06.private-key.pem" \
  hermes-secrets hermes GITHUB_APP_ID GITHUB_APP_PRIVATE_KEY
```

Der Schlüssel kommt aus der Datei, nicht aus der Abfrage: Eine
Terminal-Eingabezeile fasst 1024 Zeichen, ein PEM ist länger — Einfügen bleibt
dort wirkungslos. Base64 in einer Zeile nimmt der Sidecar aber auch an.

Die Installation ID braucht es nicht: Der Sidecar fragt sie beim Start ab und
besteht darauf, dass es genau eine gibt. Kommt je eine zweite dazu, benennt die
Fehlermeldung beide, und `GITHUB_APP_INSTALLATION_ID` entscheidet dann — der
Schlüssel ist im Deployment als `optional` eingetragen.

Ob es trägt, zeigt der Sidecar:

```bash
kubectl -n hermes logs deploy/hermes -c github-token
# Token erneuert, gueltig bis 2026-10-06T...Z
```

## Kalender, M365-Postfächer und Teams

Alles bedient `graph-mcp`, ein konfigurierter
[`ms-365-mcp-server`](https://github.com/softeria/ms-365-mcp-server). Wie beim
Postfach hält der Server die Token selbst und Hermes spricht nur HTTP — er
bekommt die Anmeldungen nie zu sehen. Die Posteo-Kalender und -Notizen folgen
später über `dav-mcp`.

Von 334 Tools bleiben 31 übrig, und `--allowed-scopes` begrenzt auch den
Login: MSAL fragt nur `Calendars.ReadWrite`, `Mail.ReadWrite` und die
Teams-Lese-Scopes an.
`get-schedule` kommt damit aus, `find-meeting-times` nicht — das verlangt
`Calendars.Read.Shared` und bleibt deshalb draußen.

### Mail: lesen und Entwürfe, wie bei Posteo

Dieselbe Linie wie beim IMAP-Server, nur härter durchgesetzt. Dort ist „kein
Senden" eine Selbstbeschränkung des Servers; hier fehlt die Berechtigung:
`send-mail` verlangt zusätzlich `Mail.Send`, und ohne diesen Scope schaltet
der Server das Tool von selbst ab — auch wenn es jemand in `--enabled-tools`
einträgt. Zwei unabhängige Riegel.

`delete-mail-message` braucht diesen zweiten Riegel nicht, es kommt mit
`Mail.ReadWrite` aus. Es steht deshalb einfach nicht in der Liste.

Was er kann: Ordner und Nachrichten lesen, Anhänge auflisten, verschieben,
als gelesen markieren, und Entwürfe anlegen — neu, als Antwort oder als
Antwort an alle.

Posteo bleibt beim IMAP-Server. Der kann dort mehr (Sterne, Massenverschieben
nach Absender oder Domain) und hält sein eigenes Passwort.

### Teams: nur lesen

Chats (`list-chats`, `get-chat`, Mitglieder, Nachrichten, Antworten) und Kanäle
(`list-joined-teams`, `get-team`, Kanäle, Nachrichten, Antworten) lassen sich
lesen. Senden, Antworten, Bearbeiten, Reaktionen, Anlegen und Löschen stehen
nicht in der Liste, und es gibt keinen `*.Send`-/`ReadWrite`-Scope.

Angefragt werden `Chat.ReadBasic`, `Chat.Read`, `ChatMember.Read`, `ChatMessage.Read`,
`Team.ReadBasic.All`, `Channel.ReadBasic.All` und `ChannelMessage.Read.All`.
**`ChannelMessage.Read.All` verlangt Admin-Consent**; ohne ihn bleiben die
Kanalnachrichten leer, Chats funktionieren davon unabhängig. `Chat.Read` braucht Graph für `list-chat-messages`; `ChatMessage.Read` allein
liefert 403. Kein Lese-Tool verlangt den Scope außer `list-pinned-chat-messages`,
das deshalb freigeschaltet ist. Nach dem Merge ist
jedes Konto einmal neu anzumelden (`--login`), weil sich die Scopes ändern.

### Hier arbeitet er unter *deiner* Identität

Bei Signal hat er eine eigene Nummer, bei GitHub eine eigene App. In einem
fremden Tenant ist beides nicht möglich: ohne eigene App-Registrierung bleibt
nur delegierter Zugriff. Jeder Termin, den er anlegt, trägt deinen Namen, und
jeder Zugriff erscheint im Audit-Log des Tenants als deine Anmeldung.

Darum sind zwei Dinge abgeschaltet: **Teilnehmer** und **Löschen**. Beides
verschickt echte Einladungen und Absagen unter deinem Namen, und Graph lässt
das nicht unterdrücken. Wird Löschen gebraucht, genügt ein Eintrag im
`--enabled-tools`-Ausdruck.

### Anmeldung je Konto

Einmalig pro Postfach, wie bei Signal und der Claude-CLI:

```bash
kubectl -n hermes exec deploy/graph-mcp -- ms-365-mcp-server --org-mode --list-permissions
kubectl -n hermes exec -it deploy/graph-mcp -- ms-365-mcp-server --login
kubectl -n hermes exec deploy/graph-mcp -- ms-365-mcp-server --list-accounts
```

`--list-permissions` vorweg sagt, was der Tenant freigeben müsste — bei fremden
Tenants der Unterschied zwischen Probieren und Wissen. Ein Tenant kann
User-Consent auf gering eingestufte Berechtigungen begrenzen oder unbekannte
Anwendungen per Conditional Access sperren; dann endet es hier.

Damit ist bei **`Mail.ReadWrite` zu rechnen**: Admin-Consent verlangt es nicht,
aber es gilt als hoch eingestuft und ist in Microsofts empfohlener
User-Consent-Richtlinie vom Selbst-Consent ausgenommen. Folgt ein Tenant dieser
Empfehlung, braucht der Mail-Teil den Administrator. Die Kalender-Tools bleiben
davon unberührt — `--allowed-scopes` führt beide Scopes getrennt.

**Schließe den Device-Code-Login im Browser mit einem Passkey ab, wo der
Tenant es zulässt**, nicht mit Passwort und MFA:

| Ereignis | Passwort + MFA | passwortlos |
|---|---|---|
| Passwort geändert, SSPR | **widerrufen** | bleibt |
| Admin-Reset (Entra/M365 admin center) | widerrufen | widerrufen |
| Admin widerruft alle Token | widerrufen | widerrufen |

Bei einem Tenant mit 90-Tage-Passwortrotation ist das der Unterschied zwischen
viermal im Jahr und praktisch nie. Durch Zeitablauf verfällt nichts: der
Refresh Token ersetzt sich bei jeder Nutzung.

Nicht in unserer Hand ist eine Sign-in-Frequency-Policy. Ohne sie gilt ein
90-Tage-Fenster; setzt ein Tenant sieben Tage, ist das Konto wöchentlich neu
anzumelden. Das zeigt sich erst im Betrieb.

Die Anmeldungen liegen allein auf `graph-mcp-tokens`. Ist das Volume weg, ist
jedes Konto neu anzumelden.

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
  SIGNAL_ACCOUNT OIDC_CLIENT_ID API_SERVER_KEY ANTHROPIC_API_KEY \
  GITHUB_APP_ID GITHUB_APP_INSTALLATION_ID GITHUB_APP_PRIVATE_KEY
```

`SIGNAL_ACCOUNT` ist die eigene Nummer in E.164 und versorgt auch
`SIGNAL_ALLOWED_USERS` und `SIGNAL_HOME_CHANNEL`; sie steht im Secret, damit
sie nicht im öffentlichen Repository landet. Das Secret muss **vor** dem ersten
Sync liegen, sonst bleibt der Pod in `CreateContainerConfigError`.
