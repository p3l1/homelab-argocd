"""Schickt die Regenmeldung als Klartext ueber die bestehende Gotify-Bridge."""

import json
import logging
import os
import urllib.request
from datetime import timedelta

log = logging.getLogger("rain-commute.notify")

# Direkt zu Gotify: In diesem Cluster gibt es keine Alertmanager-Bridge, die
# den Token halten koennte. Er kommt aus einem Secret.
GOTIFY_URL = os.environ.get("GOTIFY_ENDPOINT", "https://notification.cloud.p3l1.de/message")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN", "")
RADAR_URL = os.environ.get("RADAR_URL", "https://regen.cloud.p3l1.de/radar.svg")


def compose(report, now):
    """Aus dem Befund eine Nachricht, die die Entscheidung schon enthaelt."""
    start = now + timedelta(minutes=report["starts_in"])
    end = now + timedelta(minutes=report["ends_in"])
    word = report["word"]
    minutes = report["ends_in"] - report["starts_in"]

    if report["starts_in"] == 0:
        title = f"Es regnet — {word}"
        lead = f"Auf dem Arbeitsweg fällt gerade {word}"
    else:
        title = f"Regen ab {start:%H:%M} — {word}"
        lead = f"Ab {start:%H:%M} fällt auf dem Arbeitsweg {word}"

    body = (f"{lead}, bis etwa {end:%H:%M} ({minutes} Minuten). "
            f"Spitze {report['peak_mm_h']:.0f} mm/h.\n\n{RADAR_URL}")
    return title, body


def send(title, body, priority=7):
    if not GOTIFY_TOKEN:
        log.warning("Kein GOTIFY_TOKEN gesetzt, Meldung unterbleibt: %s", title)
        return False
    payload = {"title": title, "message": body, "priority": priority}
    req = urllib.request.Request(
        GOTIFY_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Gotify-Key": GOTIFY_TOKEN},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            log.info("Meldung zugestellt (HTTP %s): %s", r.status, title)
            return True
    except Exception:
        log.exception("Meldung konnte nicht zugestellt werden")
        return False
