"""Small command parsing and formatting helpers."""

import re
from typing import List, Optional, Tuple


def parse_renamealias_args_impl(args: List[str]) -> Tuple[Optional[str], Optional[str]]:
    if not args:
        return (None, None)
    if '->' in args:
        arrow_idx = args.index('->')
        old_alias = ' '.join(args[:arrow_idx]).strip()
        new_alias = ' '.join(args[arrow_idx + 1:]).strip()
        if not old_alias or not new_alias:
            return (None, None)
        return (old_alias, new_alias)
    if len(args) < 2:
        return (None, None)
    old_alias = args[0].strip()
    new_alias = ' '.join(args[1:]).strip()
    if not old_alias or not new_alias:
        return (None, None)
    return (old_alias, new_alias)


def _rest_starts_like_datetime_impl(s: str) -> bool:
    """
    True если строка начинается похоже на дату/время/относительное выражение.
    Достаточно для кейсов типа: "02.02 - hi", "02.02 12:00 - hi", "23:40 - hi", "tomorrow 10:00 - hi".
    """
    s = s.strip().lower()
    if not s:
        return False
    if re.match('^\\d{1,2}[./-]\\d{1,2}(\\s|$)', s):
        return True
    if re.match('^\\d{1,2}[:.]\\d{2}(\\s|$)', s):
        return True
    if re.match('^(today|tomorrow|day\\s+after\\s+tomorrow|сегодня|завтра|послезавтра)\\b', s):
        return True
    if re.match('^(in|через)\\b', s):
        return True
    return False


def _strip_leading_token_in_group_impl(raw_args: str) -> Tuple[str, bool]:
    """
    В group-чате игнорируем возможные 'роутинг-токены' в начале:
    /remind TeamA 02.02 - hi
    /remind @someone 02.02 - hi

    Возвращает (новая_строка, изменилось_ли).
    """
    s = raw_args.strip()
    if not s:
        return (raw_args, False)
    if '\n' in s:
        return (raw_args, False)
    parts = s.split(maxsplit=1)
    if len(parts) != 2:
        return (raw_args, False)
    first = parts[0].strip()
    rest = parts[1].strip()
    if not first or not rest:
        return (raw_args, False)
    if _rest_starts_like_datetime_impl(rest):
        return (rest, True)
    return (raw_args, False)


def _format_bulk_result_impl(*, created: int, failed: int, error_lines):
    parts = []
    parts.append(f'Готово. Создано напоминаний: {created}.')
    if failed:
        parts.append(f'Не удалось разобрать строк: {failed}.')
        preview = error_lines[:5]
        lines = ['', 'Проблемные строки (до 5):']
        for idx, original, error in preview:
            lines.append(f"{idx}) '{original}': {error}")
        parts.append('\n'.join(lines))
    return ' '.join(parts)
