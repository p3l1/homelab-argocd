import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import make_composite
from radolan import parse_composite
from render import render_svg

BERLIN = ZoneInfo("Europe/Berlin")


def test_svg_is_wellformed_xml():
    svg = render_svg(parse_composite(make_composite({(625, 327): 1.0})))
    assert ET.fromstring(svg).tag.endswith("svg")


def test_dry_cells_are_not_drawn():
    """Ein Rechteck je Rasterzelle waeren ueber tausend Elemente - gezeichnet wird nur, was nass ist."""
    assert render_svg(parse_composite(make_composite({}))).count('class="cell"') == 0


def test_rain_cell_is_drawn_with_colour():
    svg = render_svg(parse_composite(make_composite({(625, 327): 2.0})))
    assert svg.count('class="cell"') == 1
    assert "#" in svg


def test_heavier_rain_gets_a_different_colour():
    light = render_svg(parse_composite(make_composite({(625, 327): 0.05})))
    heavy = render_svg(parse_composite(make_composite({(625, 327): 5.0})))
    assert light != heavy


def test_route_and_endpoints_are_drawn():
    svg = render_svg(parse_composite(make_composite({})))
    assert "<polyline" in svg
    assert svg.count("<circle") == 2


def test_cells_outside_the_window_are_ignored():
    """Eine Zelle am anderen Ende Deutschlands darf den Ausschnitt nicht treffen."""
    assert render_svg(parse_composite(make_composite({(300, 900): 9.9}))).count('class="cell"') == 0


def test_endpoints_are_labelled():
    """Ohne Beschriftung ist nicht erkennbar, welches Ende welches ist."""
    svg = render_svg(parse_composite(make_composite({})))
    assert "Zuhause" in svg and "Arbeit" in svg


def test_legend_explains_the_colours():
    svg = render_svg(parse_composite(make_composite({})))
    assert "mm/h" in svg


def test_map_is_embedded_and_attributed():
    """Die Karte steckt als Data-URI im Bild - kein Kartendienst zur Laufzeit."""
    svg = render_svg(parse_composite(make_composite({})))
    assert "data:image/webp;base64," in svg
    assert "OpenStreetMap" in svg


def test_rain_is_clipped_to_the_map_area():
    """Ohne Clip ragen Zellen in die Kopfzeile und ueberdecken den Zeitstempel."""
    svg = render_svg(parse_composite(make_composite({})))
    assert 'clipPath id="map"' in svg
    assert svg.count('clip-path="url(#map)"') == 2


def test_heavy_rain_leaves_the_blue_ramp():
    """Starkregen muss als Warnfarbe lesbar sein, nicht als helleres Blau."""
    from render import _colour
    assert _colour(0.5).lower() in ("#2fa3dd", "#5fd0f0")
    assert _colour(2.0).lower() == "#f08c33"
    assert _colour(9.0).lower() == "#e2483d"


def test_header_names_the_forecast_horizon():
    now = render_svg(parse_composite(make_composite({}, forecast_minutes=0)))
    later = render_svg(parse_composite(make_composite({}, forecast_minutes=45)))
    assert "jetzt" in now
    assert "in 45 Minuten" in later


def test_header_separates_measurement_from_prognosis():
    """Beim Blick in die Vergangenheit darf kein Vorhersagebild vorgetaeuscht werden."""
    comp = parse_composite(make_composite({}))
    past = render_svg(comp, label_offset=-90, kind="ist")
    ahead = render_svg(comp, label_offset=45, kind="vorhersage")
    assert "Gemessen" in past and "vor 90 Minuten" in past
    assert "Vorhersage" in ahead and "in 45 Minuten" in ahead


def test_header_counts_days_when_it_is_long_ago():
    comp = parse_composite(make_composite({}))
    assert "vor 3 Tagen" in render_svg(comp, label_offset=-3 * 1440, kind="ist")


def test_timestamp_is_shown_when_given():
    svg = render_svg(parse_composite(make_composite({})),
                     when=datetime(2026, 9, 16, 7, 15, tzinfo=BERLIN))
    assert "16.09. 07:15" in svg


def test_route_follows_real_geometry_not_cell_centres():
    """Die Linie folgt der gefahrenen Strecke; Zellmittelpunkte ergaeben eine Treppe."""
    svg = render_svg(parse_composite(make_composite({})))
    line = svg.split('<polyline points="')[1].split('"')[0]
    xs = [float(p.split(",")[0]) for p in line.split()]
    assert len(xs) == 13
    # Auf ganze Pixel gerundete Zellmittelpunkte waeren durchweg ganzzahlig.
    assert any(abs(x - round(x)) > 0.01 for x in xs)
