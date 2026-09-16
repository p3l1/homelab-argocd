"""Ablage der Radarausschnitte - 30 Tage Vergangenheit auf der Platte.

SQLite statt PostgreSQL: Ein Treiber waere die erste Laufzeitabhaengigkeit
ueberhaupt und braeuchte ein eigenes Image. Es geht um rund 10 MB, und jeder
Wert laesst sich aus dem DWD-Archiv wiederherstellen - ein Datenbankcluster
dafuer stuende in keinem Verhaeltnis.
"""

import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import radolan

log = logging.getLogger("rain-commute.store")

DB_PATH = os.environ.get("RAIN_DB", "/data/radar.sqlite")
KEEP_DAYS = int(os.environ.get("RAIN_KEEP_DAYS", "30"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS radar (
    ts    INTEGER PRIMARY KEY,   -- Unix-Sekunden UTC des Zeitschritts
    row0  INTEGER NOT NULL,
    col0  INTEGER NOT NULL,
    nrows INTEGER NOT NULL,
    ncols INTEGER NOT NULL,
    data  BLOB    NOT NULL
);
CREATE TABLE IF NOT EXISTS days (
    day   TEXT PRIMARY KEY,      -- JJMMTT der eingelesenen Archivtage
    steps INTEGER NOT NULL
);
"""


class Store:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # check_same_thread=False plus eigene Sperre: Abrufschleife und
        # Webserver greifen aus verschiedenen Threads zu.
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.commit()
        self._lock = threading.Lock()

    def put(self, when, composite):
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO radar VALUES (?,?,?,?,?,?)",
                (int(when.timestamp()), composite.row0, composite.col0,
                 composite.rows, composite.cols,
                 composite._values.tobytes()))
            self._db.commit()

    def put_many(self, items):
        """Ein Archivtag in einem Rutsch - 288 Einzelcommits waeren zaeh."""
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO radar VALUES (?,?,?,?,?,?)",
                [(int(w.timestamp()), c.row0, c.col0, c.rows, c.cols,
                  c._values.tobytes()) for w, c in items])
            self._db.commit()

    def get(self, when):
        ts = int(when.timestamp())
        with self._lock:
            row = self._db.execute(
                "SELECT row0,col0,nrows,ncols,data FROM radar WHERE ts=?", (ts,)
            ).fetchone()
        if row is None:
            return None
        import array
        values = array.array("H")
        values.frombytes(row[4])
        return radolan.Composite(values, row[2], row[3], 0, row[0], row[1])

    def timestamps(self, since=None):
        q, args = "SELECT ts FROM radar", ()
        if since is not None:
            q += " WHERE ts >= ?"
            args = (int(since.timestamp()),)
        with self._lock:
            rows = self._db.execute(q + " ORDER BY ts", args).fetchall()
        return [datetime.fromtimestamp(r[0], timezone.utc) for r in rows]

    def span(self):
        with self._lock:
            row = self._db.execute(
                "SELECT MIN(ts), MAX(ts), COUNT(*) FROM radar").fetchone()
        if not row or row[0] is None:
            return None, None, 0
        return (datetime.fromtimestamp(row[0], timezone.utc),
                datetime.fromtimestamp(row[1], timezone.utc), row[2])

    def have_day(self, day):
        with self._lock:
            return self._db.execute(
                "SELECT 1 FROM days WHERE day=?", (day,)).fetchone() is not None

    def mark_day(self, day, steps):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO days VALUES (?,?)", (day, steps))
            self._db.commit()

    def prune(self, keep_days=KEEP_DAYS):
        cut = datetime.now(timezone.utc) - timedelta(days=keep_days)
        with self._lock:
            cur = self._db.execute("DELETE FROM radar WHERE ts < ?",
                                   (int(cut.timestamp()),))
            self._db.execute("DELETE FROM days WHERE day < ?",
                             (cut.strftime("%y%m%d"),))
            self._db.commit()
            return cur.rowcount
