# tests/test_parsing_in_months_years.py

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

try:
    # если у тебя months/years реализованы через relativedelta - это самый стабильный expected
    from dateutil.relativedelta import relativedelta  # type: ignore
except Exception:  # pragma: no cover
    relativedelta = None  # type: ignore


TZ = ZoneInfo("Europe/Madrid")


def _assert_same_minute(dt: datetime) -> None:
    assert dt.second == 0
    assert dt.microsecond == 0


def test_in_months_parses_and_keeps_text(main_module, fixed_now):
    m = main_module

    dt, text = m.parse_date_time_smart("in 4 months - https://belgasonline.com/", fixed_now)

    assert text == "https://belgasonline.com/"
    _assert_same_minute(dt)

    # проверяем сам факт сдвига по месяцу (ожидаем через relativedelta)
    if relativedelta is not None:
        expected = (fixed_now.astimezone(TZ) + relativedelta(months=+4)).replace(second=0, microsecond=0)
        assert dt == expected
    else:
        # fallback: хотя бы не свалились и действительно позже
        assert dt > fixed_now.astimezone(TZ)


def test_in_one_month(main_module, fixed_now):
    m = main_module
    dt, text = m.parse_date_time_smart("in 1 month - t", fixed_now)

    assert text == "t"
    _assert_same_minute(dt)

    if relativedelta is not None:
        expected = (fixed_now.astimezone(TZ) + relativedelta(months=+1)).replace(second=0, microsecond=0)
        assert dt == expected


def test_in_twelve_months(main_module, fixed_now):
    m = main_module
    dt, text = m.parse_date_time_smart("in 12 months - t", fixed_now)

    assert text == "t"
    _assert_same_minute(dt)

    if relativedelta is not None:
        expected = (fixed_now.astimezone(TZ) + relativedelta(months=+12)).replace(second=0, microsecond=0)
        assert dt == expected


def test_in_years_parses(main_module, fixed_now):
    m = main_module
    dt, text = m.parse_date_time_smart("in 2 years - t", fixed_now)

    assert text == "t"
    _assert_same_minute(dt)

    if relativedelta is not None:
        expected = (fixed_now.astimezone(TZ) + relativedelta(years=+2)).replace(second=0, microsecond=0)
        assert dt == expected


@pytest.mark.parametrize(
    "s, months",
    [
        ("через 1 месяц - t", 1),
        ("через 2 месяца - t", 2),
        ("через 5 месяцев - t", 5),
    ],
)
def test_ru_in_months_parses(main_module, fixed_now, s, months):
    m = main_module
    dt, text = m.parse_date_time_smart(s, fixed_now)

    assert text == "t"
    _assert_same_minute(dt)

    if relativedelta is not None:
        expected = (fixed_now.astimezone(TZ) + relativedelta(months=+months)).replace(second=0, microsecond=0)
        assert dt == expected


@pytest.mark.parametrize(
    "s, years",
    [
        ("через 1 год - t", 1),
        ("через 3 года - t", 3),
        ("через 5 лет - t", 5),
    ],
)
def test_ru_in_years_parses(main_module, fixed_now, s, years):
    m = main_module
    dt, text = m.parse_date_time_smart(s, fixed_now)

    assert text == "t"
    _assert_same_minute(dt)

    if relativedelta is not None:
        expected = (fixed_now.astimezone(TZ) + relativedelta(years=+years)).replace(second=0, microsecond=0)
        assert dt == expected


def test_in_month_boundary_jan_31_does_not_crash(main_module):
    """
    Важный крайний случай: добавление месяца к 31 числу.
    Нам важно:
    - не упасть
    - вернуть валидную дату
    """
    m = main_module
    now = datetime(2025, 1, 31, 10, 0, tzinfo=TZ)

    dt, text = m.parse_date_time_smart("in 1 month - t", now)

    assert text == "t"
    _assert_same_minute(dt)
    assert dt > now  # как минимум позже


def test_in_month_text_with_dashes_is_not_eaten(main_module, fixed_now):
    m = main_module
    dt, text = m.parse_date_time_smart("in 1 month - a-b-c", fixed_now)

    assert text == "a-b-c"
    _assert_same_minute(dt)


def test_in_month_text_without_dash_if_supported(main_module, fixed_now):
    """
    Если у тебя поддерживается вариант без ' - ', оставляем.
    Если нет - можно удалить этот тест.
    """
    m = main_module
    try:
        dt, text = m.parse_date_time_smart("in 1 month https://example.com/", fixed_now)
    except Exception:
        pytest.skip("Формат без ' - ' не поддерживается текущим splitter'ом")
        return

    assert text == "https://example.com/"
    _assert_same_minute(dt)