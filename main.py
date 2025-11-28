import asyncio
import logging
import os
import re
import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Optional, List, Tuple, Dict, Any

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
    template_id: Optional[int] = None


# ===== Работа с БД =====

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # основная таблица напоминаний (новые БД сразу с template_id)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0,
            template_id INTEGER
        )
        """
    )
    # миграция старых БД - добавляем template_id при необходимости
    c.execute("PRAGMA table_info(reminders)")
    cols = [row[1] for row in c.fetchall()]
    if "template_id" not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN template_id INTEGER")
        logger.info("DB migration: added reminders.template_id column")

    # алиасы чатов
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_aliases (
            alias TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            title TEXT
        )
        """
    )

    # таблица шаблонов повторяющихся напоминаний
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS recurring_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            pattern_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            time_hour INTEGER NOT NULL,
            time_minute INTEGER NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
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
    template_id: Optional[int] = None,
) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO reminders (chat_id, text, remind_at, created_by, created_at, delivered, template_id)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (
            chat_id,
            text,
            remind_at.isoformat(),
            created_by,
            datetime.now(TZ).isoformat(),
            template_id,
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
        SELECT id, chat_id, text, remind_at, created_by, template_id
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
        rid, chat_id, text, remind_at_str, created_by, template_id = row
        reminders.append(
            Reminder(
                id=rid,
                chat_id=chat_id,
                text=text,
                remind_at=datetime.fromisoformat(remind_at_str),
                created_by=created_by,
                template_id=template_id,
            )
        )
    return reminders


def get_reminder(reminder_id: int) -> Optional[Reminder]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, remind_at, created_by, template_id
        FROM reminders
        WHERE id = ?
        """,
        (reminder_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    rid, chat_id, text, remind_at_str, created_by, template_id = row
    return Reminder(
        id=rid,
        chat_id=chat_id,
        text=text,
        remind_at=datetime.fromisoformat(remind_at_str),
        created_by=created_by,
        template_id=template_id,
    )


def mark_reminder_sent(reminder_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET delivered = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def delete_reminders(reminder_ids: List[int], chat_id: int) -> int:
    """
    Удаляем напоминания. Если у них был template_id - деактивируем соответствующие шаблоны
    (то есть удаление повторяющегося напоминания останавливает всю серию).
    """
    if not reminder_ids:
        return 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    qmarks = ",".join("?" for _ in reminder_ids)
    params = reminder_ids + [chat_id]

    # какие шаблоны затронуты
    c.execute(
        f"SELECT DISTINCT template_id FROM reminders WHERE id IN ({qmarks}) AND chat_id = ?",
        params,
    )
    template_rows = c.fetchall()
    template_ids = [row[0] for row in template_rows if row[0] is not None]

    # удаляем сами напоминания
    c.execute(
        f"DELETE FROM reminders WHERE id IN ({qmarks}) AND chat_id = ?",
        params,
    )
    deleted = c.rowcount

    # деактивируем шаблоны
    if template_ids:
        q2 = ",".join("?" for _ in template_ids)
        c.execute(
            f"UPDATE recurring_templates SET active = 0 WHERE id IN ({q2})",
            template_ids,
        )

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


# ===== Повторяющиеся шаблоны =====

def create_recurring_template(
    chat_id: int,
    text: str,
    pattern_type: str,
    payload: Dict[str, Any],
    time_hour: int,
    time_minute: int,
    created_by: Optional[int],
) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO recurring_templates
            (chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, created_at, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            chat_id,
            text,
            pattern_type,
            json.dumps(payload, ensure_ascii=False),
            time_hour,
            time_minute,
            created_by,
            datetime.now(TZ).isoformat(),
        ),
    )
    tpl_id = c.lastrowid
    conn.commit()
    conn.close()
    return tpl_id


def get_recurring_template(template_id: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, active
        FROM recurring_templates
        WHERE id = ?
        """,
        (template_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    (
        tpl_id,
        chat_id,
        text,
        pattern_type,
        payload_json,
        time_hour,
        time_minute,
        created_by,
        active,
    ) = row
    try:
        payload = json.loads(payload_json) if payload_json else {}
    except Exception:
        payload = {}
    return {
        "id": tpl_id,
        "chat_id": chat_id,
        "text": text,
        "pattern_type": pattern_type,
        "payload": payload,
        "time_hour": time_hour,
        "time_minute": time_minute,
        "created_by": created_by,
        "active": bool(active),
    }


# ===== Парсинг времени (разовые напоминания) =====

TIME_TOKEN_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _split_expr_and_text(s: str) -> Tuple[str, str]:
    m = re.match(r"^(?P<expr>.+?)\s*[-–—]\s*(?P<text>.+)$", s.strip())
    if not m:
        raise ValueError("Ожидаю формат 'дата/время - текст'")
    expr = m.group("expr").strip()
    text = m.group("text").strip()
    if not expr or not text:
        raise ValueError("Ожидаю непустые дату/время и текст")
    return expr, text


def _extract_time_from_tokens(tokens: List[str], default_hour: int = 11, default_minute: int = 0) -> Tuple[List[str], int, int]:
    if tokens and TIME_TOKEN_RE.fullmatch(tokens[-1]):
        h_s, m_s = tokens[-1].split(":", 1)
        hour = int(h_s)
        minute = int(m_s)
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("Неверное время")
        core = tokens[:-1]
    else:
        hour = default_hour
        minute = default_minute
        core = tokens
    return core, hour, minute


def _parse_in_expression(tokens: List[str], now: datetime) -> Optional[datetime]:
    if not tokens:
        return None
    first = tokens[0]
    if first not in {"in", "через"}:
        return None
    if len(tokens) < 3:
        return None
    # "in 2 hours", "через 3 часа" и т.п.
    try:
        amount = int(tokens[1])
    except ValueError:
        return None
    unit = tokens[2]

    # английские варианты
    en_minutes = {"minute", "minutes", "min", "mins", "m"}
    en_hours = {"hour", "hours", "h", "hr", "hrs"}
    en_days = {"day", "days", "d"}
    en_weeks = {"week", "weeks", "w"}

    # русские варианты
    ru_minutes = {"минуту", "минуты", "минут", "мин", "м"}
    ru_hours = {"час", "часа", "часов", "ч"}
    ru_days = {"день", "дня", "дней"}
    ru_weeks = {"неделю", "недели", "недель", "нед"}

    delta: Optional[timedelta] = None
    if unit in en_minutes or unit in ru_minutes:
        delta = timedelta(minutes=amount)
    elif unit in en_hours or unit in ru_hours:
        delta = timedelta(hours=amount)
    elif unit in en_days or unit in ru_days:
        delta = timedelta(days=amount)
    elif unit in en_weeks or unit in ru_weeks:
        delta = timedelta(weeks=amount)

    if delta is None:
        return None

    dt = now + delta
    dt = dt.replace(second=0, microsecond=0)
    return dt


def _parse_today_tomorrow(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.lower().strip()
    # today / сегодня
    for key, days in (("today", 0), ("сегодня", 0)):
        if s.startswith(key):
            rest = s[len(key):].strip()
            tokens = rest.split() if rest else []
            tokens, hour, minute = _extract_time_from_tokens(tokens)
            base = now.astimezone(TZ).date() + timedelta(days=days)
            return datetime(base.year, base.month, base.day, hour, minute, tzinfo=TZ)
    # tomorrow / завтра
    for key, days in (("tomorrow", 1), ("завтра", 1)):
        if s.startswith(key):
            rest = s[len(key):].strip()
            tokens = rest.split() if rest else []
            tokens, hour, minute = _extract_time_from_tokens(tokens)
            base = now.astimezone(TZ).date() + timedelta(days=days)
            return datetime(base.year, base.month, base.day, hour, minute, tzinfo=TZ)
    # day after tomorrow / послезавтра
    if s.startswith("day after tomorrow"):
        rest = s[len("day after tomorrow"):].strip()
        tokens = rest.split() if rest else []
        tokens, hour, minute = _extract_time_from_tokens(tokens)
        base = now.astimezone(TZ).date() + timedelta(days=2)
        return datetime(base.year, base.month, base.day, hour, minute, tzinfo=TZ)
    if s.startswith("послезавтра"):
        rest = s[len("послезавтра"):].strip()
        tokens = rest.split() if rest else []
        tokens, hour, minute = _extract_time_from_tokens(tokens)
        base = now.astimezone(TZ).date() + timedelta(days=2)
        return datetime(base.year, base.month, base.day, hour, minute, tzinfo=TZ)
    return None


WEEKDAY_EN = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

WEEKDAY_RU = {
    "понедельник": 0,
    "понедельника": 0,
    "пн": 0,
    "вторник": 1,
    "вторника": 1,
    "вт": 1,
    "среда": 2,
    "среду": 2,
    "среды": 2,
    "ср": 2,
    "четверг": 3,
    "четверга": 3,
    "чт": 3,
    "пятница": 4,
    "пятницу": 4,
    "пятницы": 4,
    "пт": 4,
    "суббота": 5,
    "субботу": 5,
    "сб": 5,
    "воскресенье": 6,
    "воскресенья": 6,
    "вс": 6,
}


def _parse_next_expression(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.lower().strip()
    tokens = s.split()
    if not tokens:
        return None

    # "next ..." / "следующая ..."
    first = tokens[0]
    if first not in {"next", "следующий", "следующая", "следующее", "следующие"}:
        return None

    if len(tokens) == 1:
        return None

    second = tokens[1]

    local = now.astimezone(TZ)

    # next week / следующая неделя
    if second in {"week", "неделя", "неделю"}:
        base = local.date()
        cur_wd = base.weekday()
        days_until_next_monday = (7 - cur_wd) % 7
        if days_until_next_monday == 0:
            days_until_next_monday = 7
        rest_tokens = tokens[2:]
        rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens)
        target_date = base + timedelta(days=days_until_next_monday)
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=TZ,
        )

    # next month / следующий месяц
    if second in {"month", "месяц", "месяца"}:
        rest_tokens = tokens[2:]
        rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens)
        year = local.year
        month = local.month + 1
        if month > 12:
            month = 1
            year += 1
        day = local.day
        while day > 28:
            try:
                return datetime(year, month, day, hour, minute, tzinfo=TZ)
            except ValueError:
                day -= 1
        return datetime(year, month, day, hour, minute, tzinfo=TZ)

    # next Monday / следующий понедельник
    target_wd: Optional[int] = None
    if second in WEEKDAY_EN:
        target_wd = WEEKDAY_EN[second]
        rest_tokens = tokens[2:]
    elif second in WEEKDAY_RU:
        target_wd = WEEKDAY_RU[second]
        rest_tokens = tokens[2:]
    else:
        return None

    rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens)
    base = local.date()
    cur_wd = base.weekday()
    delta = (target_wd - cur_wd + 7) % 7
    if delta == 0:
        delta = 7
    target_date = base + timedelta(days=delta)
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=TZ,
    )


def _parse_weekend_weekday(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.lower().strip()
    tokens = s.split()
    if not tokens:
        return None

    local = now.astimezone(TZ)

    tokens_no_time, hour, minute = _extract_time_from_tokens(tokens)
    if not tokens_no_time:
        return None

    is_weekend = False
    is_weekday = False

    joined = " ".join(tokens_no_time)

    if "weekend" in joined or "выходн" in joined:
        is_weekend = True
    if "weekday" in joined or "workday" in joined or "будн" in joined or "рабоч" in joined:
        is_weekday = True

    if not (is_weekend or is_weekday):
        return None

    if is_weekend and is_weekday:
        return None

    if is_weekend:
        allowed = {5, 6}  # сб, вс
    else:
        allowed = {0, 1, 2, 3, 4}  # пн-пт

    for delta in range(0, 8):
        d = local.date() + timedelta(days=delta)
        if d.weekday() in allowed:
            candidate = datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ)
            if candidate > now:
                return candidate
    return None


def _parse_absolute(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.strip()
    local = now.astimezone(TZ)

    m = re.fullmatch(r"(?P<day>\d{1,2})[./](?P<month>\d{1,2})(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2}))?", s)
    if m:
        day = int(m.group("day"))
        month = int(m.group("month"))
        if m.group("hour") is not None:
            hour = int(m.group("hour"))
            minute = int(m.group("minute"))
        else:
            hour = 11
            minute = 0
        year = local.year
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата или время: {e}") from e
        if dt < now - timedelta(minutes=1):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError as e:
                raise ValueError(
                    f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
                ) from e
        return dt

    m2 = re.fullmatch(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})", s)
    if m2:
        hour = int(m2.group("hour"))
        minute = int(m2.group("minute"))
        dt = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt < now - timedelta(minutes=1):
            dt = dt + timedelta(days=1)
        return dt

    return None


def parse_date_time_smart(s: str, now: datetime) -> Tuple[datetime, str]:
    """
    Пытаемся понять:
    - DD.MM HH:MM - текст
    - DD.MM - текст (время по умолчанию 11:00)
    - HH:MM - текст (сегодня/завтра)
    - in/через N [minutes|hours|days|weeks] - текст
    - today/tomorrow/day after tomorrow/сегодня/завтра/послезавтра [+ optional HH:MM] - текст
    - next week/month/weekday names - текст
    - weekend/weekday/workday/выходные/будний/рабочий - текст
    """
    expr, text = _split_expr_and_text(s)
    expr_lower = expr.lower().strip()
    now = now.astimezone(TZ)

    tokens = expr_lower.split()
    dt = _parse_in_expression(tokens, now)
    if dt is not None:
        return dt, text

    dt = _parse_today_tomorrow(expr_lower, now)
    if dt is not None:
        return dt, text

    dt = _parse_next_expression(expr_lower, now)
    if dt is not None:
        return dt, text

    dt = _parse_weekend_weekday(expr_lower, now)
    if dt is not None:
        return dt, text

    dt = _parse_absolute(expr, now)
    if dt is not None:
        return dt, text

    raise ValueError("Не понял дату/время")


# ===== Парсинг recurring-форматов =====

def looks_like_recurring(raw: str) -> bool:
    s = raw.strip().lower()
    if not s:
        return False
    first = s.split(maxsplit=1)[0]
    return first in {"every", "everyday", "каждый", "каждую", "каждое", "каждые"}


def compute_next_occurrence(
    pattern_type: str,
    payload: Dict[str, Any],
    time_hour: int,
    time_minute: int,
    after_dt: datetime,
) -> Optional[datetime]:
    local = after_dt.astimezone(TZ)
    if pattern_type == "daily":
        candidate = local.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)
        if candidate <= after_dt:
            candidate = candidate + timedelta(days=1)
        return candidate

    if pattern_type == "weekly":
        weekday = int(payload["weekday"])
        base_date = local.date()
        cur_wd = base_date.weekday()
        delta = (weekday - cur_wd + 7) % 7
        if delta == 0:
            candidate = datetime(
                base_date.year,
                base_date.month,
                base_date.day,
                time_hour,
                time_minute,
                tzinfo=TZ,
            )
            if candidate <= after_dt:
                delta = 7
        if delta != 0:
            base_date = base_date + timedelta(days=delta)
        return datetime(
            base_date.year,
            base_date.month,
            base_date.day,
            time_hour,
            time_minute,
            tzinfo=TZ,
        )

    if pattern_type == "weekly_multi":
        days = set(int(x) for x in payload.get("days", []))
        if not days:
            return None
        for delta in range(0, 8):
            d = local.date() + timedelta(days=delta)
            if d.weekday() in days:
                candidate = datetime(d.year, d.month, d.day, time_hour, time_minute, tzinfo=TZ)
                if candidate > after_dt:
                    return candidate
        return None

    if pattern_type == "monthly":
        day = int(payload["day"])
        base = local + timedelta(minutes=1)
        year = base.year
        month = base.month
        for _ in range(24):
            try:
                candidate = datetime(year, month, day, time_hour, time_minute, tzinfo=TZ)
            except ValueError:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                continue
            if candidate <= after_dt:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                continue
            return candidate
        return None

    return None


def parse_recurring(raw: str, now: datetime) -> Tuple[datetime, str, str, Dict[str, Any], int, int]:
    """
    Разбираем строки вида:
    - every monday 10:00 - текст
    - каждый понедельник 10:00 - текст
    - every weekday - текст
    - каждые выходные - текст
    - every month 15 10:00 - текст
    - каждый месяц 15 10:00 - текст
    """
    expr, text = _split_expr_and_text(raw)
    expr_lower = expr.lower().strip()
    tokens = expr_lower.split()
    if not tokens:
        raise ValueError("Не понял повторяющийся формат")

    tokens_no_time, hour, minute = _extract_time_from_tokens(tokens)
    if not tokens_no_time:
        raise ValueError("Не понял повторяющийся формат")

    first = tokens_no_time[0]

    pattern_type: Optional[str] = None
    payload: Dict[str, Any] = {}

    # daily
    if (first == "every" and len(tokens_no_time) >= 2 and tokens_no_time[1] == "day") or (
        len(tokens_no_time) == 1 and first == "everyday"
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
    if pattern_type is None and len(tokens_no_time) >= 2:
        second = tokens_no_time[1]
        if first == "every" and second in WEEKDAY_EN:
            pattern_type = "weekly"
            payload = {"weekday": WEEKDAY_EN[second]}
        elif first.startswith("кажд") and second in WEEKDAY_RU:
            pattern_type = "weekly"
            payload = {"weekday": WEEKDAY_RU[second]}

    # weekly_multi
    if pattern_type is None:
        if first == "every" and any(t in {"weekday", "weekdays"} for t in tokens_no_time[1:]):
            pattern_type = "weekly_multi"
            payload = {"days": [0, 1, 2, 3, 4]}
        elif first == "every" and any(t in {"weekend", "weekends"} for t in tokens_no_time[1:]):
            pattern_type = "weekly_multi"
            payload = {"days": [5, 6]}
        elif first.startswith("кажд") and any("выходн" in t for t in tokens_no_time[1:]):
            pattern_type = "weekly_multi"
            payload = {"days": [5, 6]}
        elif first.startswith("кажд") and any("будн" in t or "рабоч" in t for t in tokens_no_time[1:]):
            pattern_type = "weekly_multi"
            payload = {"days": [0, 1, 2, 3, 4]}

    # monthly
    if pattern_type is None and len(tokens_no_time) >= 3:
        second = tokens_no_time[1]
        third = tokens_no_time[2]
        if first == "every" and second in {"month", "months"} and third.isdigit():
            day = int(third)
            if not (1 <= day <= 31):
                raise ValueError("Неверный день месяца для повторяющегося напоминания")
            pattern_type = "monthly"
            payload = {"day": day}
        elif first.startswith("кажд") and second.startswith("месяц") and third.isdigit():
            day = int(third)
            if not (1 <= day <= 31):
                raise ValueError("Неверный день месяца для повторяющегося напоминания")
            pattern_type = "monthly"
            payload = {"day": day}

    if pattern_type is None:
        raise ValueError("Не понял повторяющийся формат")

    first_dt = compute_next_occurrence(
        pattern_type,
        payload,
        hour,
        minute,
        now - timedelta(seconds=1),
    )
    if first_dt is None:
        raise ValueError("Не удалось посчитать дату для повторяющегося напоминания")

    return first_dt, text, pattern_type, payload, hour, minute


# ===== Парсинг alias =====

def extract_after_command(text: str) -> str:
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

    if re.fullmatch(r"\d{1,2}[./]\d{1,2}", first):
        return None, args_text.lstrip()

    if re.fullmatch(r"\d{1,2}:\d{2}", first):
        return None, args_text.lstrip()

    smart_prefixes = {
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
        "каждый",
        "каждую",
        "каждое",
        "каждые",
    }

    if first_lower in smart_prefixes:
        return None, args_text.lstrip()

    alias = first
    after_alias_first_line = rest_first[0] if rest_first else ""

    parts: List[str] = []
    if after_alias_first_line:
        parts.append(after_alias_first_line)
    if rest_lines:
        parts.append(rest_lines)

    new_args = "\n".join(parts).lstrip()
    return alias, new_args


# ===== SNOOZE клавиатуры =====

def build_snooze_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("⏰ +20 минут", callback_data=f"snooze:{reminder_id}:20m"),
            InlineKeyboardButton("⏰ +1 час", callback_data=f"snooze:{reminder_id}:1h"),
        ],
        [
            InlineKeyboardButton("⏰ +3 часа", callback_data=f"snooze:{reminder_id}:3h"),
            InlineKeyboardButton("📅 Завтра (11:00)", callback_data=f"snooze:{reminder_id}:tomorrow"),
        ],
        [
            InlineKeyboardButton("📅 Следующий понедельник (11:00)", callback_data=f"snooze:{reminder_id}:nextmon"),
            InlineKeyboardButton("📝 Кастом", callback_data=f"snooze:{reminder_id}:custom"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def build_custom_date_keyboard(reminder_id: int, start: Optional[date] = None) -> InlineKeyboardMarkup:
    if start is None:
        start = datetime.now(TZ).date()

    today = datetime.now(TZ).date()
    days = [start + timedelta(days=i) for i in range(0, 14)]
    rows: List[List[InlineKeyboardButton]] = []

    # Навигация по страницам дат
    # Левая стрелка - на 14 дней назад, но не раньше сегодняшнего дня
    prev_start = start - timedelta(days=14)
    if prev_start < today:
        prev_cb = "noop"
    else:
        prev_cb = f"snooze_page:{reminder_id}:{prev_start.isoformat()}"

    next_start = start + timedelta(days=14)
    next_cb = f"snooze_page:{reminder_id}:{next_start.isoformat()}"

    center_label = start.strftime("%d.%m")
    rows.append(
        [
            InlineKeyboardButton("◀", callback_data=prev_cb),
            InlineKeyboardButton(f"с {center_label}", callback_data="noop"),
            InlineKeyboardButton("▶", callback_data=next_cb),
        ]
    )

    # Сетка из 14 дней (2 недели)
    row: List[InlineKeyboardButton] = []
    for d in days:
        label = d.strftime("%d.%m")
        data = f"snooze_pickdate:{reminder_id}:{d.isoformat()}"
        row.append(InlineKeyboardButton(text=label, callback_data=data))
        if len(row) == 7:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton("Отмена", callback_data=f"snooze_cancel:{reminder_id}")])

    return InlineKeyboardMarkup(rows)


def build_custom_time_keyboard(reminder_id: int, date_str: str) -> InlineKeyboardMarkup:
    times = [
        "09:00", "10:00", "11:00", "12:00",
        "13:00", "14:00", "15:00", "16:00",
        "17:00", "18:00", "19:00", "20:00",
        "21:00",
    ]
    rows: List[List[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton(f"Выбор времени для {date_str}", callback_data="noop")])

    row: List[InlineKeyboardButton] = []
    for t in times:
        data = f"snooze_picktime:{reminder_id}:{date_str}:{t}"
        row.append(InlineKeyboardButton(text=t, callback_data=data))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton("Отмена", callback_data=f"snooze_cancel:{reminder_id}")])

    return InlineKeyboardMarkup(rows)


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
        "Умный парсинг времени (разовые напоминания):\n"
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
        "    /remind workday - текст\n\n"
        "Повторяющиеся напоминания:\n"
        "- Каждый день:\n"
        "    /remind every day 10:00 - текст\n"
        "    /remind каждый день 10:00 - текст\n"
        "- Каждую неделю:\n"
        "    /remind every Monday 10:00 - текст\n"
        "    /remind каждую среду 19:00 - текст\n"
        "- Только будни / только выходные:\n"
        "    /remind every weekday 09:00 - текст\n"
        "    /remind every weekend 11:00 - текст\n"
        "    /remind каждые выходные 11:00 - текст\n"
        "- Каждый месяц:\n"
        "    /remind every month 15 10:00 - текст\n"
        "    /remind каждый месяц 15 10:00 - текст\n\n"
        "После прихода напоминания можно сделать SNOOZE кнопками:\n"
        " +20 минут, +1 час, +3 часа, завтра в 11:00, следующий понедельник в 11:00, кастомная дата и время.\n\n"
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
            "или относительное:\n"
            "/remind in 2 hours - текст\n"
            "или повторяющееся:\n"
            "/remind every Monday 10:00 - текст\n"
            "или bulk:\n"
            "/remind\n"
            "- 28.11 12:00 - завтра футбол\n"
        )
        return

    is_private = chat.type == Chat.PRIVATE

    target_chat_id = chat.id
    used_alias: Optional[str] = None

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
                # поддержка recurring и в bulk
                if looks_like_recurring(line):
                    first_dt, text, pattern_type, payload, hour, minute = parse_recurring(line, now)
                    tpl_id = create_recurring_template(
                        chat_id=target_chat_id,
                        text=text,
                        pattern_type=pattern_type,
                        payload=payload,
                        time_hour=hour,
                        time_minute=minute,
                        created_by=user.id,
                    )
                    reminder_id = add_reminder(
                        chat_id=target_chat_id,
                        text=text,
                        remind_at=first_dt,
                        created_by=user.id,
                        template_id=tpl_id,
                    )
                    logger.info(
                        "Создан bulk recurring reminder id=%s tpl_id=%s chat_id=%s at=%s text=%s",
                        reminder_id,
                        tpl_id,
                        target_chat_id,
                        first_dt.isoformat(),
                        text,
                    )
                else:
                    remind_at, text = parse_date_time_smart(line, now)
                    reminder_id = add_reminder(
                        chat_id=target_chat_id,
                        text=text,
                        remind_at=remind_at,
                        created_by=user.id,
                    )
                    logger.info(
                        "Создан bulk reminder id=%s chat_id=%s at=%s text=%s",
                        reminder_id,
                        target_chat_id,
                        remind_at.isoformat(),
                        text,
                    )
                created += 1
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
    raw_single = raw_args.strip()

    if looks_like_recurring(raw_single):
        try:
            first_dt, text, pattern_type, payload, hour, minute = parse_recurring(raw_single, now)
        except ValueError as e:
            await message.reply_text(f"Не смог понять повторяющийся формат: {e}")
            return

        tpl_id = create_recurring_template(
            chat_id=target_chat_id,
            text=text,
            pattern_type=pattern_type,
            payload=payload,
            time_hour=hour,
            time_minute=minute,
            created_by=user.id,
        )
        reminder_id = add_reminder(
            chat_id=target_chat_id,
            text=text,
            remind_at=first_dt,
            created_by=user.id,
            template_id=tpl_id,
        )

        logger.info(
            "Создан recurring reminder id=%s tpl_id=%s chat_id=%s at=%s text=%s (from chat %s, user %s)",
            reminder_id,
            tpl_id,
            target_chat_id,
            first_dt.isoformat(),
            text,
            chat.id,
            user.id,
        )

        when_str = first_dt.strftime("%d.%m %H:%M")
        if used_alias:
            await message.reply_text(
                f"Ок, создал повторяющееся напоминание в чате '{used_alias}'. "
                f"Первое напоминание будет {when_str}: {text}"
            )
        else:
            await message.reply_text(
                f"Ок, создал повторяющееся напоминание. "
                f"Первое напоминание будет {when_str}: {text}"
            )
        return

    try:
        remind_at, text = parse_date_time_smart(raw_single, now)
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
        SELECT id, text, remind_at, template_id
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
    for idx, (rid, text, remind_at_str, template_id) in enumerate(rows, start=1):
        dt = datetime.fromisoformat(remind_at_str)
        ts = dt.strftime("%d.%m %H:%M")
        marker = " 🔁" if template_id is not None else ""
        lines.append(f"{idx}. {ts} - {text}{marker}")
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
        f"SELECT id, text, remind_at, template_id FROM reminders WHERE id IN ({qmarks}) ORDER BY remind_at ASC",
        ids,
    )
    rows = c.fetchall()
    conn.close()

    lines = []
    for new_idx, (rid2, text, remind_at_str, template_id) in enumerate(rows, start=1):
        dt = datetime.fromisoformat(remind_at_str)
        ts = dt.strftime("%d.%m %H:%M")
        marker = " 🔁" if template_id is not None else ""
        lines.append(f"{new_idx}. {ts} - {text}{marker}")

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


# ===== SNOOZE callback =====

async def snooze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    try:
        if data.startswith("snooze:"):
            _, rid_str, action = data.split(":", 2)
            rid = int(rid_str)
            r = get_reminder(rid)
            if not r:
                await query.answer("Напоминание не найдено", show_alert=True)
                return

            now = datetime.now(TZ)

            if action == "20m":
                new_dt = now + timedelta(minutes=20)
            elif action == "1h":
                new_dt = now + timedelta(hours=1)
            elif action == "3h":
                new_dt = now + timedelta(hours=3)
            elif action == "tomorrow":
                base = (now + timedelta(days=1)).astimezone(TZ).date()
                new_dt = datetime(base.year, base.month, base.day, 11, 0, tzinfo=TZ)
            elif action == "nextmon":
                base = now.astimezone(TZ).date()
                cur_wd = base.weekday()
                delta = (0 - cur_wd + 7) % 7
                if delta == 0:
                    delta = 7
                target = base + timedelta(days=delta)
                new_dt = datetime(target.year, target.month, target.day, 11, 0, tzinfo=TZ)
            elif action == "custom":
                kb = build_custom_date_keyboard(rid)
                await query.edit_message_reply_markup(reply_markup=kb)
                await query.answer("Выбери дату", show_alert=False)
                return
            else:
                await query.answer("Неизвестное действие", show_alert=True)
                return

            add_reminder(
                chat_id=r.chat_id,
                text=r.text,
                remind_at=new_dt,
                created_by=r.created_by,
                template_id=None,
            )
            when_str = new_dt.strftime("%d.%m %H:%M")
            # Пытаемся обновить текст сообщения
            try:
                await query.edit_message_text(f"{r.text}\n\n(Отложено до {when_str})")
            except Exception:
                # если не получилось - хотя бы уберем клавиатуру
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass
            await query.answer(f"Отложено до {when_str}")
            return

        if data.startswith("snooze_page:"):
            # перелистывание календаря кастом-даты
            _, rid_str, start_str = data.split(":", 2)
            rid = int(rid_str)  # на будущее, пока не используем
            start_date = date.fromisoformat(start_str)
            kb = build_custom_date_keyboard(rid, start=start_date)
            await query.edit_message_reply_markup(reply_markup=kb)
            await query.answer()
            return

        if data.startswith("snooze_pickdate:"):
            _, rid_str, date_str = data.split(":", 2)
            rid = int(rid_str)
            kb = build_custom_time_keyboard(rid, date_str)
            await query.edit_message_reply_markup(reply_markup=kb)
            await query.answer("Выбери время")
            return

        if data.startswith("snooze_picktime:"):
            _, rid_str, date_str, time_str = data.split(":", 3)
            rid = int(rid_str)
            r = get_reminder(rid)
            if not r:
                await query.answer("Напоминание не найдено", show_alert=True)
                return
            try:
                year, month, day = map(int, date_str.split("-"))
                hour, minute = map(int, time_str.split(":"))
                new_dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
            except Exception:
                await query.answer("Не смог понять дату/время", show_alert=True)
                return

            add_reminder(
                chat_id=r.chat_id,
                text=r.text,
                remind_at=new_dt,
                created_by=r.created_by,
                template_id=None,
            )
            when_str = new_dt.strftime("%d.%m %H:%M")
            try:
                await query.edit_message_text(f"{r.text}\n\n(Отложено до {when_str})")
            except Exception:
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass
            await query.answer(f"Отложено до {when_str}")
            return

        if data.startswith("snooze_cancel:"):
            await query.answer("Отменено")
            await query.edit_message_reply_markup(reply_markup=None)
            return

        if data == "noop":
            await query.answer()
            return

    except Exception:
        logger.exception("Ошибка в snooze_callback")
        try:
            await query.answer("Произошла ошибка", show_alert=True)
        except Exception:
            pass


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
                    # определяем тип чата, чтобы решать, показывать ли snooze-кнопки
                    try:
                        chat = await app.bot.get_chat(r.chat_id)
                        chat_type = chat.type
                    except Exception:
                        chat_type = None

                    if chat_type == Chat.PRIVATE:
                        # только в личке показываем snooze-кнопки
                        await app.bot.send_message(
                            chat_id=r.chat_id,
                            text=r.text,
                            reply_markup=build_snooze_keyboard(r.id),
                        )
                    else:
                        # в группах/каналах - только текст
                        await app.bot.send_message(
                            chat_id=r.chat_id,
                            text=r.text,
                        )

                    mark_reminder_sent(r.id)
                    logger.info(
                        "Отправлено напоминание id=%s в чат %s: %s (время %s, template_id=%s)",
                        r.id,
                        r.chat_id,
                        r.text,
                        r.remind_at.isoformat(),
                        r.template_id,
                    )

                    if r.template_id is not None:
                        tpl = get_recurring_template(r.template_id)
                        if tpl and tpl["active"]:
                            next_dt = compute_next_occurrence(
                                tpl["pattern_type"],
                                tpl["payload"],
                                tpl["time_hour"],
                                tpl["time_minute"],
                                r.remind_at,
                            )
                            if next_dt is not None:
                                add_reminder(
                                    chat_id=tpl["chat_id"],
                                    text=tpl["text"],
                                    remind_at=next_dt,
                                    created_by=tpl["created_by"],
                                    template_id=tpl["id"],
                                )
                                logger.info(
                                    "Запланировано следующее повторяющееся напоминание для tpl_id=%s на %s",
                                    tpl["id"],
                                    next_dt.isoformat(),
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
    application.add_handler(CallbackQueryHandler(
        snooze_callback,
        pattern=r"^(snooze:|snooze_pickdate:|snooze_picktime:|snooze_page:|snooze_cancel:|noop)"
    ))

    logger.info("Запускаем бота polling...")
    application.run_polling()


if __name__ == "__main__":
    main()