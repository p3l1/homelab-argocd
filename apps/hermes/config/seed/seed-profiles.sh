#!/bin/sh
# Legt die Mitarbeiter-Profile unter /opt/data/profiles an. Die config.yaml
# kommt nur auf ein frisches Profil; danach gehoert sie dem Profil selbst.
# Das Claude-Plugin wird vom Hauptprofil geteilt (Symlink).
set -eu
for f in /seed/profiles/*.yaml; do
  n=$(basename "$f" .yaml)
  d=/opt/data/profiles/$n
  install -d -m 0700 "$d"
  [ -f "$d/config.yaml" ] || install -m 0644 "$f" "$d/config.yaml"
  [ -e "$d/plugins" ] || ln -s /opt/data/plugins "$d/plugins"
done
