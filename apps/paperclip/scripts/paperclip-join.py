"""Meldet Hermes als hermes_gateway-Agent bei Paperclip an.

Laeuft im Hermes-Container. Kein Schluessel wird ausgegeben:
  accept <invite-token>  Join-Request stellen, Claim-Secret ablegen
  claim                  Agent-Key abholen und nach /opt/data/.env schreiben
"""
import json
import os
import sys
import urllib.error
import urllib.request

PAPERCLIP = "http://paperclip.paperclip.svc:3100"
STATE = "/opt/data/paperclip/join.json"
ENV_FILE = "/opt/data/.env"


def post(path, body):
    req = urllib.request.Request(
        PAPERCLIP + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:500]


def accept(token):
    status, body = post(f"/api/invites/{token}/accept", {
        "requestType": "agent",
        "agentName": "Hermes",
        "adapterType": "hermes_gateway",
        "capabilities": "Hermes mit Claude-Abo, GitHub App, kubectl (view), M365- und Posteo-Werkzeugen.",
        "agentDefaultsPayload": {
            "apiBaseUrl": "http://hermes.hermes.svc:8642",
            "apiKey": os.environ["API_SERVER_KEY"],
            "sessionKeyStrategy": "issue",
            "paperclipApiUrl": PAPERCLIP,
            "dangerouslyAllowInsecureRemoteHttp": True,
        },
    })
    if status != 202:
        sys.exit(f"accept: HTTP {status}: {body}")
    os.makedirs(os.path.dirname(STATE), mode=0o700, exist_ok=True)
    fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({k: body[k] for k in ("id", "claimSecret", "claimApiKeyPath")}, f)
    codes = [d.get("code") for d in body.get("diagnostics", [])]
    print(f"join request {body['id']} wartet auf Freigabe; diagnostics={codes}")


def claim():
    with open(STATE) as f:
        state = json.load(f)
    status, body = post(state["claimApiKeyPath"], {"claimSecret": state["claimSecret"]})
    if status != 201:
        sys.exit(f"claim: HTTP {status}: {body}")
    keep = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            keep = [l for l in f if not l.startswith(("PAPERCLIP_API_URL=", "PAPERCLIP_API_KEY="))]
    keep += [f"PAPERCLIP_API_URL={PAPERCLIP}\n", f"PAPERCLIP_API_KEY={body['token']}\n"]
    with open(ENV_FILE, "w") as f:
        f.writelines(keep)
    os.remove(STATE)
    print(f"key {body['keyId']} nach {ENV_FILE} geschrieben")


if __name__ == "__main__":
    {"accept": lambda: accept(sys.argv[2]), "claim": claim}[sys.argv[1]]()
