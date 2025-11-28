import asyncio
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from zoneinfo import ZoneInfo

from telegram import Update, Chat, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# ===== Настройки =====

TZ = ZoneInfo("Europe/Madrid")
DB_PATH = os.environ.get("DB_PATH", "/data/reminders.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ===== Модель данных =====

@dataclass
class Reminder:
    id: int
    chat_id: int
    text: str
    remind_at: datetime
    created_by: Optional[int]


# ===== Работа с БД =====

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_aliases (
            alias TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            title TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def add_reminder(
    chat_id: int,
    text: str,
    remind_at: datetime,
    created_by: Optional[int],
) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO reminders (chat_id, text, remind_at, created_by, created_at, delivered)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (
            chat_id,
            text,
            remind_at.isoformat(),
            created_by,
            datetime.now(TZ).isoformat(),
        ),
    )
    reminder_id = c.lastrowid
    conn.commit()
    conn.close()
    return reminder_id


def get_due_reminders(now: datetime) -> List[Reminder]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, remind_at, created_by
        FROM reminders
        WHERE delivered = 0 AND remind_at <= ?
        ORDER BY remind_at ASC
        """,
        (now.isoformat(),),
    )
    rows = c.fetchall()
    conn.close()
    reminders: List[Reminder] = []
    for row in rows:
        rid, chat_id, text, remind_at_str, created_by = row
        reminders.append(
            Reminder(
                id=rid,
                chat_id=chat_id,
                text=text,
                remind_at=datetime.fromisoformat(remind_at_str),
                created_by=created_by,
            )
        )
    return reminders


def mark_reminder_sent(reminder_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET delivered = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def delete_reminders(reminder_ids: List[int], chat_id: int) -> int:
    if not reminder_ids:
        return 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    qmarks = ",".join("?" for _ in reminder_ids)
    params = reminder_ids + [chat_id]
    c.execute(
        f"DELETE FROM reminders WHERE id IN ({qmarks}) AND chat_id = ?",
        params,
    )
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted


def set_chat_alias(alias: str, chat_id: int, title: Optional[str]) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO chat_aliases(alias, chat_id, title)
        VALUES (?, ?, ?)
        ON CONFLICT(alias) DO UPDATE SET
            chat_id = excluded.chat_id,
            title = excluded.title
        """,
        (alias, chat_id, title),
    )
    conn.commit()
    conn.close()


def get_chat_id_by_alias(alias: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM chat_aliases WHERE alias = ?", (alias,))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return None


def get_all_aliases():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT alias, chat_id, title FROM chat_aliases ORDER BY alias")
    rows = c.fetchall()
    conn.close()
    return rows


# ===== Парсинг времени =====

REMIND_LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<day>\d{1,2})
    [./](?P<month>\d{1,2})
    (?:                           # опциональное время
        \s+
        (?P<hour>\d{1,2})
        :
        (?P<minute>\d{2})
    )?
    \s*
    [-–—]
    \s*
    (?P<text>.+)
    $
    """,
    re.VERBOSE,
)

TIME_ONLY_RE = re.compile(
    r"""
    ^\s*
    (?P<hour>\d{1,2})
    :
    (?P<minute>\d{2})
    \s*
    [-–—]
    \s*
    (?P<text>.+)
    $
    """,
    re.VERBOSE,
)


def _parse_time_tail(tail: str) -> Optional[Tuple[int, int]]:
    """
    Хвост может быть пустым или содержать HH:MM.
    Пустой -> (11, 0)
    """
    tail = tail.strip()
    if not tail:
        return 11, 0

    m = re.fullmatch(r"(?P<h>\d{1,2}):(?P<m>\d{2})", tail)
    if not m:
        return None

    h = int(m.group("h"))
    mnt = int(m.group("m"))
    if not (0 <= h <= 23 and 0 <= mnt <= 59):
        return None
    return h, mnt


def _parse_relative_in(expr: str, now: datetime) -> Optional[datetime]:
    """
    in 2 hours / in 45 minutes / in 3 days / in 2 weeks
    """
    expr_low = expr.lower().strip()
    m = re.fullmatch(r"in\s+(\d+)\s+(\w+)", expr_low)
    if not m:
        return None

    value = int(m.group(1))
    unit = m.group(2)

    if value <= 0:
        return None

    # англ юниты
    minutes = 0
    if unit.startswith("min"):  # minute / minutes / mins
        minutes = value
    elif unit.startswith("hour"):
        minutes = value * 60
    elif unit.startswith("day"):
        minutes = value * 60 * 24
    elif unit.startswith("week"):
        minutes = value * 60 * 24 * 7
    else:
        return None

    return now + timedelta(minutes=minutes)


def _parse_relative_ru(expr: str, now: datetime) -> Optional[datetime]:
    """
    через 3 часа / через 10 минут / через 5 дней / через 2 недели
    """
    expr_low = expr.lower().strip()
    m = re.fullmatch(r"через\s+(\d+)\s+(\w+)", expr_low)
    if not m:
        return None

    value = int(m.group(1))
    unit = m.group(2)

    if value <= 0:
        return None

    minutes = 0
    # минуты
    if unit.startswith("минут"):  # минута/минуты/минут
        minutes = value
    # часы
    elif unit.startswith("час"):  # час/часа/часов
        minutes = value * 60
    # дни
    elif unit.startswith("дн"):  # день/дня/дней
        minutes = value * 60 * 24
    # недели
    elif unit.startswith("недел"):  # неделя/недели/недель
        minutes = value * 60 * 24 * 7
    else:
        return None

    return now + timedelta(minutes=minutes)


def _parse_named_days(expr: str, now: datetime) -> Optional[datetime]:
    """
    today / tomorrow / day after tomorrow (+ optional time)
    сегодня / завтра / послезавтра (+ optional time)
    """
    expr_stripped = expr.strip()
    expr_low = expr_stripped.lower()

    def build_date(delta_days: int, tail: str) -> Optional[datetime]:
        t = _parse_time_tail(tail)
        if t is None:
            return None
        h, mnt = t
        base = (now + timedelta(days=delta_days)).date()
        return datetime(base.year, base.month, base.day, h, mnt, tzinfo=TZ)

    # english
    if expr_low.startswith("today"):
        tail = expr_stripped[len("today"):].strip()
        return build_date(0, tail)

    if expr_low.startswith("tomorrow"):
        tail = expr_stripped[len("tomorrow"):].strip()
        return build_date(1, tail)

    if expr_low.startswith("day after tomorrow"):
        # фраза с пробелами, берем по длине именно этой подстроки
        prefix = "day after tomorrow"
        tail = expr_stripped[len(prefix):].strip()
        return build_date(2, tail)

    # russian
    if expr_low.startswith("сегодня"):
        tail = expr_stripped[len("сегодня"):].strip()
        return build_date(0, tail)

    if expr_low.startswith("завтра"):
        tail = expr_stripped[len("завтра"):].strip()
        return build_date(1, tail)

    if expr_low.startswith("послезавтра"):
        tail = expr_stripped[len("послезавтра"):].strip()
        return build_date(2, tail)

    return None


WEEKDAYS_EN = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

WEEKDAYS_RU = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
}


def _add_month(now: datetime) -> datetime:
    """
    Простейшее "next month": тот же день, но в следующем месяце.
    Если дня не существует (30/31), берем последний день месяца.
    Время берем 11:00 по умолчанию, дальше выставим отдельно.
    """
    year = now.year
    month = now.month + 1
    if month > 12:
        month = 1
        year += 1

    day = now.day

    # находим последний день нового месяца
    for d in range(31, 27, -1):  # 31..28
        try:
            _ = datetime(year, month, d, tzinfo=TZ)
            last_day = d
            break
        except ValueError:
            continue
    if day > last_day:
        day = last_day

    return datetime(year, month, day, 11, 0, tzinfo=TZ)


def _parse_next(expr: str, now: datetime) -> Optional[datetime]:
    """
    next Monday 10:00 / next week / next month
    следующий понедельник 10:00 / следующая неделя / следующий месяц
    """
    expr_stripped = expr.strip()
    expr_low = expr_stripped.lower()

    def parse_unit_and_time(rest_original: str, rest_low: str) -> Optional[Tuple[str, int, int]]:
        parts_orig = rest_original.split()
        parts_low = rest_low.split()
        if not parts_low:
            return None

        unit = parts_low[0]
        tail_orig = " ".join(parts_orig[1:])
        t = _parse_time_tail(tail_orig)
        if t is None:
            return None
        h, mnt = t
        return unit, h, mnt

    # EN: next ...
    if expr_low.startswith("next "):
        rest_orig = expr_stripped[5:].strip()
        rest_low = expr_low[5:].strip()
        parsed = parse_unit_and_time(rest_orig, rest_low)
        if parsed is None:
            return None
        unit, h, mnt = parsed

        # weekday
        if unit in WEEKDAYS_EN:
            target_wd = WEEKDAYS_EN[unit]
            today_wd = now.weekday()
            days_ahead = (target_wd - today_wd + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            base = (now + timedelta(days=days_ahead)).date()
            return datetime(base.year, base.month, base.day, h, mnt, tzinfo=TZ)

        # week
        if unit == "week":
            base = (now + timedelta(days=7)).date()
            return datetime(base.year, base.month, base.day, h, mnt, tzinfo=TZ)

        # month
        if unit == "month":
            base_dt = _add_month(now)
            return base_dt.replace(hour=h, minute=mnt)

        return None

    # RU: следующий / следующая / следующее ...
    for prefix in ("следующий ", "следующая ", "следующее "):
        if expr_low.startswith(prefix):
            rest_orig = expr_stripped[len(prefix):].strip()
            rest_low = expr_low[len(prefix):].strip()
            parsed = parse_unit_and_time(rest_orig, rest_low)
            if parsed is None:
                return None
            unit, h, mnt = parsed

            # русские дни недели
            if unit in WEEKDAYS_RU:
                target_wd = WEEKDAYS_RU[unit]
                today_wd = now.weekday()
                days_ahead = (target_wd - today_wd + 7) % 7
                if days_ahead == 0:
                    days_ahead = 7
                base = (now + timedelta(days=days_ahead)).date()
                return datetime(base.year, base.month, base.day, h, mnt, tzinfo=TZ)

            # неделя
            if unit.startswith("недел"):  # неделя/неделю/недели
                base = (now + timedelta(days=7)).date()
                return datetime(base.year, base.month, base.day, h, mnt, tzinfo=TZ)

            # месяц
            if unit.startswith("месяц"):
                base_dt = _add_month(now)
                return base_dt.replace(hour=h, minute=mnt)

            return None

    return None


def _parse_week_kind(expr: str, now: datetime) -> Optional[datetime]:
    """
    weekend / weekday / workday
    выходные / будний / рабочий день
    """
    expr_stripped = expr.strip()
    expr_low = expr_stripped.lower()

    def build_dt_for_date(date_obj, tail: str) -> Optional[datetime]:
        t = _parse_time_tail(tail)
        if t is None:
            return None
        h, mnt = t
        return datetime(date_obj.year, date_obj.month, date_obj.day, h, mnt, tzinfo=TZ)

    # weekend / weekday / workday (EN)
    if expr_low.startswith("weekend"):
        tail = expr_stripped[len("weekend"):].strip()
        # ближайшая суббота (если сегодня суббота и время по умолчанию еще не прошло - берем сегодня)
        today = now.date()
        today_wd = now.weekday()  # 0=Mon .. 5=Sat 6=Sun
        days_ahead = (5 - today_wd + 7) % 7
        candidate = today + timedelta(days=days_ahead)
        # если сегодня суббота и 11:00 уже прошло - переносим на следующую субботу
        if candidate == today:
            default_dt = datetime(candidate.year, candidate.month, candidate.day, 11, 0, tzinfo=TZ)
            if default_dt < now - timedelta(minutes=1):
                candidate = candidate + timedelta(days=7)
        return build_dt_for_date(candidate, tail)

    if expr_low.startswith("weekday") or expr_low.startswith("workday"):
        # первый ближайший рабочий день (пн-пт)
        prefix = "weekday" if expr_low.startswith("weekday") else "workday"
        tail = expr_stripped[len(prefix):].strip()
        today = now.date()
        date_candidate = today
        while True:
            wd = date_candidate.weekday()
            if wd < 5:  # Mon-Fri
                dt_candidate = build_dt_for_date(date_candidate, tail or "")
                if dt_candidate is None:
                    return None
                # если это сегодня и время по умолчанию уже прошло - берем следующий рабочий
                if dt_candidate < now - timedelta(minutes=1):
                    date_candidate = date_candidate + timedelta(days=1)
                    continue
                return dt_candidate
            date_candidate = date_candidate + timedelta(days=1)

    # RU: выходные
    if expr_low.startswith("выходные"):
        tail = expr_stripped[len("выходные"):].strip()
        today = now.date()
        today_wd = now.weekday()
        days_ahead = (5 - today_wd + 7) % 7
        candidate = today + timedelta(days=days_ahead)
        default_dt = datetime(candidate.year, candidate.month, candidate.day, 11, 0, tzinfo=TZ)
        if candidate == today and default_dt < now - timedelta(minutes=1):
            candidate = candidate + timedelta(days=7)
        return build_dt_for_date(candidate, tail)

    # RU: будний / рабочий день
    if expr_low.startswith("будний") or expr_low.startswith("рабочий"):
        # "будний", "будний день", "рабочий", "рабочий день"
        if expr_low.startswith("будний"):
            tail = expr_stripped[len("будний"):].strip()
        else:
            tail = expr_stripped[len("рабочий"):].strip()
        today = now.date()
        date_candidate = today
        while True:
            wd = date_candidate.weekday()
            if wd < 5:
                dt_candidate = build_dt_for_date(date_candidate, tail or "")
                if dt_candidate is None:
                    return None
                if dt_candidate < now - timedelta(minutes=1):
                    date_candidate = date_candidate + timedelta(days=1)
                    continue
                return dt_candidate
            date_candidate = date_candidate + timedelta(days=1)

    return None


def parse_date_time_smart(s: str, now: datetime) -> Tuple[datetime, str]:
    """
    Пытаемся понять:
    - DD.MM HH:MM - текст
    - DD.MM - текст (время по умолчанию 11:00)
    - HH:MM - текст (сегодня/завтра)
    - in / через N минут/часов/дней/недель
    - today / tomorrow / day after tomorrow (+ русские аналоги)
    - next Monday / next week / next month (+ русские аналоги)
    - weekend / weekday / workday (+ русские аналоги)
    """
    s = s.strip()

    # 1) Старый формат: дата + (опционально) время
    m = REMIND_LINE_RE.match(s)
    if m:
        day = int(m.group("day"))
        month = int(m.group("month"))
        hour_str = m.group("hour")
        minute_str = m.group("minute")
        text = m.group("text").strip()

        if hour_str is None:
            hour = 11
            minute = 0
        else:
            hour = int(hour_str)
            minute = int(minute_str)

        year = now.year
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата или время: {e}") from e

        # Если дата уже в прошлом - считаем, что имеется в виду следующий год
        if dt < now - timedelta(minutes=1):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError as e:
                raise ValueError(
                    f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
                ) from e

        return dt, text

    # 2) Старый формат: только время
    m2 = TIME_ONLY_RE.match(s)
    if m2:
        hour = int(m2.group("hour"))
        minute = int(m2.group("minute"))
        text = m2.group("text").strip()

        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt < now - timedelta(minutes=1):
            dt = dt + timedelta(days=1)

        return dt, text

    # 3) Все "умные" варианты работают в формате:
    #   <выражение времени> - текст
    if "-" not in s:
        raise ValueError("Не понял дату/время")

    left, right = s.split("-", 1)
    time_expr = left.strip()
    text = right.strip()

    # 3.1 относительное время EN: in 2 hours
    dt = _parse_relative_in(time_expr, now)
    if dt is not None:
        return dt, text

    # 3.2 относительное время RU: через 3 часа
    dt = _parse_relative_ru(time_expr, now)
    if dt is not None:
        return dt, text

    # 3.3 today / tomorrow / (сегодня/завтра/послезавтра)
    dt = _parse_named_days(time_expr, now)
    if dt is not None:
        return dt, text

    # 3.4 next Monday / next week / next month (+ русские аналоги)
    dt = _parse_next(time_expr, now)
    if dt is not None:
        return dt, text

    # 3.5 weekend / weekday / workday (+ русские аналоги)
    dt = _parse_week_kind(time_expr, now)
    if dt is not None:
        return dt, text

    raise ValueError("Не понял дату/время")

def extract_after_command(text: str) -> str:
    """
    Убирает /remind или /remind@Bot и возвращает остальной текст.
    """
    if not text:
        return ""
    stripped = text.strip()
    parts = stripped.split(maxsplit=1)
    if not parts:
        return ""
    if not parts[0].startswith("/"):
        return stripped
    if len(parts) == 1:
        return ""
    return parts[1]


def maybe_split_alias_first_token(args_text: str) -> Tuple[Optional[str], str]:
    """
    В личке: если первое словечко (на первой строке) не похоже на дату/время
    и не является ключевым словом для "умного" парсинга, считаем его alias.

    Работает и с bulk:
      "/remind football 28.11 12:00 - текст"
      "/remind football\n- 28.11 12:00 - текст"
      "/remind\n- 28.11 12:00 - текст" (без alias)
    """
    if not args_text:
        return None, ""

    lines = args_text.splitlines()
    first_line = lines[0].lstrip()
    rest_lines = "\n".join(lines[1:])

    # Пустая первая строка - значит, сразу bulk, alias нет
    if not first_line:
        return None, args_text.lstrip()

    # Если первая осмысленная строка начинается с "-", это точно bulk без alias
    if first_line.startswith("-"):
        return None, args_text.lstrip()

    first, *rest_first = first_line.split(maxsplit=1)
    first_lower = first.lower()

    # 1) Явная дата: 29.11 или 29/11 - не alias
    if re.fullmatch(r"\d{1,2}[./]\d{1,2}", first):
        return None, args_text.lstrip()

    # 2) Явное время: 23:59 - не alias
    if re.fullmatch(r"\d{1,2}:\d{2}", first):
        return None, args_text.lstrip()

    # 3) Ключевые слова "умного" парсинга - не alias
    smart_prefixes = {
        # относительное время
        "in", "через",
        # сегодня/завтра/послезавтра
        "today", "сегодня",
        "tomorrow", "завтра",
        "dayaftertomorrow", "послезавтра",
        # "next something"
        "next", "следующий", "следующая", "следующее",
        # выходные / будни / рабочий день
        "weekend", "weekday", "workday",
        "выходные", "будний", "буднийдень", "рабочий", "рабочийдень",
    }

    if first_lower in smart_prefixes:
        # Это часть выражения времени, а не alias
        return None, args_text.lstrip()

    # Иначе считаем, что это alias
    alias = first
    after_alias_first_line = rest_first[0] if rest_first else ""

    parts: List[str] = []
    if after_alias_first_line:
        parts.append(after_alias_first_line)
    if rest_lines:
        parts.append(rest_lines)

    new_args = "\n".join(parts).lstrip()
    return alias, new_args


# ===== Хендлеры команд =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет. Я твой личный бот для напоминаний.\n\n"
        "Базовый формат:\n"
        "/remind DD.MM HH:MM - текст\n"
        "Пример: /remind 28.11 12:00 - завтра футбол в 20:45\n\n"
        "Bulk (много строк сразу):\n"
        "/remind\n"
        "- 28.11 12:00 - завтра спринт Ф1 в 15:00\n"
        "- 28.11 12:00 - завтра футбол в 20:45\n\n"
        "Alias чата для лички:\n"
        "1) В чате: /linkchat football\n"
        "2) В личке: /remind football 28.11 12:00 - завтра футбол\n\n"
        "Умный парсинг времени:\n"
        "- Только дата: /remind 29.11 - текст (по умолчанию в 11:00)\n"
        "- Только время: /remind 23:59 - текст (сегодня, или завтра, если время уже прошло)\n"
        "- Относительное:\n"
        "    /remind in 2 hours - текст\n"
        "    /remind in 45 minutes - текст\n"
        "    /remind через 3 часа - текст\n"
        "- Завтра / послезавтра:\n"
        "    /remind tomorrow 18:00 - текст\n"
        "    /remind tomorrow - текст (11:00)\n"
        "    /remind завтра 19:00 - текст\n"
        "    /remind послезавтра - текст (11:00)\n"
        "- Следующие периоды:\n"
        "    /remind next Monday 10:00 - текст\n"
        "    /remind next week - текст\n"
        "    /remind next month - текст\n"
        "- Выходные / будни:\n"
        "    /remind weekend - текст\n"
        "    /remind weekday - текст\n"
        "    /remind workday - текст\n"
        "\n"
        "/list - показать активные напоминания для чата и удалить лишние кнопками\n"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def linkchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message

    if chat is None or message is None:
        return

    if chat.type == Chat.PRIVATE:
        await message.reply_text("Команду /linkchat нужно вызывать в групповом чате, который хочешь привязать.")
        return

    if not context.args:
        await message.reply_text("Формат: /linkchat alias\nНапример: /linkchat football")
        return

    alias = context.args[0].strip()
    if not alias:
        await message.reply_text("Alias не должен быть пустым.")
        return

    title = chat.title or chat.username or str(chat.id)
    set_chat_alias(alias, chat.id, title)

    await message.reply_text(
        f"Ок, запомнил этот чат как '{alias}'.\n"
        f"Теперь в личке можно писать:\n"
        f"/remind {alias} 28.11 12:00 - завтра футбол"
    )


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    now = datetime.now(TZ)
    raw_args = extract_after_command(message.text or "")

    if not raw_args.strip():
        await message.reply_text(
            "Формат:\n"
            "/remind DD.MM HH:MM - текст\n"
            "или без времени:\n"
            "/remind 29.11 - важный звонок\n"
            "или только время:\n"
            "/remind 23:59 - проверить двери\n"
            "или bulk:\n"
            "/remind\n"
            "- 28.11 12:00 - завтра футбол\n"
        )
        return

    is_private = chat.type == Chat.PRIVATE

    target_chat_id = chat.id
    used_alias: Optional[str] = None

    # В личке допускаем alias первым словом / первой строкой
    if is_private:
        maybe_alias, rest = maybe_split_alias_first_token(raw_args)
        if maybe_alias is not None:
            alias_chat_id = get_chat_id_by_alias(maybe_alias)
            if alias_chat_id is None:
                aliases = get_all_aliases()
                if not aliases:
                    await message.reply_text(
                        f"Alias '{maybe_alias}' не найден.\n"
                        f"Сначала зайди в нужный чат и выполни /linkchat название.\n"
                    )
                else:
                    known = ", ".join(a for a, _, _ in aliases)
                    await message.reply_text(
                        f"Alias '{maybe_alias}' не найден.\n"
                        f"Из известных: {known}"
                    )
                return

            target_chat_id = alias_chat_id
            used_alias = maybe_alias
            raw_args = rest.strip()

            if not raw_args:
                await message.reply_text(
                    "После alias нужно указать дату и текст.\n"
                    "Пример:\n"
                    f"/remind {used_alias} 28.11 12:00 - завтра футбол"
                )
                return

    # Bulk или одиночный?
    if "\n" in raw_args:
        lines = [ln.strip() for ln in raw_args.splitlines() if ln.strip()]
        created = 0
        failed = 0
        error_lines: List[str] = []

        for line in lines:
            if line.startswith("- "):
                line = line[2:].strip()
            try:
                remind_at, text = parse_date_time_smart(line, now)
                reminder_id = add_reminder(
                    chat_id=target_chat_id,
                    text=text,
                    remind_at=remind_at,
                    created_by=user.id,
                )
                created += 1
                logger.info(
                    "Создан bulk reminder id=%s chat_id=%s at=%s text=%s",
                    reminder_id,
                    target_chat_id,
                    remind_at.isoformat(),
                    text,
                )
            except Exception as e:
                failed += 1
                error_lines.append(f"'{line}': {e}")

        reply = f"Готово. Создано напоминаний: {created}."
        if failed:
            reply += f" Не удалось разобрать строк: {failed}."
        if error_lines:
            reply += "\n\nПроблемные строки (до 5):\n" + "\n".join(error_lines[:5])

        await message.reply_text(reply)
        return

    # Одиночная строка
    try:
        remind_at, text = parse_date_time_smart(raw_args.strip(), now)
    except ValueError as e:
        await message.reply_text(f"Не смог понять дату и текст: {e}")
        return

    reminder_id = add_reminder(
        chat_id=target_chat_id,
        text=text,
        remind_at=remind_at,
        created_by=user.id,
    )

    logger.info(
        "Создан reminder id=%s chat_id=%s at=%s text=%s (from chat %s, user %s)",
        reminder_id,
        target_chat_id,
        remind_at.isoformat(),
        text,
        chat.id,
        user.id,
    )

    when_str = remind_at.strftime("%d.%m %H:%M")
    if used_alias:
        await message.reply_text(
            f"Ок, напомню в чате '{used_alias}' {when_str}: {text}"
        )
    else:
        await message.reply_text(
            f"Ок, напомню {when_str}: {text}"
        )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message

    if chat is None or message is None:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, text, remind_at
        FROM reminders
        WHERE chat_id = ? AND delivered = 0
        ORDER BY remind_at ASC
        """,
        (chat.id,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        await message.reply_text("Напоминаний нет.")
        return

    lines = []
    ids: List[int] = []
    for idx, (rid, text, remind_at_str) in enumerate(rows, start=1):
        dt = datetime.fromisoformat(remind_at_str)
        ts = dt.strftime("%d.%m %H:%M")
        lines.append(f"{idx}. {ts} - {text}")
        ids.append(rid)

    context.user_data["list_ids"] = ids

    reply = "Активные напоминания:\n\n" + "\n".join(lines)

    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for idx in range(1, len(ids) + 1):
        row.append(
            InlineKeyboardButton(
                text=f"❌{idx}",
                callback_data=f"del:{idx}",
            )
        )
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(buttons)

    await message.reply_text(reply, reply_markup=keyboard)


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    if not data.startswith("del:"):
        return

    try:
        idx = int(data.split(":", 1)[1])
    except ValueError:
        return

    ids: List[int] = context.user_data.get("list_ids") or []
    if idx < 1 or idx > len(ids):
        await query.answer("Не нашел такое напоминание", show_alert=True)
        return

    rid = ids[idx - 1]
    chat = query.message.chat if query.message else None
    if chat is None:
        return

    deleted = delete_reminders([rid], chat.id)
    if not deleted:
        await query.answer("Уже удалено", show_alert=True)
        return

    ids.pop(idx - 1)
    context.user_data["list_ids"] = ids

    if not ids:
        await query.edit_message_text("Напоминаний больше нет.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    qmarks = ",".join("?" for _ in ids)
    c.execute(
        f"SELECT id, text, remind_at FROM reminders WHERE id IN ({qmarks}) ORDER BY remind_at ASC",
        ids,
    )
    rows = c.fetchall()
    conn.close()

    lines = []
    for new_idx, (rid2, text, remind_at_str) in enumerate(rows, start=1):
        dt = datetime.fromisoformat(remind_at_str)
        ts = dt.strftime("%d.%m %H:%M")
        lines.append(f"{new_idx}. {ts} - {text}")

    reply = "Активные напоминания:\n\n" + "\n".join(lines)

    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for new_idx in range(1, len(ids) + 1):
        row.append(
            InlineKeyboardButton(
                text=f"❌{new_idx}",
                callback_data=f"del:{new_idx}",
            )
        )
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(reply, reply_markup=keyboard)


# ===== Фоновый worker =====

async def reminders_worker(app: Application) -> None:
    logger.info("Запущен фоновой worker напоминаний")
    while True:
        try:
            now = datetime.now(TZ)
            due = get_due_reminders(now)
            if due:
                logger.info("Нашел %s напоминаний к отправке", len(due))
            for r in due:
                try:
                    await app.bot.send_message(chat_id=r.chat_id, text=r.text)
                    mark_reminder_sent(r.id)
                    logger.info(
                        "Отправлено напоминание id=%s в чат %s: %s (время %s)",
                        r.id,
                        r.chat_id,
                        r.text,
                        r.remind_at.isoformat(),
                    )
                except Exception:
                    logger.exception("Ошибка при отправке напоминания id=%s", r.id)
        except Exception:
            logger.exception("Ошибка в worker напоминаний")

        await asyncio.sleep(10)


async def post_init(application: Application) -> None:
    init_db()
    application.create_task(reminders_worker(application))
    logger.info("Фоновый worker напоминаний запущен из post_init")


# ===== main =====

def main() -> None:
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("Не задан BOT_TOKEN")

    application = (
        Application.builder()
        .token(bot_token)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("linkchat", linkchat_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del:\d+$"))

    logger.info("Запускаем бота polling...")
    application.run_polling()


if __name__ == "__main__":
    main()