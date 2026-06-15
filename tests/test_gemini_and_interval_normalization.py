from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def test_normalize_gemini_russian_interval_number_words(main_module):
    assert (
        main_module.normalize_gemini_reminder_command_text("каждые два часа - попить воды")
        == "каждые 2 часа - попить воды"
    )
    assert (
        main_module.normalize_gemini_reminder_command_text("каждые три дня - сделать отчет")
        == "каждые 3 дня - сделать отчет"
    )
    assert (
        main_module.normalize_gemini_reminder_command_text("каждые две недели - проверить счета")
        == "каждые 2 недели - проверить счета"
    )


def test_normalize_gemini_russian_fractional_intervals(main_module):
    assert (
        main_module.normalize_gemini_reminder_command_text("каждые полчаса - размяться")
        == "every 30 minutes - размяться"
    )
    assert (
        main_module.normalize_gemini_reminder_command_text("каждые полтора часа - попить воды")
        == "every 90 minutes - попить воды"
    )


def test_normalize_gemini_interval_does_not_touch_regular_text(main_module):
    assert (
        main_module.normalize_gemini_reminder_command_text("завтра 11:00 - купить два литра воды")
        == "завтра 11:00 - купить два литра воды"
    )


def test_parse_recurring_english_interval_units(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    for text, unit, value in [
        ("every 30 minutes - stretch", "minutes", 30),
        ("every 2 hours - drink water", "hours", 2),
        ("every 3 days - report", "days", 3),
        ("every 4 weeks - bills", "weeks", 4),
        ("every 2 months - review", "months", 2),
    ]:
        parsed = main_module.parse_recurring(text, now)
        assert parsed is not None, text
        remind_at, reminder_text, recurring_type, payload, hour, minute = parsed

        assert reminder_text
        assert recurring_type == "interval"
        assert payload["unit"] == unit
        assert payload["value"] == value
        assert hour == 10
        assert minute == 0


def test_parse_recurring_russian_interval_units(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    for text, unit, value in [
        ("каждые 30 минут - размяться", "minutes", 30),
        ("каждые 2 часа - попить воды", "hours", 2),
        ("каждые 3 дня - отчет", "days", 3),
        ("каждые 4 недели - счета", "weeks", 4),
        ("каждые 2 месяца - ревью", "months", 2),
    ]:
        parsed = main_module.parse_recurring(text, now)
        assert parsed is not None, text
        remind_at, reminder_text, recurring_type, payload, hour, minute = parsed

        assert reminder_text
        assert recurring_type == "interval"
        assert payload["unit"] == unit
        assert payload["value"] == value
        assert hour == 10
        assert minute == 0
