"""Liest das DWD-Radarkomposit RV und rechnet Koordinaten ins DE1200-Gitter."""

import array
import io
import math
import re
import sys
import tarfile

LATEST_URL = "https://opendata.dwd.de/weather/radar/composite/rv/"
# Beobachtete Vergangenheit; das RV-Verzeichnis reicht nur zwei Tage zurueck.
ARCHIVE_URL = ("https://opendata.dwd.de/climate_environment/CDC/grids_germany/"
               "5_minutes/radolan/recent/")

_A, _B = 6378137.0, 6356752.3142451802
_E = math.sqrt(1 - (_B * _B) / (_A * _A))
_LAT_TS, _LON_0 = math.radians(60.0), math.radians(10.0)
_X0, _Y0 = 543196.83521776, 3622588.8619310017

_NODATA_BIT = 0x2000
_VALUE_MASK = 0x0FFF
_PRECISION = 0.01


# Das aeltere YW-Produkt liegt auf dem 900x900-Gitter mit Kugelerde statt auf
# DE1200. Beide Gitter werden gebraucht: RV fuer jetzt und die Vorhersage,
# YW fuer alles aeltere als zwei Tage.
_R900 = 6370040.0
_X0_900, _Y0_900 = 522962.16692185, 3759144.72432902


def _t(phi):
    s = math.sin(phi)
    return math.tan(math.pi / 4 - phi / 2) / (((1 - _E * s) / (1 + _E * s)) ** (_E / 2))


_TC = _t(_LAT_TS)
_MC = math.cos(_LAT_TS) / math.sqrt(1 - _E * _E * math.sin(_LAT_TS) ** 2)


def lonlat_to_grid(lon, lat):
    """Gitterindex (spalte, zeile) im DE1200-Raster; Zeile 0 liegt im Norden."""
    rho = _A * _MC * _t(math.radians(lat)) / _TC
    dlon = math.radians(lon) - _LON_0
    x = rho * math.sin(dlon)
    y = -rho * math.cos(dlon)
    return (x + _X0) / 1000.0, -(y + _Y0) / 1000.0


def grid_to_lonlat(col, row):
    """Umkehrung von lonlat_to_grid. Die Breite folgt iterativ, weil sie in
    der ellipsoidischen Form nicht geschlossen aufloesbar ist."""
    x = col * 1000.0 - _X0
    y = -row * 1000.0 - _Y0
    rho = math.hypot(x, y)
    if rho == 0:
        return math.degrees(_LON_0), 90.0
    t = rho * _TC / (_A * _MC)
    phi = math.pi / 2 - 2 * math.atan(t)
    for _ in range(8):
        s = math.sin(phi)
        phi = math.pi / 2 - 2 * math.atan(t * ((1 - _E * s) / (1 + _E * s)) ** (_E / 2))
    lam = _LON_0 + math.atan2(x, -y)
    return math.degrees(lam), math.degrees(phi)


def lonlat_to_grid900(lon, lat):
    """Gitterindex im aelteren RADOLAN-900-Raster (Kugelerde)."""
    lat_r = math.radians(lat)
    rho = _R900 * (1 + math.sin(_LAT_TS)) * math.tan(math.pi / 4 - lat_r / 2)
    dlon = math.radians(lon) - _LON_0
    x = rho * math.sin(dlon)
    y = -rho * math.cos(dlon)
    return (x + _X0_900) / 1000.0, -(y + _Y0_900) / 1000.0


def resample_to_de1200(source, row0, col0, rows, cols, mapping):
    """Traegt ein 900er-Komposit in einen DE1200-Ausschnitt ein.

    mapping kommt aus build_mapping und ist fuer einen festen Ausschnitt
    konstant - so kostet der Umweg zur Laufzeit nur einen Indexzugriff.
    """
    out = array.array("H", [0x29C4]) * (rows * cols)
    for i, (r9, c9) in enumerate(mapping):
        if 0 <= r9 < source.rows and 0 <= c9 < source.cols:
            out[i] = source._values[r9 * source.cols + c9]
    return Composite(out, rows, cols, 0, row0, col0)


def build_mapping(row0, col0, rows, cols):
    """Fuer jede DE1200-Zelle des Ausschnitts die zustaendige 900er-Zelle."""
    out = []
    for r in range(row0, row0 + rows):
        for c in range(col0, col0 + cols):
            lon, lat = grid_to_lonlat(c, r)
            c9, r9 = lonlat_to_grid900(lon, lat)
            out.append((int(round(r9)), int(round(c9))))
    return out


class Composite:
    """Ein Zeitschritt des Komposits.

    row0/col0 verschieben den Ursprung, damit ein Ausschnitt weiterhin unter
    den Koordinaten des Gesamtgitters angesprochen wird - der Rest des
    Programms muss so nicht wissen, ob er einen Ausschnitt vor sich hat.
    """

    def __init__(self, values, rows, cols, forecast_minutes, row0=0, col0=0):
        self._values = values
        self.rows = rows
        self.cols = cols
        self.forecast_minutes = forecast_minutes
        self.row0 = row0
        self.col0 = col0

    def value_at(self, row, col):
        """mm pro 5 Minuten, oder None ausserhalb des Ausschnitts."""
        r, c = row - self.row0, col - self.col0
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return None
        raw = self._values[r * self.cols + c]
        if raw & _NODATA_BIT:
            return None
        return (raw & _VALUE_MASK) * _PRECISION

    def crop(self, row0, col0, rows, cols):
        """Ausschnitt als eigenstaendiges Composite.

        Ein voller Zeitschritt belegt 2,6 MB; fuer eine Zeitachse ueber
        Stunden waeren das Hunderte. Gebraucht wird nur der Kartenausschnitt.
        """
        out = array.array("H")
        for r in range(row0, row0 + rows):
            rr = r - self.row0
            if 0 <= rr < self.rows:
                base = rr * self.cols
                lo, hi = col0 - self.col0, col0 - self.col0 + cols
                if lo >= 0 and hi <= self.cols:
                    out.extend(self._values[base + lo:base + hi])
                    continue
            out.extend([0x29C4] * cols)   # ausserhalb: wie "keine Radardaten"
        return Composite(out, rows, cols, self.forecast_minutes, row0, col0)


def parse_composite(raw):
    end = raw.find(b"\x03")
    if end < 0:
        raise ValueError("Kopf ohne Abschlusszeichen")
    head = raw[: end + 1].decode("latin-1")

    size = re.search(r"GP\s*(\d+)x\s*(\d+)", head)
    if not size:
        raise ValueError(f"Kopf ohne GP-Feld: {head[:80]!r}")
    rows, cols = int(size.group(1)), int(size.group(2))
    # VV traegt die Vorhersagezeit und fehlt bei Messungen wie YW - dort ist
    # der Zeitschritt per Definition der Zeitpunkt selbst.
    step = re.search(r"VV\s*(\d+)", head)
    forecast = int(step.group(1)) if step else 0

    body = raw[end + 1 :]
    if len(body) < rows * cols * 2:
        raise ValueError(
            f"Datenteil unvollstaendig: {len(body)} statt {rows * cols * 2} Bytes"
        )
    # array.array statt struct.unpack: Ein Tupel aus 1,32 Mio Python-Ints belegt
    # rund 47 MB je Zeitschritt, das kompakte Array nur 2,6 MB.
    values = array.array("H")
    values.frombytes(body[: rows * cols * 2])
    if sys.byteorder != "little":
        values.byteswap()
    return Composite(values, rows, cols, forecast)


def read_archive(blob, only_first=False):
    """Entpackt ein tar.bz2 des RV-Produkts in nach Vorhersagezeit sortierte Schritte.

    only_first liest allein den Nullschritt - fuer die Historie, wo die
    Vorhersagen der alten Dateien nicht gebraucht werden.
    """
    out = []
    # "r:bz2" packt beim Lesen aus; bz2.decompress haette das ganze Tar
    # (rund 66 MB) zuvor in den Speicher gelegt.
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:bz2") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            comp = parse_composite(tar.extractfile(member).read())
            if only_first and comp.forecast_minutes != 0:
                continue
            out.append(comp)
            if only_first and out:
                break
    return sorted(out, key=lambda c: c.forecast_minutes)
