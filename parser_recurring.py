"""High-level recurring reminder parser."""
from time_utils import BOT_TZ, ensure_aware

import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from parser_lexicon import (
    INTERVAL_UNITS_EN,
    INTERVAL_UNITS_RU,
    MONTH_EN,
    ORDINAL_RU,
    ORDINAL_RU_COMPOUND_TENS,
    RECURRING_DAILY_ALIASES,
    RECURRING_HOURLY_ALIASES,
    RECURRING_MONTHLY_ALIASES,
    RECURRING_WEEKLY_ALIASES,
    WEEKDAY_EN,
    WEEKDAY_RU,
    tokens_match_alias,
)
from parser_recurring_schedule import compute_next_occurrence
from parser_split import _split_expr_and_text
from parser_time_tokens import _extract_time_from_tokens


TZ = BOT_TZ


def _default_time_or(value: Optional[Tuple[int, int]], fallback_hour: int, fallback_minute: int) -> Tuple[int, int]:
    return value if value is not None else (fallback_hour, fallback_minute)


def parse_recurring(raw: str, now: datetime, default_time: Optional[Tuple[int, int]] = None) -> Tuple[datetime, str, str, Dict[str, Any], int, int]:
    """
    Разбираем строки вида:
    - every monday 10:00 - текст
    - каждый понедельник 10:00 - текст
    - every weekday - текст
    - каждые выходные - текст
    - every month 15 10:00 - текст
    - каждый месяц 15 10:00 - текст
    - every 3 days - текст
    - every 2 hours - текст
    - hourly - текст
    - daily - текст
    - weekly - текст
    - monthly - текст
    - каждые 3 дня - текст
    - каждые 2 часа - текст
    - ежечасно - текст
    - ежедневно - текст
    - еженедельно - текст
    - ежемесячно - текст
    """
    expr, text = _split_expr_and_text(raw)
    expr_lower = expr.lower().strip()
    tokens = expr_lower.split()
    if not tokens:
        raise ValueError("Не понял повторяющийся формат")

    tokens_no_time, hour, minute = _extract_time_from_tokens(
        tokens,
        *_default_time_or(default_time, 10, 0),
    )
    if not tokens_no_time:
        raise ValueError("Не понял повторяющийся формат")

    first = tokens_no_time[0]

    pattern_type: Optional[str] = None
    payload: Dict[str, Any] = {}

    interval_units_en = INTERVAL_UNITS_EN

    interval_units_ru = INTERVAL_UNITS_RU

    # interval: every 3 days / каждые 3 дня / hourly / biweekly / every other week / раз в две недели
    if tokens_match_alias(tokens_no_time, RECURRING_HOURLY_ALIASES):
        pattern_type = "interval"
        payload = {"value": 1, "unit": "hours"}
    elif tokens_no_time in (["biweekly"], ["fortnightly"]):
        pattern_type = "interval"
        payload = {"value": 2, "unit": "weeks"}
    elif len(tokens_no_time) >= 3:
        second = tokens_no_time[1]
        third = tokens_no_time[2]

        if first == "every" and second.isdigit() and third in interval_units_en:
            value = int(second)
            if value <= 0:
                raise ValueError("Интервал должен быть больше нуля")
            pattern_type = "interval"
            payload = {"value": value, "unit": interval_units_en[third]}

        elif first == "every" and second == "other" and third in {"week", "weeks"}:
            pattern_type = "interval"
            payload = {"value": 2, "unit": "weeks"}

        elif first.startswith("кажд") and second.isdigit() and third in interval_units_ru:
            value = int(second)
            if value <= 0:
                raise ValueError("Интервал должен быть больше нуля")
            pattern_type = "interval"
            payload = {"value": value, "unit": interval_units_ru[third]}

        elif first == "раз" and second == "в" and third in {"две", "2"} and len(tokens_no_time) >= 4 and tokens_no_time[3] in {
            "неделю",
            "недели",
            "недель",
        }:
            pattern_type = "interval"
            payload = {"value": 2, "unit": "weeks"}

    # interval shorthand: every hour / every minute / каждый час / каждую минуту
    # Важно: НЕ трогаем every day/week/month - ниже у них есть отдельная семантика.
    if pattern_type is None and len(tokens_no_time) >= 2:
        second = tokens_no_time[1]
        if first == "every" and second in {"minute", "minutes", "min", "mins", "hour", "hours"}:
            pattern_type = "interval"
            payload = {"value": 1, "unit": interval_units_en[second]}
        elif first.startswith("кажд") and second in {"минута", "минуту", "минуты", "минут", "мин", "час", "часа", "часов"}:
            pattern_type = "interval"
            payload = {"value": 1, "unit": interval_units_ru[second]}

    # daily
    if (first == "every" and len(tokens_no_time) >= 2 and tokens_no_time[1] == "day") or tokens_match_alias(
        tokens_no_time,
        RECURRING_DAILY_ALIASES,
    ):
        # every day / everyday
        pattern_type = "daily"
    elif (
        first.startswith("кажд")
        and len(tokens_no_time) >= 2
        and (
            tokens_no_time[1] in {"день", "дня", "дней", "дни"}
            or tokens_no_time[1].startswith("дн")
        )
    ):
        # каждый день / каждую ... форму
        pattern_type = "daily"

    # weekly
    if pattern_type is None:
        if tokens_match_alias(tokens_no_time, RECURRING_WEEKLY_ALIASES):
            pattern_type = "weekly"
            payload = {"weekday": ensure_aware(now).astimezone(TZ).weekday()}
        elif len(tokens_no_time) >= 2:
            second = tokens_no_time[1]
            if first == "every" and second in WEEKDAY_EN:
                pattern_type = "weekly"
                payload = {"weekday": WEEKDAY_EN[second]}
            elif first == "every" and second in {"week", "weeks"}:
                pattern_type = "weekly"
                payload = {"weekday": ensure_aware(now).astimezone(TZ).weekday()}
            elif first.startswith("кажд") and second in WEEKDAY_RU:
                pattern_type = "weekly"
                payload = {"weekday": WEEKDAY_RU[second]}
            elif first.startswith("кажд") and second in {"неделю", "недели", "недель"}:
                pattern_type = "weekly"
                payload = {"weekday": ensure_aware(now).astimezone(TZ).weekday()}

    # weekly_multi: weekdays / weekends / по будням / по выходным
    if pattern_type is None:
        if (
            tokens_no_time in (["weekdays"], ["weekday"], ["workdays"], ["workday"])
            or first == "every" and any(t in {"weekday", "weekdays", "workday", "workdays"} for t in tokens_no_time[1:])
        ):
            pattern_type = "weekly_multi"
            payload = {"days": [0, 1, 2, 3, 4]}

        elif (
            tokens_no_time in (["weekends"], ["weekend"])
            or first == "every" and any(t in {"weekend", "weekends"} for t in tokens_no_time[1:])
        ):
            pattern_type = "weekly_multi"
            payload = {"days": [5, 6]}

        elif (
            first in {"по", "по-"} and len(tokens_no_time) >= 2 and any("выходн" in t for t in tokens_no_time[1:])
        ) or (
            first.startswith("кажд") and any("выходн" in t for t in tokens_no_time[1:])
        ) or (
            any(t in {"выходные", "выходным"} or "выходн" in t for t in tokens_no_time)
        ):
            pattern_type = "weekly_multi"
            payload = {"days": [5, 6]}

        elif (
            first in {"по", "по-"} and len(tokens_no_time) >= 2 and any("будн" in t or "рабоч" in t for t in tokens_no_time[1:])
        ) or (
            first.startswith("кажд") and any("будн" in t or "рабоч" in t for t in tokens_no_time[1:])
        ) or (
            any(t in {"будни", "будням", "рабочие"} or "будн" in t or "рабоч" in t for t in tokens_no_time)
        ):
            pattern_type = "weekly_multi"
            payload = {"days": [0, 1, 2, 3, 4]}

    # monthly
    if pattern_type is None:
        ordinal_ru = ORDINAL_RU

        ordinal_ru_compound_tens = ORDINAL_RU_COMPOUND_TENS

        def _parse_day_token(token: str) -> Optional[int]:
            if token.isdigit():
                return int(token)

            m = re.match(r"^(\d+)(?:st|nd|rd|th)$", token)
            if m:
                return int(m.group(1))

            return ordinal_ru.get(token)

        def _parse_day_from_tokens(tokens: list[str], start: int = 0) -> tuple[Optional[int], int]:
            if start >= len(tokens):
                return None, 0

            single = _parse_day_token(tokens[start])
            if single is not None:
                return single, 1

            if start + 1 < len(tokens) and tokens[start] in ordinal_ru_compound_tens:
                tail = _parse_day_token(tokens[start + 1])
                if tail is not None and 1 <= tail <= 9:
                    return ordinal_ru_compound_tens[tokens[start]] + tail, 2

            return None, 0

        day = None

        if tokens_match_alias(tokens_no_time, RECURRING_MONTHLY_ALIASES):
            day = ensure_aware(now).astimezone(TZ).day

        elif len(tokens_no_time) >= 2 and first == "every" and tokens_no_time[1] in {"month", "months"}:
            day = ensure_aware(now).astimezone(TZ).day
            if len(tokens_no_time) >= 3:
                parsed = _parse_day_token(tokens_no_time[2])
                if parsed is not None:
                    day = parsed

        elif len(tokens_no_time) >= 2 and first.startswith("кажд") and tokens_no_time[1].startswith("месяц"):
            day = ensure_aware(now).astimezone(TZ).day
            if len(tokens_no_time) >= 3:
                parsed = _parse_day_token(tokens_no_time[2])
                if parsed is not None:
                    day = parsed

        elif len(tokens_no_time) >= 4 and tokens_no_time[0] in {"каждое", "каждый", "каждого"}:
            parsed, consumed = _parse_day_from_tokens(tokens_no_time, 1)
            if parsed is not None and 1 + consumed < len(tokens_no_time) and tokens_no_time[1 + consumed] in {"число", "числа"}:
                day = parsed

        elif len(tokens_no_time) >= 5 and first == "every":
            parsed = _parse_day_token(tokens_no_time[1])
            if parsed is not None and tokens_no_time[2:] == ["of", "the", "month"]:
                day = parsed
        
        elif len(tokens_no_time) >= 6 and first == "on" and tokens_no_time[1] == "the":
            parsed = _parse_day_token(tokens_no_time[2])
            if parsed is not None and tokens_no_time[3:] == ["of", "every", "month"]:
                day = parsed

        elif len(tokens_no_time) >= 5 and first == "on":
            parsed = _parse_day_token(tokens_no_time[1])
            if parsed is not None and tokens_no_time[2:] == ["of", "every", "month"]:
                day = parsed

        elif len(tokens_no_time) >= 4 and tokens_no_time[1:] == ["of", "every", "month"]:
            parsed = _parse_day_token(tokens_no_time[0])
            if parsed is not None:
                day = parsed

        elif len(tokens_no_time) >= 4:
            parsed, consumed = _parse_day_from_tokens(tokens_no_time, 0)
            if parsed is not None and consumed < len(tokens_no_time) and tokens_no_time[consumed] in {"число", "числа"} and any(t.startswith("месяц") for t in tokens_no_time[consumed + 1:]):
                day = parsed
            elif (
                "числа" in tokens_no_time
                and any(t.startswith("месяц") for t in tokens_no_time)
                and any(t.startswith("кажд") for t in tokens_no_time)
            ):
                raise ValueError("Неверный день месяца для повторяющегося напоминания")

        if day is not None:
            if not (1 <= day <= 31):
                raise ValueError("Неверный день месяца для повторяющегося напоминания")
            pattern_type = "monthly"
            payload = {"day": day}

    # yearly: yearly / every year / каждый год / every year on december 25 [10:00] - text
    if pattern_type is None:
        if tokens_no_time == ["yearly"]:
            now_local = ensure_aware(now).astimezone(TZ)
            pattern_type = "yearly"
            payload = {"month": now_local.month, "day": now_local.day}

        elif len(tokens_no_time) >= 2 and first == "every" and tokens_no_time[1] == "year":
            i = 2
            if i < len(tokens_no_time) and tokens_no_time[i] == "on":
                i += 1

            if i + 1 < len(tokens_no_time):
                month_token = tokens_no_time[i]
                day_token = tokens_no_time[i + 1]

                if month_token in MONTH_EN and day_token.isdigit():
                    month = int(MONTH_EN[month_token])
                    day = int(day_token)
                    if not (1 <= day <= 31):
                        raise ValueError("Неверный день месяца для повторяющегося напоминания")

                    pattern_type = "yearly"
                    payload = {"month": month, "day": day}
            else:
                now_local = ensure_aware(now).astimezone(TZ)
                pattern_type = "yearly"
                payload = {"month": now_local.month, "day": now_local.day}

        elif len(tokens_no_time) >= 2 and first.startswith("кажд") and tokens_no_time[1] in {"год", "года"}:
            now_local = ensure_aware(now).astimezone(TZ)
            pattern_type = "yearly"
            payload = {"month": now_local.month, "day": now_local.day}

    if pattern_type is None:
        raise ValueError("Не понял повторяющийся формат")

    first_dt = compute_next_occurrence(
        pattern_type,
        payload,
        hour,
        minute,
        now,
    )
    if first_dt is None:
        raise ValueError("Не удалось посчитать дату для повторяющегося напоминания")

    return first_dt, text, pattern_type, payload, hour, minute
