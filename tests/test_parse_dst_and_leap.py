import pytest
from datetime import datetime


def test_parse_dst_spring_nonexistent_time_keeps_local_time(main_module, tz):
    # В Europe/Madrid в 2025 DST начинается 30.03: 02:00 -> 03:00
    # 02:30 "не существует" в реальности, но текущая логика в main.py
    # создает datetime с tzinfo напрямую (без валидации).
    now = datetime(2025, 1, 24, 1, 0, tzinfo=tz)

    remind_at, text = main_module.parse_date_time_smart("30.03 02:30 - hi", now)

    assert text == "hi"
    assert remind_at.year == 2025
    assert remind_at.month == 3
    assert remind_at.day == 30
    assert remind_at.hour == 2
    assert remind_at.minute == 30
    assert remind_at.tzinfo == tz
    # Важно зафиксировать текущее поведение: получается CET (+01:00)
    assert remind_at.utcoffset().total_seconds() == 3600


def test_parse_dst_fall_ambiguous_time_uses_first_instance(main_module, tz):
    # В Europe/Madrid в 2025 DST заканчивается 26.10: 03:00 -> 02:00
    # 02:30 двусмысленно (есть два раза). Текущее поведение при прямом tzinfo
    # обычно соответствует первой инстанции (CEST, +02:00).
    now = datetime(2025, 1, 24, 1, 0, tzinfo=tz)

    remind_at, text = main_module.parse_date_time_smart("26.10 02:30 - hi", now)

    assert text == "hi"
    assert remind_at.year == 2025
    assert remind_at.month == 10
    assert remind_at.day == 26
    assert remind_at.hour == 2
    assert remind_at.minute == 30
    assert remind_at.tzinfo == tz
    assert remind_at.utcoffset().total_seconds() == 7200


def test_parse_leap_day_non_leap_year_raises(main_module, tz):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=tz)

    with pytest.raises(ValueError):
        main_module.parse_date_time_smart("29.02 12:00 - hi", now)


def test_parse_leap_day_leap_year_ok(main_module, tz):
    now = datetime(2024, 1, 24, 1, 0, tzinfo=tz)

    remind_at, text = main_module.parse_date_time_smart("29.02 12:00 - hi", now)

    assert text == "hi"
    assert remind_at.year == 2024
    assert remind_at.month == 2
    assert remind_at.day == 29
    assert remind_at.hour == 12
    assert remind_at.minute == 0
    assert remind_at.tzinfo == tz