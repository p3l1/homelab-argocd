from datetime import datetime
from zoneinfo import ZoneInfo

from notify import compose

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 9, 17, 7, 0, tzinfo=BERLIN)


def test_title_carries_the_decision():
    """Der Titel ist alles, was auf dem Sperrbildschirm sicher ankommt."""
    title, _ = compose({"starts_in": 20, "ends_in": 55, "peak_mm_h": 6.0,
                        "word": "mäßiger Regen"}, NOW)
    assert "07:20" in title
    assert "mäßiger Regen" in title


def test_body_says_when_how_long_and_how_hard():
    _, body = compose({"starts_in": 20, "ends_in": 55, "peak_mm_h": 6.0,
                       "word": "mäßiger Regen"}, NOW)
    assert "07:20" in body and "07:55" in body
    assert "35 Minuten" in body
    assert "6 mm/h" in body


def test_rain_already_falling_is_worded_differently():
    """'Regen ab 07:00' waere irrefuehrend, wenn es laengst regnet."""
    title, body = compose({"starts_in": 0, "ends_in": 30, "peak_mm_h": 2.0,
                           "word": "leichter Regen"}, NOW)
    assert title.startswith("Es regnet")
    assert "gerade" in body


def test_message_links_the_radar_image():
    _, body = compose({"starts_in": 10, "ends_in": 40, "peak_mm_h": 1.0,
                       "word": "Nieselregen"}, NOW)
    assert "http" in body


def test_message_carries_no_markup():
    """Die Bridge reicht den Text unformatiert weiter - Sternchen kaemen als Zeichen an."""
    _, body = compose({"starts_in": 10, "ends_in": 40, "peak_mm_h": 1.0,
                       "word": "Nieselregen"}, NOW)
    assert "**" not in body and "](" not in body
