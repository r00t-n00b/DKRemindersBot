from dkreminders_bot.ui.presentation import format_deleted_human, format_recurring_human


def test_format_recurring_human_known_patterns():
    assert format_recurring_human("daily", {}) == "daily"
    assert format_recurring_human("weekly", {"weekday": 0}) == "weekly (Mon)"
    assert format_recurring_human("weekly_multi", {"days": [0, 1, 2, 3, 4]}) == "weekdays"
    assert format_recurring_human("weekly_multi", {"days": [5, 6]}) == "weekends"
    assert format_recurring_human("monthly", {"day": 15}) == "monthly (day 15)"
    assert format_recurring_human("yearly", {"month": 12, "day": 25}) == "yearly (Dec 25)"


def test_format_recurring_human_interval_patterns():
    assert format_recurring_human("interval", {"value": 1, "unit": "minutes"}) == "every 1 minute"
    assert format_recurring_human("interval", {"value": 2, "unit": "hours"}) == "every 2 hours"
    assert format_recurring_human("interval", {"value": 3, "unit": "days"}) == "every 3 days"
    assert format_recurring_human("interval", {"value": 4, "unit": "weeks"}) == "every 4 weeks"
    assert format_recurring_human("interval", {"value": 5, "unit": "months"}) == "every 5 months"


def test_format_recurring_human_fallbacks():
    assert format_recurring_human(None, None) == "повтор"
    assert format_recurring_human("unknown", {}) == "unknown"


def test_format_deleted_human_without_recurring_suffix():
    assert (
        format_deleted_human(
            "2026-06-22T19:30:00+02:00",
            "test reminder",
            None,
            None,
        )
        == "22.06 19:30 - test reminder"
    )


def test_format_deleted_human_with_recurring_suffix():
    assert (
        format_deleted_human(
            "2026-06-22T19:30:00+02:00",
            "test reminder",
            "daily",
            {},
        )
        == "22.06 19:30 - test reminder  🔁 daily"
    )
