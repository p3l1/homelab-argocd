from datetime import datetime, timedelta, timezone

import pytest
from conftest import make_composite
from radolan import parse_composite
from store import Store

UTC = timezone.utc


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "t.sqlite"))


def _small(values=None, **kw):
    return parse_composite(make_composite(values or {}, **kw)).crop(620, 322, 12, 12)


def test_roundtrip_keeps_values_and_position(store):
    when = datetime(2026, 9, 1, 7, 0, tzinfo=UTC)
    store.put(when, _small({(625, 327): 0.42}))
    back = store.get(when)
    assert back.value_at(625, 327) == pytest.approx(0.42)
    assert (back.row0, back.col0, back.rows, back.cols) == (620, 322, 12, 12)


def test_missing_timestamp_is_none(store):
    assert store.get(datetime(2026, 1, 1, tzinfo=UTC)) is None


def test_span_reports_the_range(store):
    base = datetime(2026, 9, 1, tzinfo=UTC)
    for i in range(5):
        store.put(base + timedelta(minutes=5 * i), _small())
    first, last, count = store.span()
    assert count == 5
    assert first == base
    assert last == base + timedelta(minutes=20)


def test_empty_store_has_no_span(store):
    assert store.span() == (None, None, 0)


def test_prune_drops_only_the_old(store):
    now = datetime.now(UTC)
    store.put(now - timedelta(days=40), _small())
    store.put(now - timedelta(days=2), _small())
    assert store.prune(keep_days=30) == 1
    assert store.span()[2] == 1


def test_days_are_marked_so_they_are_not_fetched_twice(store):
    assert not store.have_day("260915")
    store.mark_day("260915", 288)
    assert store.have_day("260915")


def test_put_many_writes_a_whole_day(store):
    base = datetime(2026, 9, 1, tzinfo=UTC)
    store.put_many([(base + timedelta(minutes=5 * i), _small()) for i in range(288)])
    assert store.span()[2] == 288
