from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from commute import (
    describe,
    intensity_word,
    ROUTE_CELLS,
    expected_rain,
    max_on_route,
    window_active,
)
from conftest import make_composite
from radolan import parse_composite

BERLIN = ZoneInfo("Europe/Berlin")


def test_route_covers_eleven_verified_cells():
    assert len(ROUTE_CELLS) == 11
    assert (625, 327) in ROUTE_CELLS      # Bornheimer Strasse
    assert (628, 332) in ROUTE_CELLS      # Konrad-Zuse-Platz


def test_max_on_route_takes_the_wettest_cell():
    """Regen irgendwo auf dem Weg macht nass - also das Maximum, nicht der Mittelwert."""
    comp = parse_composite(make_composite({(625, 327): 0.1, (627, 331): 0.9}))
    assert max_on_route(comp) == pytest.approx(0.9)


def test_max_on_route_ignores_cells_outside_the_route():
    comp = parse_composite(make_composite({(625, 327): 0.1, (700, 700): 9.9}))
    assert max_on_route(comp) == pytest.approx(0.1)


def test_max_on_route_is_none_when_radar_covers_nothing():
    """Keine Abdeckung heisst unbekannt - sonst meldete der Alarm bei Radarausfall Trockenheit."""
    assert max_on_route(parse_composite(make_composite({}))) is None


@pytest.mark.parametrize(
    "moment,active",
    [
        (datetime(2026, 9, 16, 7, 0, tzinfo=BERLIN), True),     # Mittwoch Hinweg
        (datetime(2026, 9, 16, 17, 0, tzinfo=BERLIN), True),    # Mittwoch Rueckweg
        (datetime(2026, 9, 16, 12, 0, tzinfo=BERLIN), False),   # Mittwoch Mittag
        (datetime(2026, 9, 16, 6, 0, tzinfo=BERLIN), False),    # vor dem Fenster
        (datetime(2026, 9, 18, 7, 0, tzinfo=BERLIN), True),     # Freitag
        (datetime(2026, 9, 19, 7, 0, tzinfo=BERLIN), False),    # Samstag
        (datetime(2026, 9, 20, 7, 0, tzinfo=BERLIN), False),    # Sonntag
        (datetime(2026, 9, 21, 7, 0, tzinfo=BERLIN), True),     # Montag
    ],
)
def test_window_active_covers_weekdays_only(moment, active):
    assert window_active(moment) is active


def test_window_uses_local_time_not_utc():
    """Im Sommer liegt Berlin zwei Stunden vor UTC; eine UTC-Regel feuerte zu frueh."""
    summer = datetime(2026, 7, 15, 7, 0, tzinfo=BERLIN)
    winter = datetime(2026, 1, 14, 7, 0, tzinfo=BERLIN)
    assert window_active(summer) and window_active(winter)
    assert not window_active(datetime(2026, 7, 15, 5, 0, tzinfo=BERLIN))


def test_expected_rain_only_looks_as_far_as_the_ride():
    """Regen in zwei Stunden ist fuer eine 45-Minuten-Fahrt belanglos."""
    comps = [
        parse_composite(make_composite({(625, 327): 0.0}, forecast_minutes=0)),
        parse_composite(make_composite({(625, 327): 0.3}, forecast_minutes=30)),
        parse_composite(make_composite({(625, 327): 9.0}, forecast_minutes=90)),
    ]
    assert expected_rain(comps) == pytest.approx(0.3)


def test_expected_rain_is_none_without_usable_data():
    assert expected_rain([]) is None


def test_describe_is_none_when_dry():
    comps = [parse_composite(make_composite({(625, 327): 0.0}, forecast_minutes=m))
             for m in (0, 15, 30)]
    assert describe(comps) is None


def test_describe_reports_when_rain_starts_and_ends():
    """Die Nachricht muss wann und wie lange beantworten, nicht nur ob."""
    comps = [
        parse_composite(make_composite({(625, 327): 0.0}, forecast_minutes=0)),
        parse_composite(make_composite({(625, 327): 0.0}, forecast_minutes=10)),
        parse_composite(make_composite({(625, 327): 0.5}, forecast_minutes=20)),
        parse_composite(make_composite({(625, 327): 0.9}, forecast_minutes=30)),
        parse_composite(make_composite({(625, 327): 0.0}, forecast_minutes=40)),
    ]
    d = describe(comps)
    assert d["starts_in"] == 20
    assert d["ends_in"] == 35
    assert d["peak_mm_h"] == pytest.approx(10.8)


def test_describe_marks_rain_already_falling():
    comps = [parse_composite(make_composite({(625, 327): 0.4}, forecast_minutes=0))]
    assert describe(comps)["starts_in"] == 0


def test_intensity_words_follow_the_scale():
    assert intensity_word(0.2) == "Nieselregen"
    assert intensity_word(1.5) == "leichter Regen"
    assert intensity_word(6.0) == "mäßiger Regen"
    assert intensity_word(20.0) == "starker Regen"
    assert intensity_word(80.0) == "Platzregen"
