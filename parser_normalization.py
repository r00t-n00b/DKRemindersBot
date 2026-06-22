"""Text normalization helpers for reminder parsers."""

import re
from typing import List


def _normalize_on_at_phrase(expr_lower: str) -> str:
    """
    Нормализуем:
    - on Thursday at 20:30 -> thursday 20:30
    - on Thursday 20:30 -> thursday 20:30
    - on 25 december at 20:30 -> 25 december 20:30
    - в четверг в 20.30 -> четверг 20:30
    - четверг в 20.30 -> четверг 20:30

    Важно: точку в HH.MM меняем на двоеточие только если это похоже на ВРЕМЯ (hour <= 23),
    чтобы не ломать даты вида 29.11.
    """
    s = expr_lower.strip()

    # 1) Убираем ведущий "on"
    if s.startswith("on "):
        s = s[3:].strip()

    # 2) Убираем " at " как отдельное слово
    s = re.sub(r"\bat\b", "", s).strip()
    s = re.sub(r"\s+", " ", s)

    # 3) Русское "в " в начале
    if s.startswith("в "):
        s = s[2:].strip()

    # 4) Меняем HH.MM -> HH:MM только если это действительно время.
    # ВАЖНО: если токен выглядит как дата DD.MM, не трогаем его.
    parts = s.split()
    fixed: List[str] = []
    for i, p in enumerate(parts):
        m = re.fullmatch(r"(\d{1,2})\.(\d{2})", p)
        if not m:
            fixed.append(p)
            continue

        a = int(m.group(1))
        b = int(m.group(2))

        # Если это похоже на дату (DD.MM): 1-31 и 1-12 - НЕ конвертируем.
        # Это чинит "02.02 12:00" и не ломает "29.11".
        if 1 <= a <= 31 and 1 <= b <= 12:
            fixed.append(p)
            continue

        # Иначе - это может быть время HH.MM
        if 0 <= a <= 23 and 0 <= b <= 59:
            fixed.append(f"{a}:{m.group(2)}")
            continue

        fixed.append(p)

    s = " ".join(fixed)
    s = re.sub(r"\s+", " ", s).strip()
    return s
