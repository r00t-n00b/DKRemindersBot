from datetime import datetime
from zoneinfo import ZoneInfo

import main
from dkreminders_bot.parsing.parser_recurring_schedule import _add_months_clamped, compute_next_occurrence


TZ = ZoneInfo("Europe/Madrid")


def test_add_months_clamped_keeps_day_when_possible():
    dt = datetime(2026, 1, 15, 10, 0, tzinfo=TZ)

    assert _add_months_clamped(dt, 1) == datetime(2026, 2, 15, 10, 0, tzinfo=TZ)


def test_add_months_clamped_clamps_last_day():
    dt = datetime(2026, 1, 31, 10, 0, tzinfo=TZ)

    assert _add_months_clamped(dt, 1) == datetime(2026, 2, 28, 10, 0, tzinfo=TZ)


def test_compute_next_occurrence_daily_rolls_to_next_day_after_time_passed():
    after = datetime(2026, 6, 22, 10, 1, tzinfo=TZ)

    assert compute_next_occurrence("daily", {}, 10, 0, after) == datetime(2026, 6, 23, 10, 0, tzinfo=TZ)


def test_compute_next_occurrence_weekly_same_day_future_time():
    after = datetime(2026, 6, 22, 9, 0, tzinfo=TZ)  # Monday

    assert compute_next_occurrence("weekly", {"weekday": 0}, 10, 0, after) == datetime(2026, 6, 22, 10, 0, tzinfo=TZ)


def test_compute_next_occurrence_monthly_clamps_day():
    after = datetime(2026, 1, 31, 11, 0, tzinfo=TZ)

    assert compute_next_occurrence("monthly", {"day": 31}, 10, 0, after) == datetime(2026, 2, 28, 10, 0, tzinfo=TZ)


def test_main_reexports_recurring_schedule_helpers_for_existing_callers():
    assert main.compute_next_occurrence is compute_next_occurrence
    assert main._add_months_clamped is _add_months_clamped
