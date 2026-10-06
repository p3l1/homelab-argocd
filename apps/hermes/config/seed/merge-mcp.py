# Fuehrt die Serverliste in die Datei ein, die Hermes selbst fortschreibt.
# Ein Seed allein greift nur auf einem frischen Volume.
import pathlib
import yaml

config = pathlib.Path("/opt/data/config.yaml")
have = yaml.safe_load(config.read_text()) or {}
want = yaml.safe_load(pathlib.Path("/seed/mcp-servers.yaml").read_text()) or {}

if have.get("mcp_servers") != want:
    have["mcp_servers"] = want
    config.write_text(yaml.safe_dump(have, sort_keys=False, allow_unicode=True))
    print("mcp_servers aus dem Seed uebernommen")
