"""Command text and alias split helpers."""

import re
from typing import List, Optional, Tuple

from dkreminders_bot.parsing.parser_lexicon import MONTH_EN


def extract_after_command(text: str) -> str:
    if not text:
        return ""

    t = text.lstrip()
    if not t:
        return ""

    # Если это не команда - просто вернем строку как есть (без внешних пробелов)
    if not t.startswith("/"):
        return t.strip()

    # Команда - это первый "токен" до любого whitespace
    i = 0
    while i < len(t) and not t[i].isspace():
        i += 1

    rest = t[i:]  # тут важно сохранить переносы строк для bulk-режима
    if not rest:
        return ""

    # Убираем только пробелы/табы после команды, но НЕ убираем \n
    return rest.lstrip(" \t")


SMART_REMINDER_PREFIXES = {
    "in",
    "через",
    "today",
    "сегодня",
    "tomorrow",
    "завтра",
    "dayaftertomorrow",
    "day",
    "послезавтра",
    "next",
    "следующий",
    "следующая",
    "следующее",
    "следующие",
    "weekend",
    "weekday",
    "workday",
    "выходные",
    "будний",
    "буднийдень",
    "рабочий",
    "рабочийдень",
    "every",
    "everyday",
    "daily",
    "weekly",
    "monthly",
    "каждый",
    "каждую",
    "каждое",
    "каждые",
    "on",
    "at",
    "в",
}


MONTH_REMINDER_PREFIXES = {
    "jan", "january",
    "feb", "february",
    "mar", "march",
    "apr", "april",
    "may",
    "jun", "june",
    "jul", "july",
    "aug", "august",
    "sep", "sept", "september",
    "oct", "october",
    "nov", "november",
    "dec", "december",
}


def first_token_looks_like_reminder_start(first_token: str) -> bool:
    token = first_token.strip()
    token_lower = token.lower()
    token_compact = token_lower.replace(" ", "")

    return bool(
        re.match(r"^\d{1,2}[:.]\d{2}$", token)
        or re.match(r"^\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?$", token)
        or token_compact in SMART_REMINDER_PREFIXES
        or token_lower in MONTH_REMINDER_PREFIXES
    )


def maybe_split_alias_first_token(args_text: str) -> Tuple[Optional[str], str]:
    """
    В личке: если первое словечко (на первой строке) не похоже на дату/время
    и не является ключевым словом для "умного" парсинга, считаем его alias.
    """
    if not args_text:
        return None, ""

    lines = args_text.splitlines()
    first_line = lines[0].lstrip()
    rest_lines = "\n".join(lines[1:])

    if not first_line:
        return None, args_text.lstrip()

    if first_line.startswith("-"):
        return None, args_text.lstrip()

    first, *rest_first = first_line.split(maxsplit=1)
    first_lower = first.lower()

    # DD.MM / DD/MM
    if re.fullmatch(r"\d{1,2}[./]\d{1,2}", first):
        return None, args_text.lstrip()

    # HH:MM
    if re.fullmatch(r"\d{1,2}:\d{2}", first):
        return None, args_text.lstrip()

    # Месяц с названием: "january 25 ..."
    if first_lower in MONTH_EN:
        return None, args_text.lstrip()

    # "25 january ..." (или "25 january at 20:30")
    if first_lower.isdigit() and rest_first:
        second_token = rest_first[0].lstrip().split(maxsplit=1)[0].lower()
        if second_token in MONTH_EN:
            return None, args_text.lstrip()

    if first_token_looks_like_reminder_start(first):
        return None, args_text

    alias = first
    after_alias_first_line = rest_first[0] if rest_first else ""

    parts: List[str] = []
    if after_alias_first_line:
        parts.append(after_alias_first_line)
    if rest_lines:
        parts.append(rest_lines)

    new_args = "\n".join(parts).lstrip()
    return alias, new_args
