import bz2
import io
import pathlib
import struct
import sys
import tarfile

# Die Module liegen unter base/src, damit die ConfigMap sie einsammeln kann.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "base" / "src"))

ROWS, COLS = 1200, 1100
NODATA = 0x29C4          # Bit 13 gesetzt, wie in den echten Dateien


def make_composite(values=None, forecast_minutes=0, rows=ROWS, cols=COLS):
    """Baut eine RV-Datei; values ist {(zeile, spalte): mm_pro_5min}."""
    grid = [NODATA] * (rows * cols)
    for (r, c), mm in (values or {}).items():
        grid[r * cols + c] = int(round(mm * 100))
    header = (
        f"RV160720100000926BY   2640195VS 5SW  P42001H"
        f"PR E-02INT   5GP{rows:04d}x{cols:04d}"
        f"VV {forecast_minutes:03d}MF 00000008MS 1<deess>\x03"
    ).encode("latin-1")
    return header + struct.pack(f"<{rows * cols}H", *grid)


def make_archive(composites):
    """Packt Komposite so, wie der DWD sie ausliefert: tar, dann bz2."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for i, blob in enumerate(composites):
            info = tarfile.TarInfo(f"DE1200_RV2609160720_{i * 5:03d}")
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
    return bz2.compress(buf.getvalue())
