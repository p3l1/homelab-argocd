"""Laedt das RV-Komposit, liefert Metriken, Kartenbilder und die Zeitachse aus."""

import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import archive
import commute
import notify
import radolan
import render
import store as store_mod
import webpage

BERLIN = ZoneInfo("Europe/Berlin")
REFRESH_SECONDS = 300
PORT = 8000
HISTORY_STEPS = 24            # 2 Stunden aus dem RV-Verzeichnis
KEEP_DAYS = int(os.environ.get('RAIN_KEEP_DAYS', '30'))
CROP_PAD = 2                  # Rand um den Kartenausschnitt

log = logging.getLogger("rain-commute")
_state = {"forecast": [], "base_time": None, "report": None,
          "expected": None, "route": [], "fetched_at": None}
_store = None
_mapping = None
_notified = set()
_lock = threading.Lock()

_CROP = None


def _crop_box():
    """Der Bildausschnitt plus Rand - mehr muss vom Gitter nicht aufgehoben werden."""
    global _CROP
    if _CROP is None:
        grid = [radolan.lonlat_to_grid(lon, lat) for lon, lat in commute.ROUTE_POINTS]
        mid_c = (min(c for c, _ in grid) + max(c for c, _ in grid)) / 2
        mid_r = (min(r for _, r in grid) + max(r for _, r in grid)) / 2
        side = render.HALF * 2 + 2 * CROP_PAD
        _CROP = (int(mid_r - render.HALF - CROP_PAD), int(mid_c - render.HALF - CROP_PAD),
                 side, side)
    return _CROP


def _small(composite):
    return composite.crop(*_crop_box())


def _yw_mapping():
    """Zuordnung DE1200-Ausschnitt -> YW-Gitter. Fest, also einmal berechnet."""
    global _mapping
    if _mapping is None:
        _mapping = radolan.build_mapping(*_crop_box())
    return _mapping


def _listing():
    with urllib.request.urlopen(radolan.LATEST_URL, timeout=30) as resp:
        listing = resp.read().decode("utf-8", "replace")
    names = sorted(set(re.findall(r"DE1200_RV\d{10}\.tar\.bz2", listing)))
    if not names:
        raise RuntimeError("Verzeichnis enthaelt keine RV-Dateien")
    return names


def _time_of(name):
    """Der Dateiname traegt JJMMTThhmm in UTC."""
    m = re.search(r"RV(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", name)
    y, mo, d, h, mi = (int(v) for v in m.groups())
    return datetime(2000 + y, mo, d, h, mi, tzinfo=timezone.utc)


def _load(name, only_first=False):
    with urllib.request.urlopen(radolan.LATEST_URL + name, timeout=60) as resp:
        blob = resp.read()
    return radolan.read_archive(blob, only_first=only_first)


def _fetch_once(with_history=False):
    names = _listing()
    latest = names[-1]
    composites = _load(latest)
    forecast = [_small(c) for c in composites]
    base = _time_of(latest)

    # Der Nullschritt ist die Beobachtung von jetzt und gehoert in die Ablage.
    if forecast:
        _store.put(base, forecast[0])

    if with_history:
        # Die letzten Stunden aus dem RV-Verzeichnis; alles Aeltere holt der
        # Nachlauf aus dem Klimaarchiv.
        for name in names[-(HISTORY_STEPS + 1):-1]:
            when = _time_of(name)
            if _store.get(when) is not None:
                continue
            try:
                got = _load(name, only_first=True)
                if got:
                    _store.put(when, _small(got[0]))
            except Exception:
                log.warning("Historienschritt %s nicht ladbar", name)
        log.info("Jüngste Historie ergänzt")

    route = [(c.forecast_minutes, commute.max_on_route(c)) for c in forecast]
    with _lock:
        _state["forecast"] = forecast
        _state["base_time"] = base
        _state["route"] = route
        _state["expected"] = commute.expected_rain(forecast)
        _state["report"] = commute.describe(forecast)
        _state["fetched_at"] = time.time()
    log.info("%s geladen, %d Zeitschritte", latest, len(forecast))
    _maybe_notify()


def _day_steps(day):
    """Die Zeitpunkte eines Kalendertages in Ortszeit, aelteste zuerst.

    Fuer heute kommen die Vorhersageschritte hinten dran, sodass sich der
    Regler ohne Bruch von der Vergangenheit in die Zukunft schieben laesst.
    """
    lo = datetime.combine(day, dtime(0, 0), tzinfo=BERLIN)
    hi = lo + timedelta(days=1)
    out = [(w.astimezone(BERLIN), "ist")
           for w in _store.timestamps(since=lo) if w < hi]
    with _lock:
        forecast = list(_state["forecast"])
        base = _state["base_time"]
    if base is not None:
        for c in forecast:
            if c.forecast_minutes == 0:
                continue
            w = (base + timedelta(minutes=c.forecast_minutes)).astimezone(BERLIN)
            if lo <= w < hi:
                out.append((w, "vorhersage"))
    out.sort(key=lambda p: p[0])
    return out


def _composite_at_time(when):
    """Beobachtung aus der Ablage, sonst der passende Vorhersageschritt."""
    got = _store.get(when.astimezone(timezone.utc).replace(second=0, microsecond=0))
    if got is not None:
        return got, "ist"
    with _lock:
        forecast = list(_state["forecast"])
        base = _state["base_time"]
    if base is None:
        return None, None
    want = int((when - base).total_seconds() // 60)
    best = min(forecast, key=lambda c: abs(c.forecast_minutes - want), default=None)
    return best, "vorhersage"


def _backfill_loop():
    """Fehlende Archivtage nachladen - einer nach dem anderen.

    Im Hintergrund und einzeln, damit der Dienst waehrenddessen benutzbar
    bleibt: 30 Tage sind 120 MB und auf einem Pi kein Nebenbei.
    """
    time.sleep(20)
    while True:
        try:
            days = archive.available_days()[-KEEP_DAYS:]
            todo = [d for d in days if not _store.have_day(d)]
            if not todo:
                removed = _store.prune()
                if removed:
                    log.info("%d Schritte aelter als %d Tage entfernt", removed, KEEP_DAYS)
                time.sleep(3600)
                continue
            day = todo[-1]          # von der Gegenwart rueckwaerts
            steps = archive.fetch_day(day, *_crop_box(), _yw_mapping())
            _store.put_many(steps)
            _store.mark_day(day, len(steps))
            first, _, count = _store.span()
            log.info("Archivtag %s eingelesen (%d Schritte); Ablage nun %d Schritte ab %s",
                     day, len(steps), count,
                     first.astimezone(BERLIN).strftime("%d.%m. %H:%M") if first else "?")
        except Exception:
            log.exception("Nachlauf fehlgeschlagen")
            time.sleep(300)


def _current_window(now):
    if now.weekday() > 4:
        return None
    minutes = now.hour * 60 + now.minute
    for name, start, end in commute.WINDOWS:
        if start <= minutes < end:
            return f"{now:%Y-%m-%d}/{name}"
    return None


def _maybe_notify():
    """Einmal je Pendelfenster melden - der Alarm soll informieren, nicht nerven."""
    now = datetime.now(BERLIN)
    window = _current_window(now)
    if window is None or window in _notified:
        return
    with _lock:
        report = _state["report"]
    if report is None:
        return
    title, body = notify.compose(report, now)
    if notify.send(title, body):
        _notified.add(window)


def _refresh_loop():
    first = True
    while True:
        try:
            _fetch_once(with_history=first)
            first = False
        except Exception:
            # Alte Werte stehen lassen: commute_radar_age_seconds waechst und
            # die Regel StaleRadarData schlaegt an.
            log.exception("Abruf fehlgeschlagen")
        time.sleep(REFRESH_SECONDS)


def _metrics():
    with _lock:
        route = list(_state["route"])
        expected = _state["expected"]
        fetched_at = _state["fetched_at"]
    history = _store.span()[2] if _store else 0

    now = datetime.now(BERLIN)
    lines = [
        "# HELP commute_window_active Laeuft gerade ein Pendelfenster.",
        "# TYPE commute_window_active gauge",
        f"commute_window_active {int(commute.window_active(now))}",
        "# HELP commute_radar_age_seconds Alter des juengsten Radarabrufs.",
        "# TYPE commute_radar_age_seconds gauge",
        "commute_radar_age_seconds "
        + (f"{time.time() - fetched_at:.0f}" if fetched_at else "+Inf"),
        "# HELP commute_history_steps Schritte in der Ablage.",
        "# TYPE commute_history_steps gauge",
        f"commute_history_steps {history}",
    ]
    if route:
        lines += [
            "# HELP commute_rain_forecast_mm Regen auf der Route je Vorhersagehorizont, mm pro 5 Minuten.",
            "# TYPE commute_rain_forecast_mm gauge",
        ]
        for horizon, value in route:
            if value is not None:
                lines.append(
                    f'commute_rain_forecast_mm{{horizon_min="{horizon}"}} {value:.2f}')
        if expected is not None:
            lines += [
                "# HELP commute_rain_expected_mm Staerkster Regen auf der Route in den naechsten 45 Minuten.",
                "# TYPE commute_rain_expected_mm gauge",
                f"commute_rain_expected_mm {expected:.2f}",
            ]
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, body, content_type, status=200, cache="no-cache"):
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            today = datetime.now(BERLIN).date()
            first, last, count = _store.span()
            self._send(webpage.page(
                today,
                first.astimezone(BERLIN).date() if first else today,
                _day_steps(today), count), "text/html; charset=utf-8")
        elif path == "/api/day":
            try:
                day = datetime.strptime(query.get("d", [""])[0], "%Y-%m-%d").date()
            except ValueError:
                self._send("{}", "application/json", 400)
                return
            steps = [{"at": w.isoformat(), "clock": w.strftime("%H:%M"), "kind": k}
                     for w, k in _day_steps(day)]
            self._send(json.dumps(steps), "application/json")
        elif path == "/radar.svg":
            when, comp, kind = None, None, None
            if "at" in query:
                try:
                    when = datetime.fromisoformat(query["at"][0])
                except ValueError:
                    when = None
                if when is not None:
                    comp, kind = _composite_at_time(when)
            if comp is None:
                try:
                    offset = int(query.get("t", ["0"])[0])
                except ValueError:
                    offset = 0
                with _lock:
                    base = _state["base_time"]
                    forecast = list(_state["forecast"])
                if base is None:
                    self._send("noch keine Radardaten", "text/plain; charset=utf-8", 503)
                    return
                when = base + timedelta(minutes=offset)
                comp, kind = _composite_at_time(when)
                if comp is None and forecast:
                    comp, kind = forecast[0], "vorhersage"
            if comp is None:
                self._send("kein Bild fuer diesen Zeitpunkt",
                           "text/plain; charset=utf-8", 404)
                return
            with _lock:
                base = _state["base_time"]
            offset = int((when - base).total_seconds() // 60) if base else 0
            bare = query.get("bare", ["0"])[0] == "1"
            svg = render.render_svg(comp, when=when.astimezone(BERLIN),
                                    with_map=not bare, label_offset=offset,
                                    kind=kind)
            self._send(svg, "image/svg+xml")
        elif path == "/radar.geojson":
            when, comp = None, None
            if "at" in query:
                try:
                    when = datetime.fromisoformat(query["at"][0])
                    comp, _ = _composite_at_time(when)
                except ValueError:
                    pass
            if comp is None:
                with _lock:
                    forecast = list(_state["forecast"])
                comp = forecast[0] if forecast else None
            if comp is None:
                self._send("{}", "application/json", 503)
                return
            self._send(json.dumps(render.to_geojson(comp)), "application/geo+json")
        elif path == "/karte.webp":
            try:
                with open(render.MAP_FILE, "rb") as fh:
                    self._send(fh.read(), "image/webp", cache="public, max-age=86400")
            except OSError:
                self._send("keine Karte", "text/plain; charset=utf-8", 404)
        elif path == "/metrics":
            self._send(_metrics(), "text/plain; version=0.0.4; charset=utf-8")
        elif path == "/healthz":
            self._send("ok", "text/plain; charset=utf-8")
        else:
            self._send("not found", "text/plain; charset=utf-8", 404)

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)


def main():
    global _store
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    _store = store_mod.Store()
    first, _, count = _store.span()
    log.info("Ablage: %d Schritte%s", count,
             f" ab {first.astimezone(BERLIN):%d.%m. %H:%M}" if first else "")
    threading.Thread(target=_refresh_loop, daemon=True).start()
    threading.Thread(target=_backfill_loop, daemon=True).start()
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
