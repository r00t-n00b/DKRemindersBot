from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def test_extract_event_datetime_from_relative_ru_text(main_module):
    base_now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    result = main_module.extract_event_datetime_from_text(
        "завтра футбол в 15:30",
        base_now,
    )

    assert result == datetime(2026, 6, 13, 15, 30, tzinfo=TZ)


def test_extract_event_datetime_from_relative_en_text(main_module):
    base_now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    result = main_module.extract_event_datetime_from_text(
        "football tomorrow at 15:30",
        base_now,
    )

    assert result == datetime(2026, 6, 13, 15, 30, tzinfo=TZ)


def test_extract_event_datetime_from_dd_mm_text(main_module):
    base_now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    result = main_module.extract_event_datetime_from_text(
        "финал 15.07 в 21:00",
        base_now,
    )

    assert result == datetime(2026, 7, 15, 21, 0, tzinfo=TZ)


def test_extract_event_datetime_rolls_past_dd_mm_to_next_year(main_module):
    base_now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    result = main_module.extract_event_datetime_from_text(
        "старое событие 01.02 в 12:00",
        base_now,
    )

    assert result == datetime(2027, 2, 1, 12, 0, tzinfo=TZ)


def test_extract_event_datetime_returns_none_without_time(main_module):
    base_now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    assert main_module.extract_event_datetime_from_text("завтра футбол", base_now) is None
    assert main_module.extract_event_datetime_from_text("", base_now) is None


def test_normalize_relative_event_date_in_text_replaces_first_relative_date(main_module):
    event_at = datetime(2026, 6, 13, 15, 30, tzinfo=TZ)

    result = main_module.normalize_relative_event_date_in_text(
        "завтра футбол в 15:30, завтра купить пиво",
        event_at,
    )

    assert result == "13.06 футбол в 15:30, завтра купить пиво"


def test_get_self_remind_event_base_prefers_sent_at(main_module):
    remind_at = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    sent_at = datetime(2026, 6, 12, 10, 5, tzinfo=TZ)
    src = SimpleNamespace(remind_at=remind_at, sent_at=sent_at)

    assert main_module.get_self_remind_event_base(src) == sent_at


def test_get_self_remind_event_base_falls_back_to_remind_at(main_module):
    remind_at = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    src = SimpleNamespace(remind_at=remind_at, sent_at=None)

    assert main_module.get_self_remind_event_base(src) == remind_at


def test_compute_event_before_time_supported_options(main_module):
    event_at = datetime(2026, 6, 13, 15, 30, tzinfo=TZ)

    assert main_module.compute_event_before_time("20m", event_at) == event_at - timedelta(minutes=20)
    assert main_module.compute_event_before_time("1h", event_at) == event_at - timedelta(hours=1)
    assert main_module.compute_event_before_time("3h", event_at) == event_at - timedelta(hours=3)
    assert main_module.compute_event_before_time("10h", event_at) == event_at - timedelta(hours=10)
    assert main_module.compute_event_before_time("1d", event_at) == event_at - timedelta(days=1)


def test_compute_event_before_time_unknown_option_returns_none(main_module):
    event_at = datetime(2026, 6, 13, 15, 30, tzinfo=TZ)

    assert main_module.compute_event_before_time("bad", event_at) is None
