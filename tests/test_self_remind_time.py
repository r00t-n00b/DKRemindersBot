from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main
from dkreminders_bot.callbacks.self_remind_time import compute_self_remind_time


TZ = ZoneInfo("Europe/Madrid")


def test_compute_self_remind_time_20m():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert compute_self_remind_time("20m", now) == datetime(2026, 6, 22, 8, 20, tzinfo=TZ)


def test_compute_self_remind_time_1h():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert compute_self_remind_time("1h", now) == datetime(2026, 6, 22, 9, 0, tzinfo=TZ)


def test_compute_self_remind_time_3h():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert compute_self_remind_time("3h", now) == datetime(2026, 6, 22, 11, 0, tzinfo=TZ)


def test_compute_self_remind_time_tomorrow11_keeps_existing_10am_behavior():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert compute_self_remind_time("tomorrow11", now) == datetime(2026, 6, 23, 10, 0, tzinfo=TZ)


def test_compute_self_remind_time_nextmon_from_monday_goes_next_week():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)  # Monday

    assert compute_self_remind_time("nextmon", now) == datetime(2026, 6, 29, 10, 0, tzinfo=TZ)


def test_compute_self_remind_time_rejects_unknown_option():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    with pytest.raises(ValueError):
        compute_self_remind_time("bad", now)


def test_main_reexports_compute_self_remind_time_for_existing_callers():
    assert main.compute_self_remind_time is compute_self_remind_time
