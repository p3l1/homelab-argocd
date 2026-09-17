"""Zeichnet den Radarausschnitt ueber der Karte als SVG."""

import base64
import os

from commute import ROUTE_POINTS
from radolan import grid_to_lonlat, lonlat_to_grid

# Der Ausschnitt ist fest, also ist es auch die Karte: einmal aus
# OpenStreetMap gerendert, auf das DE1200-Raster reprojiziert und
# abgedunkelt (tools/build_karte.py). Kein Kartendienst zur Laufzeit.
# 1536 px auf 640 Anzeigepixel, damit sie beim Zoomen scharf bleibt.
HALF, SCALE = 10, 32
MAP_FILE = os.path.join(os.path.dirname(__file__), "karte.webp")
_MAP_FILE = MAP_FILE

# Schwellen in mm je 5 Minuten, Farbe, Beschriftung in mm/h.
# Die Skala bricht bei Starkregen bewusst aus dem Blau aus: Gelb und Rot
# liest man als "heute lieber Bahn", helleres Blau nicht.
_SCALE = [
    (0.02, "#1d4e6b", "0,2"), (0.10, "#2277b0", "1"), (0.30, "#2fa3dd", "4"),
    (0.70, "#5fd0f0", "8"), (1.50, "#f2d24b", "18"), (3.00, "#f08c33", "36"),
    (float("inf"), "#e2483d", "36+"),
]

_INK, _MUTED, _GROUND = "#e6edf3", "#8b949e", "#0b1016"


def _colour(mm):
    for limit, colour, _ in _SCALE:
        if mm < limit:
            return colour
    return _SCALE[-1][1]


def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _map_data_uri():
    try:
        with open(_MAP_FILE, "rb") as fh:
            return "data:image/webp;base64," + base64.b64encode(fh.read()).decode()
    except OSError:
        return None


_MAP_URI = _map_data_uri()


def render_svg(composite, points=ROUTE_POINTS, when=None, half=HALF, scale=SCALE,
               with_map=True, label_offset=None, kind=None):
    """Kartenausschnitt mit Regen und Route.

    when ist die Ortszeit des dargestellten Zeitpunkts, label_offset dessen
    Abstand zu jetzt in Minuten. with_map=False laesst die eingebettete Karte
    weg - die Seite haelt sie als eigenes Bild und laedt sie nur einmal.
    kind unterscheidet Messung von Prognose: Wer in die Vergangenheit schaut,
    muss erkennen koennen, dass er kein Vorhersagebild vor sich hat.
    """
    grid = [lonlat_to_grid(lon, lat) for lon, lat in points]
    mid_c = (min(c for c, _ in grid) + max(c for c, _ in grid)) / 2
    mid_r = (min(r for _, r in grid) + max(r for _, r in grid)) / 2
    c0, r0 = mid_c - half, mid_r - half

    side = half * 2
    w = map_h = side * scale
    head, legend = 44, 46
    h = head + map_h + legend

    def px(c, r):
        return (c - c0) * scale, (r - r0) * scale + head

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="system-ui,-apple-system,sans-serif">',
    ]
    if with_map:
        parts.append(f'<rect width="{w}" height="{h}" fill="{_GROUND}"/>')
    else:
        # Kopf- und Fusszeile brauchen weiter ihren Grund, die Kartenflaeche nicht.
        parts.append(f'<rect width="{w}" height="{head}" fill="{_GROUND}"/>')
        parts.append(f'<rect y="{head + map_h}" width="{w}" height="{legend}" '
                     f'fill="{_GROUND}"/>')
    parts.append(f'<defs><clipPath id="map"><rect x="0" y="{head}" width="{w}" '
                 f'height="{map_h}"/></clipPath></defs>')
    if with_map and _MAP_URI:
        parts.append(f'<image x="0" y="{head}" width="{w}" height="{map_h}" '
                     f'href="{_MAP_URI}"/>')

    # Halbdeckend, damit Fluss und Ortsnamen unter dem Regen sichtbar bleiben.
    parts.append(f'<g opacity="0.72" clip-path="url(#map)">')
    for r in range(int(r0), int(r0) + side + 1):
        for c in range(int(c0), int(c0) + side + 1):
            mm = composite.value_at(r, c)
            if mm is None or mm < _SCALE[0][0]:
                continue
            x, y = px(c - 0.5, r - 0.5)
            parts.append(
                f'<rect class="cell" x="{x:.0f}" y="{y:.0f}" width="{scale}" '
                f'height="{scale}" fill="{_colour(mm)}"/>'
            )
    parts.append("</g>")

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (px(c, r) for c, r in grid))
    parts.append('<g clip-path="url(#map)">')
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#000000" '
                 f'stroke-width="8" stroke-linejoin="round" stroke-linecap="round" opacity="0.55"/>')
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#ffffff" '
                 f'stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>')

    for (c, r), label, anchor in ((grid[0], "Zuhause", "start"), (grid[-1], "Arbeit", "end")):
        x, y = px(c, r)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#ffffff" '
                     f'stroke="#000000" stroke-width="2.5"/>')
        dx = 13 if anchor == "start" else -13
        parts.append(
            f'<text x="{x + dx:.1f}" y="{y - 11:.1f}" fill="#ffffff" font-size="14" '
            f'font-weight="700" text-anchor="{anchor}" stroke="#000000" '
            f'stroke-width="4" paint-order="stroke" stroke-linejoin="round">'
            f'{_esc(label)}</text>')
    parts.append("</g>")

    off = composite.forecast_minutes if label_offset is None else label_offset
    if kind == "vorhersage" and off > 0:
        titel = f"Vorhersage — in {off} Minuten"
    elif off == 0:
        titel = "Regenradar — jetzt"
    elif off > 0:
        titel = f"Vorhersage — in {off} Minuten"
    elif abs(off) < 1440:
        titel = f"Gemessen — vor {abs(off)} Minuten"
    else:
        titel = f"Gemessen — vor {abs(off) // 1440} Tagen"
    parts.append(f'<text x="14" y="28" fill="{_INK}" font-size="16" font-weight="600">'
                 f'{_esc(titel)}</text>')
    if when is not None:
        parts.append(f'<text x="{w - 14}" y="28" fill="{_MUTED}" font-size="12" '
                     f'text-anchor="end">{_esc(when.strftime("%d.%m. %H:%M"))}</text>')

    ly = head + map_h + 20
    parts.append(f'<text x="14" y="{ly + 4}" fill="{_MUTED}" font-size="11">mm/h</text>')
    bx = 52
    for _, colour, label in _SCALE:
        parts.append(f'<rect x="{bx}" y="{ly - 9}" width="30" height="12" fill="{colour}"/>')
        parts.append(f'<text x="{bx + 15}" y="{ly + 19}" fill="{_MUTED}" font-size="10" '
                     f'text-anchor="middle">{_esc(label)}</text>')
        bx += 32
    parts.append(f'<text x="{w - 14}" y="{ly + 4}" fill="{_MUTED}" font-size="9" '
                 f'text-anchor="end">Karte © OpenStreetMap-Mitwirkende</text>')

    parts.append("</svg>")
    return "".join(parts)


def to_geojson(composite, points=ROUTE_POINTS, half=HALF):
    """Die nassen Rasterzellen als Polygone in Laenge/Breite.

    Fuer die Vektorkarte: MapLibre faerbt sie selbst ein und kann sie in jeder
    Zoomstufe scharf zeichnen - anders als ein Rasterbild.
    """
    grid = [lonlat_to_grid(lon, lat) for lon, lat in points]
    mid_c = (min(c for c, _ in grid) + max(c for c, _ in grid)) / 2
    mid_r = (min(r for _, r in grid) + max(r for _, r in grid)) / 2
    r0, c0 = int(mid_r - half), int(mid_c - half)
    side = half * 2 + 1

    features = []
    for r in range(r0, r0 + side):
        for c in range(c0, c0 + side):
            mm = composite.value_at(r, c)
            if mm is None or mm < _SCALE[0][0]:
                continue
            # Die Zelle spannt sich um ihren Mittelpunkt, daher die halben Schritte.
            corners = [grid_to_lonlat(c - 0.5, r - 0.5), grid_to_lonlat(c + 0.5, r - 0.5),
                       grid_to_lonlat(c + 0.5, r + 0.5), grid_to_lonlat(c - 0.5, r + 0.5)]
            ring = [[round(lon, 5), round(lat, 5)] for lon, lat in corners]
            ring.append(ring[0])
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"mm_h": round(mm * 12, 1), "colour": _colour(mm)},
            })
    return {"type": "FeatureCollection", "features": features,
            "properties": {"forecast_minutes": composite.forecast_minutes}}


def route_geojson(points=ROUTE_POINTS):
    """Die Pendelstrecke als Linie, dazu die beiden Endpunkte."""
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"kind": "route"},
             "geometry": {"type": "LineString",
                          "coordinates": [[lon, lat] for lon, lat in points]}},
            {"type": "Feature", "properties": {"kind": "end", "label": "Zuhause"},
             "geometry": {"type": "Point", "coordinates": list(points[0])}},
            {"type": "Feature", "properties": {"kind": "end", "label": "Arbeit"},
             "geometry": {"type": "Point", "coordinates": list(points[-1])}},
        ],
    }
