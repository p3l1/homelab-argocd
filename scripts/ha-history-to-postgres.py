#!/usr/bin/env python3
"""Traegt die Recorder-Historie aus einer SQLite-Datei in die Postgres-Datenbank
von Home Assistant nach.

Home Assistant legt das Schema beim ersten Start selbst an; dieses Skript
fuellt nur die Tabellen. Es laeuft gegen einen port-forward:

    kubectl -n home-assistant port-forward svc/home-assistant-db-rw 5432:5432
    ./scripts/ha-history-to-postgres.py home-assistant_v2.db \\
        "postgresql://homeassistant:...@127.0.0.1:5432/homeassistant"

Home Assistant muss dabei angehalten sein - der Recorder wuerde sonst in
dieselben Tabellen schreiben.

Warum nicht pgloader: Die Recorder-Tabellen haben Boolean-Spalten, die SQLite
als 0/1 ablegt, und states.old_state_id zeigt auf dieselbe Tabelle. Beides
muss beim Uebertragen bedacht werden; hier steht explizit, wie.
"""
import sys
import sqlite3

import psycopg

# Reihenfolge spielt keine Rolle, weil die Fremdschluessel fuer die Dauer der
# Transaktion zurueckgestellt werden - die Liste bestimmt nur, was ueberhaupt
# uebertragen wird. schema_changes und migration_changes bleiben draussen:
# die hat Home Assistant beim Anlegen des Schemas schon gefuellt.
TABLES = [
    "recorder_runs",
    "statistics_runs",
    "statistics_meta",
    "states_meta",
    "event_types",
    "event_data",
    "state_attributes",
    "events",
    "states",
    "statistics",
    "statistics_short_term",
]


def target_columns(pg, table):
    """Spalten und Typen aus Postgres - SQLite kennt die Reihenfolge anders."""
    rows = pg.execute(
        "SELECT column_name, data_type FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = %s"
        " ORDER BY ordinal_position",
        (table,),
    ).fetchall()
    return [(name, typ) for name, typ in rows]


def convert(value, pg_type):
    if value is None:
        return None
    if pg_type == "boolean":
        return bool(value)
    if pg_type == "bytea":
        return bytes(value)
    return value


def main(sqlite_path, dsn):
    lite = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    lite.row_factory = sqlite3.Row

    with psycopg.connect(dsn) as pg:
        cur = pg.cursor()
        # Fremdschluessel zurueckstellbar machen. states.old_state_id zeigt
        # auf states selbst; in Zeilenreihenfolge zu laden reicht nicht.
        fks = cur.execute(
            "SELECT conrelid::regclass::text, conname FROM pg_constraint"
            " WHERE contype = 'f' AND connamespace = 'public'::regnamespace"
        ).fetchall()
        for table, name in fks:
            cur.execute(f'ALTER TABLE {table} ALTER CONSTRAINT "{name}" DEFERRABLE')
        pg.commit()
        print(f"==> {len(fks)} Fremdschluessel zurueckstellbar gemacht")

        cur.execute("SET CONSTRAINTS ALL DEFERRED")
        for table in TABLES:
            cols = target_columns(cur, table)
            if not cols:
                print(f"    {table}: in Postgres nicht vorhanden, uebersprungen")
                continue
            # In Anfuehrungszeichen, weil recorder_runs eine Spalte "end"
            # hat - in SQL ein reserviertes Wort.
            names = [f'"{c}"' for c, _ in cols]
            types = [t for _, t in cols]
            try:
                src = lite.execute(f"SELECT {', '.join(names)} FROM {table}")
            except sqlite3.OperationalError as err:
                print(f"    {table}: in SQLite nicht lesbar ({err}), uebersprungen")
                continue

            cur.execute(f"TRUNCATE {table} CASCADE")
            count = 0
            with cur.copy(
                f"COPY {table} ({', '.join(names)}) FROM STDIN"
            ) as copy:
                while rows := src.fetchmany(5000):
                    for row in rows:
                        copy.write_row(
                            [convert(v, t) for v, t in zip(row, types)]
                        )
                    count += len(rows)
            print(f"    {table}: {count} Zeilen")
        pg.commit()
        print("==> uebertragen")

        # Die Sequenzen stehen sonst auf 1 und die naechste Zeile
        # kollidiert mit einer eingelesenen.
        seqs = cur.execute(
            "SELECT c.relname AS tbl, a.attname AS col,"
            " s.relnamespace::regnamespace::text || '.' || s.relname AS seq"
            " FROM pg_class s"
            " JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i')"
            " JOIN pg_class c ON c.oid = d.refobjid"
            " JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.refobjsubid"
            " WHERE s.relkind = 'S' AND c.relname = ANY(%s)",
            (TABLES,),
        ).fetchall()
        for table, column, seq in seqs:
            cur.execute(
                f"SELECT setval('{seq}',"
                f" COALESCE((SELECT MAX({column}) FROM {table}), 1))"
            )
            print(f"    {seq} nachgezogen")
        pg.commit()
    lite.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
