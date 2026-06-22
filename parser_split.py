"""Shared date/text splitting helpers for reminder parsers."""

import re
from typing import Tuple

from parser_lexicon import MONTH_EN


def _split_expr_and_text(s: str) -> Tuple[str, str]:
    raw = (s or "").strip()

    # Russian month name date without dash must be checked before
    # generic numeric/time splitting, otherwise "1 октября ..." becomes "01:00 - october ...".
    # Check explicit time forms first, otherwise "1 октября в 12:30 - ..." can be split
    # as expr="1 октября" and text="в 12:30 - ...".
    m = re.match(
        r"^\s*(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(?:в\s+)?\d{1,2}[:.]\d{2})\s+(?![-–—])(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    m = re.match(
        r"^\s*(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря))\s+(?![-–—]|(?:в\s+)?\d{1,2}[:.]\d{2}\b)(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()


    m = re.match(
        r"^\s*(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря))\s+(?![-–—]|(?:в\s+)?\d{1,2}[:.]\d{2}\b)(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()


    # Нормальный путь: есть дефис-разделитель
    m = re.search(r"\s-\s", raw)
    if m:
        expr = raw[: m.start()].strip()
        text = raw[m.end() :].strip()
        if not expr or not text:
            raise ValueError("Не понял дату/время или текст. Нужен формат 'дата время - текст'.")
        return expr, text

    # Фоллбек: люди забыли дефис. Разрешаем только single-line режим
    # (bulk уже режется выше и там дефисы внутри строк важны).
    # Поддерживаем безопасные форматы:
    # - DD.MM.YYYY HH:MM <text>
    # - D.M.YYYY H:MM <text>
    # - DD.MM HH:MM <text>
    # - DD.MM.YYYY <text>
    # - DD.MM <text>
    # - HH:MM <text>
    # - today/tomorrow/сегодня/завтра (+ optional HH:MM) <text>
    # - in/через N units <text>

    # 1) Абсолютная дата + время
    m = re.match(
        r"^\s*(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\s+\d{1,2}:\d{2})\s+(.+)\s*$",
        raw,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # 2) Абсолютная дата без времени
    m = re.match(r"^\s*(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)\s+(.+)\s*$", raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # 3) Только время
    m = re.match(r"^\s*(\d{1,2}:\d{2})\s+(.+)\s*$", raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # 4) today/tomorrow и т.п. (+ optional HH:MM)
    m = re.match(
        r"^\s*((?:today|tomorrow|day\s+after\s+tomorrow|сегодня|завтра|послезавтра)(?:\s+\d{1,2}:\d{2})?)\s+(.+)\s*$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # 5) in/через N units, плюс русские формы с подразумеваемой единицей:
    # "через час", "через неделю", "через день", "через минуту"
    m = re.match(
        r"^\s*((?:in|через)\s+(?:\d+\s+)?(?:minute|minutes|hour|hours|day|days|week|weeks|минуту|минут|минуты|час|часа|часов|день|дня|дней|неделю|недели|недель))\s+(.+)\s*$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # 6) month name date without dash:
    # "on March 14 отменить принтер"
    # "March 14 10:30 отменить принтер"
    # (time optional; text required)
    m = re.match(
        r"^\s*((?:on\s+)?[A-Za-z]{3,9}\s+\d{1,2}(?:\s+\d{4})?(?:\s+\d{1,2}[:.]\d{2})?)\s+(.+)\s*$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        expr = m.group(1).strip()
        text = m.group(2).strip()

        # validate month token (avoid treating random words as a month-date)
        tokens = expr.split()
        if tokens and tokens[0].lower() == "on":
            month_token = tokens[1].lower() if len(tokens) > 1 else ""
        else:
            month_token = tokens[0].lower() if tokens else ""

        if month_token in MONTH_EN:
            return expr, text

    # 7) standalone vague time word without explicit date:
    # "утром посмотреть ссылку"
    # "morning check link"
    m = re.match(
        r"^\s*((?:утром|morning|вечером|evening))\s+(.+)\s*$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    raise ValueError(
        "Не смог понять дату и текст: ожидаю формат 'дата время - текст'. "
        "Можно и без '-', но тогда нужно: 'дата [время] текст' (с пробелом)."
    )
