# Hinterlegte SSH-Schlüssel

Öffentliche Schlüssel, die auf jedem Node in `authorized_keys` landen — über
`flash-node.sh` beim ersten Start und danach fortlaufend über die Rolle
`node_base`. Beides liest aus diesem Verzeichnis, die Quelle ist also dieselbe.

| Datei | Herkunft |
|---|---|
| `yubikey.pub` | GPG-Authentication-Subkey auf dem YubiKey (`A097B5F697CF30CB`) |

Es gibt bewusst keinen zweiten Schlüssel: Der Zugang zu den Nodes hängt am
YubiKey, der dafür gesteckt sein muss.

Welche Dateien tatsächlich verwendet werden, steht in
`inventory/group_vars/all/main.yml` unter `node_ssh_public_key_files`.
Öffentliche Schlüssel sind nicht geheim und gehören bewusst ins Repo.
