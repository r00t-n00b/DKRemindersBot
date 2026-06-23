"""Voice and Gemini reminder text normalization helpers."""

import re

from parser_lexicon import (
    MONTH_EN,
    VOICE_RU_MONTH_NORMALIZATION_MAP,
    VOICE_SPOKEN_NUMBER_REPLACEMENTS,
    WEEKDAY_EN,
    WEEKDAY_RU,
)


def _strip_voice_reminder_prefix(s: str) -> str:
    """
    Убираем естественные голосовые префиксы:
    - напомни завтра ...
    - напомнить завтра ...
    - поставь напоминание завтра ...
    - remind me tomorrow ...
    """
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s).strip()

    prefixes = [
        r"^напомни\s+мне\s+",
        r"^напомни\s+",
        r"^напомнить\s+мне\s+",
        r"^напомнить\s+",
        r"^поставь\s+напоминание\s+",
        r"^создай\s+напоминание\s+",
        r"^remind\s+me\s+",
        r"^reminder\s+",
        r"^me\s+",
    ]

    for pattern in prefixes:
        new_s = re.sub(pattern, "", s, count=1, flags=re.IGNORECASE).strip()
        if new_s != s:
            return new_s

    return s


def _normalize_voice_spoken_numbers(s: str) -> str:
    """
    MVP для русских голосовых чисел.
    Не пытаемся сделать полный NLP, только частые reminder-кейсы:
    - двадцать девятого мая
    - в восемнадцать сорок шесть
    """
    replacements = VOICE_SPOKEN_NUMBER_REPLACEMENTS

    result = s

    # Сначала длинные фразы, потом одиночные слова.
    for phrase, value in sorted(replacements.items(), key=lambda x: -len(x[0])):
        result = re.sub(
            rf"\b{re.escape(phrase)}\b",
            value,
            result,
            flags=re.IGNORECASE,
        )

    return result


def _normalize_voice_ru_months(s: str) -> str:
    month_map = VOICE_RU_MONTH_NORMALIZATION_MAP

    result = s
    for ru, en in month_map.items():
        result = re.sub(rf"\b{ru}\b", en, result, flags=re.IGNORECASE)

    return result


def _format_english_relative_interval(value: int, singular: str, plural: str) -> str:
    unit = singular if int(value) == 1 else plural
    return f"{int(value)} {unit}"


def _normalize_plain_text_relative_reminder_locally(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    s = re.sub(r"\s+", " ", raw).strip()
    s = _strip_voice_reminder_prefix(s)

    # RU:
    # "через минуту тест"
    # "через 1 минуту тест"
    # "через 5 минут тест"
    # "через час тест"
    # "через 2 часа тест"
    m = re.match(
        r"^через\s+"
        r"(?:(?P<num>\d{1,3})\s+)?"
        r"(?P<unit>минуту|минуты|минут|час|часа|часов)\s+"
        r"(?P<text>.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        num_raw = m.group("num")
        unit = m.group("unit").lower()
        reminder_text = m.group("text").strip()

        if not reminder_text:
            return ""

        if num_raw is None:
            value = 1
        else:
            value = int(num_raw)

        if value <= 0:
            return ""

        if unit.startswith("минут"):
            return f"in {_format_english_relative_interval(value, 'minute', 'minutes')} - {reminder_text}"

        if unit.startswith("час"):
            return f"in {_format_english_relative_interval(value, 'hour', 'hours')} - {reminder_text}"

    # EN:
    # "in a minute test"
    # "in 1 minute test"
    # "in 5 minutes test"
    # "in an hour test"
    # "in 2 hours test"
    m = re.match(
        r"^in\s+"
        r"(?:(?P<num>\d{1,3}|a|an)\s+)?"
        r"(?P<unit>minute|minutes|hour|hours)\s+"
        r"(?P<text>.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        num_raw = (m.group("num") or "1").lower()
        unit = m.group("unit").lower()
        reminder_text = m.group("text").strip()

        if not reminder_text:
            return ""

        value = 1 if num_raw in {"a", "an"} else int(num_raw)
        if value <= 0:
            return ""

        if unit.startswith("minute"):
            return f"in {_format_english_relative_interval(value, 'minute', 'minutes')} - {reminder_text}"

        if unit.startswith("hour"):
            return f"in {_format_english_relative_interval(value, 'hour', 'hours')} - {reminder_text}"

    return ""


def normalize_gemini_reminder_command_text(text: str) -> str:
    """
    Детерминированно дочищает Gemini output перед передачей в /remind.

    Gemini иногда возвращает человекочитаемые интервалы:
    - "каждые два часа - попить воды"
    - "каждые полтора часа - попить воды"

    Parser ожидает канонический формат:
    - "каждые 2 часа - попить воды"
    - "every 90 minutes - попить воды"
    """
    s = (text or "").strip()
    if not s:
        return ""

    number_words = {
        "одну": "1",
        "один": "1",
        "одно": "1",
        "два": "2",
        "две": "2",
        "три": "3",
        "четыре": "4",
        "пять": "5",
        "шесть": "6",
        "семь": "7",
        "восемь": "8",
        "девять": "9",
        "десять": "10",
        "одиннадцать": "11",
        "двенадцать": "12",
    }

    # "каждые полчаса - text" -> "every 30 minutes - text"
    s = re.sub(
        r"\bкажд\w*\s+полчаса\b",
        "every 30 minutes",
        s,
        flags=re.IGNORECASE,
    )

    # "каждые полтора часа - text" / "каждые полторы минуты - text"
    # Для часов переводим в минуты, чтобы parser не зависел от дробных чисел.
    s = re.sub(
        r"\bкажд\w*\s+полтор[аы]\s+час\w*\b",
        "every 90 minutes",
        s,
        flags=re.IGNORECASE,
    )

    def replace_interval_number(match):
        prefix = match.group("prefix")
        num = match.group("num")
        unit = match.group("unit")
        num_normalized = number_words.get(num.lower(), num)
        return f"{prefix} {num_normalized} {unit}"

    # "каждые два часа" -> "каждые 2 часа"
    # "каждые две недели" -> "каждые 2 недели"
    # Трогаем только конструкции после "кажд...", чтобы не портить текст напоминания.
    s = re.sub(
        r"\b(?P<prefix>кажд\w*)\s+"
        r"(?P<num>одну|один|одно|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|одиннадцать|двенадцать)\s+"
        r"(?P<unit>минут\w*|час\w*|дн\w*|недел\w*|месяц\w*)",
        replace_interval_number,
        s,
        flags=re.IGNORECASE,
    )

    return s


def normalize_voice_reminder_text(text: str) -> str:
    """
    MVP-нормализация голосового reminder-а.

    Примеры:
    - "завтра в 11 купить молоко" -> "завтра 11:00 - купить молоко"
    - "напомни завтра в 14:55 позвонить" -> "завтра 14:55 - позвонить"
    - "в следующий понедельник в 22:00 спросить" -> "следующий понедельник 22:00 - спросить"
    - "в понедельник 22:58 спросить" -> "в понедельник 22:58 - спросить"
    - "двадцать девятого мая в восемнадцать сорок шесть спросить" -> "29 may 18:46 - спросить"
    """
    raw = (text or "").strip()
    if not raw:
        return ""

    s = re.sub(r"\s+", " ", raw).strip()
    s = _strip_voice_reminder_prefix(s)
    s = _normalize_voice_spoken_numbers(s)
    s = _normalize_voice_ru_months(s)

    # "18 46" после spoken-number нормализации -> "18:46"
    s = re.sub(
        r"\b(?P<hour>\d{1,2})\s+(?P<minute>[0-5]?\d)\b",
        lambda m: (
            f"{int(m.group('hour')):02d}:{int(m.group('minute')):02d}"
            if 0 <= int(m.group("hour")) < 24 and 0 <= int(m.group("minute")) < 60
            else m.group(0)
        ),
        s,
    )

    # "завтра в 11 купить" / "tomorrow at 11 buy"
    m = re.match(
        r"^(?P<date>today|tomorrow|day after tomorrow|сегодня|завтра|послезавтра)\s+"
        r"(?:(?:в|at)\s+)?"
        r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"
        r"\s+(?P<text>.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        hour = int(m.group("hour"))
        minute = int(m.group("minute") or "0")
        if 0 <= hour < 24 and 0 <= minute < 60:
            return f"{m.group('date')} {hour:02d}:{minute:02d} - {m.group('text').strip()}"

    # "в следующий понедельник в 22:00 спросить"
    m = re.match(
        r"^(?:в\s+)?(?P<date>следующий|следующая|следующее|следующие|next)\s+"
        r"(?P<weekday>[a-zа-яё]+)\s+"
        r"(?:(?:в|at)\s+)?"
        r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"
        r"\s+(?P<text>.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        hour = int(m.group("hour"))
        minute = int(m.group("minute") or "0")
        if 0 <= hour < 24 and 0 <= minute < 60:
            return (
                f"{m.group('date')} {m.group('weekday')} "
                f"{hour:02d}:{minute:02d} - {m.group('text').strip()}"
            )

    # "в понедельник 22:58 спросить" / "понедельник в 22:58 спросить"
    m = re.match(
        r"^(?:в\s+)?(?P<weekday>[a-zа-яё]+)\s+"
        r"(?:(?:в|at)\s+)?"
        r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"
        r"\s+(?P<text>.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        weekday = m.group("weekday").lower()
        if weekday in WEEKDAY_EN or weekday in WEEKDAY_RU:
            hour = int(m.group("hour"))
            minute = int(m.group("minute") or "0")
            if 0 <= hour < 24 and 0 <= minute < 60:
                return f"в {weekday} {hour:02d}:{minute:02d} - {m.group('text').strip()}"

    # "29 may в 18:46 спросить" / "29 may 18:46 спросить"
    m = re.match(
        r"^(?P<day>\d{1,2})\s+(?P<month>[a-z]+)\s+"
        r"(?:(?:в|at)\s+)?"
        r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"
        r"\s+(?P<text>.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m and m.group("month").lower() in MONTH_EN:
        hour = int(m.group("hour"))
        minute = int(m.group("minute") or "0")
        if 0 <= hour < 24 and 0 <= minute < 60:
            return (
                f"{m.group('day')} {m.group('month')} "
                f"{hour:02d}:{minute:02d} - {m.group('text').strip()}"
            )

    # "в 11 купить" / "at 11 buy" -> "11:00 - buy"
    m = re.match(
        r"^(?:(?:в|at)\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s+(?P<text>.+)$",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        hour = int(m.group("hour"))
        minute = int(m.group("minute") or "0")
        if 0 <= hour < 24 and 0 <= minute < 60:
            return f"{hour:02d}:{minute:02d} - {m.group('text').strip()}"

    return s
