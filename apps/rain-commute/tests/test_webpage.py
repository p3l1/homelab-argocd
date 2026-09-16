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


def _json(html):
    return json.loads(re.search(r"let steps = (\[.*?\]);", html, re.S).group(1))


def test_date_picker_spans_the_stored_range():
    html = page(TODAY, FIRST, _steps(), 8640)
    assert f'min="{FIRST.isoformat()}"' in html
    assert f'max="{TODAY.isoformat()}"' in html
    assert f'value="{TODAY.isoformat()}"' in html


def test_steps_carry_kind_so_forecast_is_marked():
    """Wer in die Vergangenheit schaut, muss Messung von Prognose unterscheiden."""
    data = _json(page(TODAY, FIRST, _steps(), 8640))
    assert data[0]["kind"] == "ist"
    assert data[-1]["kind"] == "vorhersage"


def test_steps_use_absolute_timestamps():
    """Ein Offset zu jetzt truege nicht ueber Tagesgrenzen."""
    data = _json(page(TODAY, FIRST, _steps(), 8640))
    assert data[0]["at"].startswith("2026-09-17T07:00")
    assert data[0]["clock"] == "07:00"


def test_page_reports_how_much_is_stored():
    assert "8640 Zeitschritte" in page(TODAY, FIRST, _steps(), 8640)


def test_map_stays_a_separate_image():
    html = page(TODAY, FIRST, _steps(), 100)
    assert 'src="karte.webp"' in html
    assert "bare=1" in html
    assert "data:image/webp" not in html


def test_empty_day_does_not_break_the_page():
    html = page(TODAY, FIRST, [], 0)
    assert _json(html) == []
