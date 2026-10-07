#!/bin/sh
# Legt die Mitarbeiter-Profile unter /opt/data/profiles an. Die config.yaml
# kommt nur auf ein frisches Profil; danach gehoert sie dem Profil selbst.
# Das Claude-Plugin wird vom Hauptprofil geteilt (Symlink).
set -eu
# ConfigMap-Keys sind flach: profile-<name>.yaml
for f in /seed/profile-*.yaml; do
  n=$(basename "$f" .yaml); n=${n#profile-}
  d=/opt/data/profiles/$n
  install -d -m 0700 "$d"
  [ -f "$d/config.yaml" ] || install -m 0644 "$f" "$d/config.yaml"
  # Temporaerer Shim: jedes Profil laeuft als eigenes Sidecar-Gateway.
  # Bestehende config.yaml (volle Vorlage mit leerem gateway:-Block) ergaenzen.
  if ! grep -q '^  standalone:' "$d/config.yaml"; then
    if grep -q '^gateway:' "$d/config.yaml"; then
      sed -i 's/^gateway:.*/gateway:\n  standalone: true/' "$d/config.yaml"
    else
      printf 'gateway:\n  standalone: true\n' >> "$d/config.yaml"
    fi
  fi
  [ -e "$d/plugins" ] || ln -s /opt/data/plugins "$d/plugins"
done
