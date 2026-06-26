from datetime import datetime
from types import SimpleNamespace

from event_datetime import (
    compute_event_before_time,
    extract_event_datetime_from_text,
    get_self_remind_event_base,
    normalize_relative_event_date_in_text,
)
from self_remind_time import compute_self_remind_time


def test_compute_self_remind_time_accepts_naive_now_as_bot_timezone():
    result = compute_self_remind_time("20m", datetime(2026, 1, 2, 10, 0))

    assert result.isoformat() == "2026-01-02T10:20:00+01:00"


def test_extract_event_datetime_from_text_accepts_naive_base_as_bot_timezone():
    result = extract_event_datetime_from_text(
        "завтра футбол в 15:30",
        datetime(2026, 1, 2, 10, 0),
    )

    assert result.isoformat() == "2026-01-03T15:30:00+01:00"


def test_normalize_relative_event_date_accepts_naive_event_at_as_bot_timezone():
    result = normalize_relative_event_date_in_text(
        "напомни про футбол завтра",
        datetime(2026, 1, 3, 15, 30),
    )

    assert result == "напомни про футбол 03.01"


def test_get_self_remind_event_base_accepts_naive_source_datetime():
    src = SimpleNamespace(
        sent_at=None,
        remind_at=datetime(2026, 1, 2, 10, 0),
    )

    result = get_self_remind_event_base(src)

    assert result.isoformat() == "2026-01-02T10:00:00+01:00"


def test_compute_event_before_time_accepts_naive_event_at_as_bot_timezone():
    result = compute_event_before_time("1h", datetime(2026, 1, 2, 10, 0))

    assert result.isoformat() == "2026-01-02T09:00:00+01:00"
