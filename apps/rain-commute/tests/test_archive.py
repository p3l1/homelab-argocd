from datetime import datetime, timezone

from archive import _step_time


def test_step_time_reads_the_filename():
    when = _step_time("raa01-yw_10000-2609150005-dwd---bin")
    assert when == datetime(2026, 9, 15, 0, 5, tzinfo=timezone.utc)


def test_step_time_ignores_foreign_names():
    assert _step_time("irgendwas.txt") is None
