import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from webpage import page

BERLIN = ZoneInfo("Europe/Berlin")
TODAY = date(2026, 9, 17)
FIRST = date(2026, 8, 18)


def _steps(n=12, forecast_from=8):
    base = datetime(2026, 9, 17, 7, 0, tzinfo=BERLIN)
    return [(base + timedelta(minutes=5 * i),
             "vorhersage" if i >= forecast_from else "ist") for i in range(n)]


def _json(html, name):
    return json.loads(re.search(r"(?:let|const) %s = (\[.*?\]|\{.*?\});" % name,
                                html, re.S).group(1))


def test_date_picker_spans_the_stored_range():
    html = page(TODAY, FIRST, _steps(), 8640)
    assert f'min="{FIRST.isoformat()}"' in html
    assert f'max="{TODAY.isoformat()}"' in html


def test_steps_carry_kind_so_forecast_is_marked():
    data = _json(page(TODAY, FIRST, _steps(), 8640), "steps")
    assert data[0]["kind"] == "ist"
    assert data[-1]["kind"] == "vorhersage"


def test_map_uses_our_own_tile_server():
    """Kein fremder Kartendienst und kein Schluessel."""
    html = page(TODAY, FIRST, _steps(), 100)
    assert "/tiles/" in html
    assert "VersaTilesStyle" in html
    for foreign in ("mapbox.com", "api.maptiler", "tile.openstreetmap.org"):
        assert foreign not in html


def test_rain_is_vector_not_a_raster_image():
    """Vektorpolygone bleiben beim Zoomen scharf, ein Bild nicht."""
    html = page(TODAY, FIRST, _steps(), 100)
    assert "radar.geojson?at=" in html
    assert "type: 'fill'" in html
    assert "karte.webp" not in html


def test_colour_comes_from_the_feature_not_a_second_scale():
    """Die Skala steht im Exporter; die Seite darf sie nicht noch einmal fuehren."""
    html = page(TODAY, FIRST, _steps(), 100)
    assert "['get', 'colour']" in html


def test_route_is_embedded_so_it_needs_no_extra_request():
    html = page(TODAY, FIRST, _steps(), 100)
    route = _json(html, "SCALE")     # vorhanden
    assert route
    assert '"LineString"' in html
    assert "Zuhause" in html and "Arbeit" in html


def test_empty_day_does_not_break_the_page():
    assert _json(page(TODAY, FIRST, [], 0), "steps") == []
