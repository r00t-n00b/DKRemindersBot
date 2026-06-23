from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import main
from event_datetime import (
    compute_event_before_time,
    extract_event_datetime_from_text,
    get_self_remind_event_base,
    normalize_relative_event_date_in_text,
)


TZ = ZoneInfo("Europe/Madrid")


class DummyReminder:
    def __init__(self, remind_at, sent_at=None):
        self.remind_at = remind_at
        self.sent_at = sent_at


def test_extract_event_datetime_relative_ru():
    base = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert extract_event_datetime_from_text("завтра футбол в 15:00", base) == datetime(
        2026, 6, 23, 15, 0, tzinfo=TZ
    )


def test_extract_event_datetime_relative_en():
    base = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert extract_event_datetime_from_text("football tomorrow at 15:00", base) == datetime(
        2026, 6, 23, 15, 0, tzinfo=TZ
    )


def test_extract_event_datetime_absolute_dd_mm_with_words_between():
    base = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert extract_event_datetime_from_text("футбол 03.07 где-то в 15:00", base) == datetime(
        2026, 7, 3, 15, 0, tzinfo=TZ
    )


def test_extract_event_datetime_month_name_forms():
    base = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    assert extract_event_datetime_from_text("football on May 3 at 15:00", base) == datetime(
        2026, 5, 3, 15, 0, tzinfo=TZ
    )
    assert extract_event_datetime_from_text("football on 3 May at 15:00", base) == datetime(
        2026, 5, 3, 15, 0, tzinfo=TZ
    )


def test_extract_event_datetime_only_explicit_time_uses_nearest_future():
    base = datetime(2026, 6, 22, 16, 0, tzinfo=TZ)

    assert extract_event_datetime_from_text("футбол в 15:00", base) == datetime(
        2026, 6, 23, 15, 0, tzinfo=TZ
    )


def test_extract_event_datetime_invalid_time_returns_none():
    base = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert extract_event_datetime_from_text("футбол в 25:00", base) is None


def test_normalize_relative_event_date_in_text_replaces_first_relative_date():
    event_at = datetime(2026, 6, 23, 15, 0, tzinfo=TZ)

    assert normalize_relative_event_date_in_text("завтра футбол", event_at) == "23.06 футбол"
    assert normalize_relative_event_date_in_text("football tomorrow", event_at) == "football 23.06"


def test_get_self_remind_event_base_prefers_sent_at():
    remind_at = datetime(2026, 6, 23, 10, 0, tzinfo=TZ)
    sent_at = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert get_self_remind_event_base(DummyReminder(remind_at=remind_at, sent_at=sent_at)) is sent_at


def test_get_self_remind_event_base_falls_back_to_remind_at():
    remind_at = datetime(2026, 6, 23, 10, 0, tzinfo=TZ)

    assert get_self_remind_event_base(DummyReminder(remind_at=remind_at, sent_at=None)) is remind_at


def test_compute_event_before_time_options():
    event_at = datetime(2026, 6, 23, 15, 0, tzinfo=TZ)

    assert compute_event_before_time("20m", event_at) == event_at - timedelta(minutes=20)
    assert compute_event_before_time("1h", event_at) == event_at - timedelta(hours=1)
    assert compute_event_before_time("3h", event_at) == event_at - timedelta(hours=3)
    assert compute_event_before_time("10h", event_at) == event_at - timedelta(hours=10)
    assert compute_event_before_time("1d", event_at) == event_at - timedelta(days=1)
    assert compute_event_before_time("bad", event_at) is None


def test_main_reexports_event_datetime_helpers_for_existing_callers():
    assert main.extract_event_datetime_from_text is extract_event_datetime_from_text
    assert main.normalize_relative_event_date_in_text is normalize_relative_event_date_in_text
    assert main.get_self_remind_event_base is get_self_remind_event_base
    assert main.compute_event_before_time is compute_event_before_time
