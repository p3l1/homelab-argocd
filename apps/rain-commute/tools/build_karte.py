#!/usr/bin/env python3
"""Erzeugt base/src/karte.png neu.

Einmalig auszufuehren - und erneut, wenn sich die Route oder der Ausschnitt
aendert. Braucht Pillow und pyproj, die der Exporter selbst nicht kennt:

    python3 -m venv .venv && .venv/bin/pip install pillow pyproj
    .venv/bin/python tools/build_karte.py

Die Kacheln kommen von OpenStreetMap. 49 Stueck sind ein Einzelabruf, kein
Massendownload - mit Pause und sprechendem User-Agent, wie es deren Richtlinie
verlangt. Wer den Ausschnitt vergroessert, sollte die Zoomstufe senken statt
hunderte Kacheln zu ziehen.
"""

import io
import math
import os
import sys
import time
import urllib.request

from PIL import Image, ImageEnhance, ImageOps
from pyproj import CRS, Transformer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "base", "src"))
from commute import ROUTE_POINTS  # noqa: E402

ZOOM, TILE = 13, 256
HALF, TARGET = 10, 1536          # 20 x 20 km, Zielkante in Pixeln
UA = {"User-Agent": "homelab-rain-commute/1.0 (einmaliger Kartenaufbau, privat)"}
OUT = os.path.join(os.path.dirname(__file__), "..", "base", "src", "karte.webp")

DE1200 = ("+proj=stere +lat_0=90 +lat_ts=60 +lon_0=10 +a=6378137 "
          "+b=6356752.3142451802 +x_0=543196.83521776 +y_0=3622588.8619310017 "
          "+units=m +no_defs")


def deg2num(lat, lon, z):
    n = 2 ** z
    return ((lon + 180) / 360 * n,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def main():
    crs = CRS.from_proj4(DE1200)
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    grid = []
    for lon, lat in ROUTE_POINTS:
        x, y = fwd.transform(lon, lat)
        grid.append((x / 1000, -y / 1000))
    mid_c = (min(c for c, _ in grid) + max(c for c, _ in grid)) / 2
    mid_r = (min(r for _, r in grid) + max(r for _, r in grid)) / 2
    c0, r0 = mid_c - HALF, mid_r - HALF

    corners = [inv.transform((c0 + dc * 2 * HALF) * 1000, -(r0 + dr * 2 * HALF) * 1000)
               for dc in (0, 1) for dr in (0, 1)]
    xs, ys = zip(*[deg2num(la, lo, ZOOM) for lo, la in corners])
    tx0, tx1, ty0, ty1 = int(min(xs)), int(max(xs)), int(min(ys)), int(max(ys))
    count = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    print(f"Zoom {ZOOM}: {count} Kacheln")

    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE))
    for i, tx in enumerate(range(tx0, tx1 + 1)):
        for ty in range(ty0, ty1 + 1):
            url = f"https://tile.openstreetmap.org/{ZOOM}/{tx}/{ty}.png"
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as resp:
                tile = Image.open(io.BytesIO(resp.read())).convert("RGB")
            mosaic.paste(tile, ((tx - tx0) * TILE, (ty - ty0) * TILE))
            time.sleep(0.12)
        print(f"  Spalte {i + 1}/{tx1 - tx0 + 1}")

    # Reprojektion: Web-Mercator und die polarstereografische DE1200 decken
    # sich nicht. Ohne diesen Schritt laegen Karte und Radar um Hunderte Meter
    # auseinander.
    src, (mw, mh) = mosaic.load(), mosaic.size
    out = Image.new("RGB", (TARGET, TARGET))
    dst = out.load()
    for py in range(TARGET):
        row = r0 + (py + 0.5) / TARGET * 2 * HALF
        for px in range(TARGET):
            col = c0 + (px + 0.5) / TARGET * 2 * HALF
            lon, lat = inv.transform(col * 1000, -row * 1000)
            mx, my = deg2num(lat, lon, ZOOM)
            sx, sy = int(mx * TILE - tx0 * TILE), int(my * TILE - ty0 * TILE)
            if 0 <= sx < mw and 0 <= sy < mh:
                dst[px, py] = src[sx, sy]

    # Abdunkeln: die Karte ist Kontext, der Regen liegt darueber und dominiert.
    grey = ImageEnhance.Contrast(ImageOps.grayscale(out)).enhance(1.7)
    dark = ImageOps.colorize(grey, black="#070b10", white="#2b3a49")
    # WebP statt PNG: bei 1536 px ist die Datei ein Fuenftel so gross, und die
    # Ortsnamen ueberstehen Qualitaet 80 sichtbar unbeschadet.
    dark.save(OUT, "WEBP", quality=80, method=6)
    print(f"{OUT}: {os.path.getsize(OUT) // 1024} kB")


if __name__ == "__main__":
    main()
