"""Holt beobachtete Vergangenheit aus dem DWD-Klimaarchiv.

Das RV-Verzeichnis reicht nur zwei Tage zurueck. Weiter zurueck liegt YW -
dieselbe Groesse in mm je fuenf Minuten, aber auf dem aelteren 900x900-Gitter
und geeicht statt reiner Radarschaetzung. Beim Einlesen wird es auf den
DE1200-Ausschnitt umgerechnet, damit Vergangenheit und Vorhersage dasselbe
Raster benutzen.
"""

import io
import logging
import re
import tarfile
import urllib.request
from datetime import datetime, timezone

import radolan

log = logging.getLogger("rain-commute.archive")

_DAY_RE = re.compile(r"YW-(\d{6})\.tar\.gz")
_STEP_RE = re.compile(r"yw_\d+-(\d{10})-")


def available_days():
    """Die Tage, die das Archiv vorhaelt, als JJMMTT - aeltester zuerst."""
    with urllib.request.urlopen(radolan.ARCHIVE_URL, timeout=60) as resp:
        listing = resp.read().decode("utf-8", "replace")
    return sorted(set(_DAY_RE.findall(listing)))


def _step_time(name):
    m = _STEP_RE.search(name)
    if not m:
        return None
    v = m.group(1)
    return datetime(2000 + int(v[0:2]), int(v[2:4]), int(v[4:6]),
                    int(v[6:8]), int(v[8:10]), tzinfo=timezone.utc)


def fetch_day(day, row0, col0, rows, cols, mapping):
    """Ein Archivtag als Liste von (Zeitpunkt, Ausschnitt im DE1200-Raster)."""
    url = f"{radolan.ARCHIVE_URL}YW-{day}.tar.gz"
    with urllib.request.urlopen(url, timeout=180) as resp:
        blob = resp.read()
    out = []
    # "r:gz" packt beim Lesen aus; die Tagesdatei entpackt waere 80 MB.
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            when = _step_time(member.name)
            if when is None:
                continue
            source = radolan.parse_composite(tar.extractfile(member).read())
            out.append((when, radolan.resample_to_de1200(
                source, row0, col0, rows, cols, mapping)))
    out.sort(key=lambda p: p[0])
    return out
