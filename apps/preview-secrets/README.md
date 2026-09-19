# Preview Secrets

Kopiert `ghcr-pull` und `taktwerk-preview-secrets` aus dem Namensraum
`preview-secrets` in jeden Namensraum mit dem Label
`p3l1.de/preview-secrets: "true"`.

Preview-Namensräume entstehen und vergehen mit ihrer Pull Request. Was sie
brauchen — Zugang zu den privaten Images und der Anwendungsschlüssel — ist zu
geheim für dieses öffentliche Repository und kann deshalb nicht aus dem Chart
kommen. Das Chart verweist nur auf die Namen.

Nur kopieren, nie entfernen: Preview-Namensräume verschwinden als Ganzes, ein
Entfernen-Pfad wäre toter Code.

## Grenzen

RBAC kann Schreibrechte auf Secrets nicht auf bestimmte Namen einschränken; die
Liste in `SECRET_NAMES` tut das. Der Dienst darf damit technisch mehr, als er
tut — der Grund, warum er nichts anderes anfasst, steht nur im Programm.
