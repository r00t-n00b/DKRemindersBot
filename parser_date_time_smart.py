"""High-level one-off reminder date/time parser."""

from datetime import datetime
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from parser_absolute import _parse_absolute
from parser_in_expression import _parse_in_expression
from parser_month_name_date import _parse_month_name_date
from parser_next_expression import _parse_next_expression
from parser_normalization import _normalize_on_at_phrase
from parser_relative_day import _parse_standalone_vague_time, _parse_today_tomorrow
from parser_split import _split_expr_and_text
from parser_time_tokens import VAGUE_TIME_WORDS
from parser_weekend_weekday import _parse_weekend_weekday


TZ = ZoneInfo("Europe/Madrid")


def parse_date_time_smart(s: str, now: datetime, default_time: Optional[Tuple[int, int]] = None) -> Tuple[datetime, str]:
    """
    Пытаемся понять:
    - DD.MM HH:MM - текст
    - DD.MM - текст (время по умолчанию 10:00)
    - HH:MM - текст (сегодня/завтра)
    - in/через N [minutes|hours|days|weeks] - текст
    - today/tomorrow/day after tomorrow/сегодня/завтра/послезавтра [+ optional HH:MM] - текст
    - next week/month/weekday names - текст
    - weekend/weekday/workday/выходные/будний/рабочий - текст
    """
    expr, text = _split_expr_and_text(s)
    # "завтра вечером купить молоко" раньше делилось как:
    # expr="завтра", text="вечером купить молоко".
    # Переносим vague time word в expr, чтобы получить 18:00
    # и убрать "вечером/evening" из текста напоминания.
    text_parts = text.strip().split(maxsplit=1)
    if text_parts and expr.strip().lower() in {"сегодня", "завтра", "послезавтра", "today", "tomorrow"}:
        first_text_token = text_parts[0].strip(" ,.!?:;").lower()
        if first_text_token in VAGUE_TIME_WORDS:
            expr = f"{expr.strip()} {first_text_token}".strip()
            text = text_parts[1].strip() if len(text_parts) == 2 else ""
    expr_lower = expr.lower().strip()
    expr_lower = _normalize_on_at_phrase(expr_lower)
    now = now.astimezone(TZ)

    dt = _parse_standalone_vague_time(expr_lower, now)
    if dt is not None:
        return dt, text

    tokens = expr_lower.split()
    dt = _parse_in_expression(tokens, now)
    if dt is not None:
        return dt, text

    dt = _parse_today_tomorrow(expr_lower, now, default_time=default_time)
    if dt is not None:
        return dt, text

    dt = _parse_next_expression(expr_lower, now, default_time=default_time)
    if dt is not None:
        return dt, text

    dt = _parse_weekend_weekday(expr_lower, now, default_time=default_time)
    if dt is not None:
        return dt, text

    dt = _parse_month_name_date(expr_lower, now, default_time=default_time)
    if dt is not None:
        return dt, text

    dt = _parse_absolute(expr_lower, now, default_time=default_time)
    if dt is not None:
        return dt, text

    raise ValueError("Не понял дату/время. Ожидаю формат 'дата время - текст'. Обрати внимание, что нужен - перед текстом")
