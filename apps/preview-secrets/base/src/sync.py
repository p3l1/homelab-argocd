"""Kopiert benannte Secrets in jeden Namespace mit dem passenden Label.

Preview-Namensraeume entstehen und vergehen mit ihrer Pull Request. Was sie
brauchen - der Zugang zu den privaten Images und der Anwendungsschluessel -
ist zu geheim fuer das oeffentliche Repository und kann deshalb nicht aus dem
Chart kommen.
"""

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://kubernetes.default.svc"
SA = "/var/run/secrets/kubernetes.io/serviceaccount"
LABEL = os.environ.get("PREVIEW_LABEL", "p3l1.de/preview-secrets")
SOURCE_NS = os.environ.get("SOURCE_NAMESPACE", "preview-secrets")
NAMES = [n for n in os.environ.get("SECRET_NAMES", "").split(",") if n]
INTERVAL = int(os.environ.get("INTERVAL_SECONDS", "30"))

log = logging.getLogger("preview-secrets")


def _token():
    with open(f"{SA}/token") as fh:
        return fh.read().strip()


_ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")


def call(method, path, body=None):
    req = urllib.request.Request(f"{API}{path}", method=method)
    req.add_header("Authorization", f"Bearer {_token()}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    with urllib.request.urlopen(req, context=_ctx, timeout=30) as resp:
        return json.load(resp)


def target_namespaces():
    q = urllib.parse.quote(f"{LABEL}=true", safe="=")
    got = call("GET", f"/api/v1/namespaces?labelSelector={q}")
    return [
        ns["metadata"]["name"]
        for ns in got.get("items", [])
        if ns["metadata"]["name"] != SOURCE_NS
        and ns.get("status", {}).get("phase") != "Terminating"
    ]


def source_secret(name):
    return call("GET", f"/api/v1/namespaces/{SOURCE_NS}/secrets/{name}")


def copy_into(ns, src):
    name = src["metadata"]["name"]
    body = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": name,
            "namespace": ns,
            "labels": {"app.kubernetes.io/managed-by": "preview-secrets"},
        },
        "type": src.get("type", "Opaque"),
        "data": src.get("data", {}),
    }
    try:
        current = call("GET", f"/api/v1/namespaces/{ns}/secrets/{name}")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        call("POST", f"/api/v1/namespaces/{ns}/secrets", body)
        log.info("angelegt: %s/%s", ns, name)
        return
    if current.get("data") != body["data"]:
        call("PUT", f"/api/v1/namespaces/{ns}/secrets/{name}", body)
        log.info("aktualisiert: %s/%s", ns, name)


def reconcile():
    sources = {}
    for name in NAMES:
        try:
            sources[name] = source_secret(name)
        except urllib.error.HTTPError as exc:
            log.error("Quelle %s/%s nicht lesbar: %s", SOURCE_NS, name, exc.code)
    for ns in target_namespaces():
        for src in sources.values():
            try:
                copy_into(ns, src)
            except urllib.error.HTTPError as exc:
                log.error("%s/%s: %s", ns, src["metadata"]["name"], exc.code)


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if not NAMES:
        raise SystemExit("SECRET_NAMES ist leer")
    log.info("beobachte %s=true, kopiere %s aus %s", LABEL, NAMES, SOURCE_NS)
    while True:
        try:
            reconcile()
        except Exception:
            log.exception("Durchlauf fehlgeschlagen")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
