#!/usr/bin/env python3
"""
Prueft einen Paperless-Export gegen die Pruefsummen, die Paperless selbst fuehrt.

    ./scripts/verify-paperless-backup.py ~/backups/paperless/2026-09-06-pre-v3/export

Das Manifest enthaelt zu jedem Dokument die Pruefsumme von Original und
Archivfassung, wie sie in der Datenbank steht. Stimmen alle exportierten
Dateien damit ueberein, ist der Export inhaltlich vollstaendig - eine
Aussage, die Dateizahl und Groesse nicht treffen koennen.

Bis 2.x fuehrt Paperless MD5, ab 3.0 SHA-256 (Migration
documents.0016_sha256_checksums). Welches Verfahren gilt, verraet die Laenge
des hinterlegten Werts - so passt das Skript auf Exporte beider Fassungen.
"""

import hashlib
import json
import sys
from pathlib import Path

# Hexlaenge -> Verfahren. MD5 bis 2.x, SHA-256 ab 3.0.
ALGORITHMS = {32: "md5", 64: "sha256"}


def file_digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2

    export = Path(sys.argv[1]).expanduser()
    manifest_path = export / "manifest.json"
    if not manifest_path.exists():
        print(f"Fehler: {manifest_path} nicht gefunden")
        return 2

    manifest = json.loads(manifest_path.read_text())
    docs = [e for e in manifest if e["model"] == "documents.document"]
    print(f"Dokumente im Manifest: {len(docs)}")

    ok = mismatch = missing = 0
    problems = []
    used = set()

    for d in docs:
        fields = d["fields"]
        for name_key, sum_key in (
            ("__exported_file_name__", "checksum"),
            ("__exported_archive_name__", "archive_checksum"),
        ):
            name = d.get(name_key)
            expected = fields.get(sum_key)
            if not name or not expected:
                continue

            algorithm = ALGORITHMS.get(len(expected))
            if algorithm is None:
                mismatch += 1
                problems.append(
                    f"UNBEKANNT  pk={d['pk']} Pruefsumme mit {len(expected)} Zeichen"
                )
                continue
            used.add(algorithm)

            path = export / name
            if not path.exists():
                missing += 1
                problems.append(f"FEHLT      pk={d['pk']} {name}")
            elif file_digest(path, algorithm) == expected:
                ok += 1
            else:
                mismatch += 1
                problems.append(f"ABWEICHUNG pk={d['pk']} {name}")

    print(f"Verfahren             : {', '.join(sorted(used)) or 'keins'}")
    print(f"Pruefsummen korrekt   : {ok}")
    print(f"Pruefsummen abweichend: {mismatch}")
    print(f"Dateien fehlend       : {missing}")

    if problems:
        print("\nProbleme (erste 20):")
        for p in problems[:20]:
            print(" ", p)
        return 1

    print("\nAlle Original- und Archivdateien stimmen mit der Datenbank ueberein.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
