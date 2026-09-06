#!/usr/bin/env python3
"""
Prueft einen Paperless-Export gegen die Pruefsummen, die Paperless selbst fuehrt.

    ./scripts/verify-paperless-backup.py ~/backups/paperless/2026-09-06-pre-v3/export

Das Manifest enthaelt zu jedem Dokument die MD5-Summe von Original und
Archivfassung, wie sie in der Datenbank steht. Stimmen alle exportierten
Dateien damit ueberein, ist der Export inhaltlich vollstaendig - eine
Aussage, die Dateizahl und Groesse nicht treffen koennen.
"""

import hashlib
import json
import sys
from pathlib import Path


def md5(path: Path) -> str:
    h = hashlib.md5()
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
            path = export / name
            if not path.exists():
                missing += 1
                problems.append(f"FEHLT      pk={d['pk']} {name}")
            elif md5(path) == expected:
                ok += 1
            else:
                mismatch += 1
                problems.append(f"ABWEICHUNG pk={d['pk']} {name}")

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
