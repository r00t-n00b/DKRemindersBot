import asyncio
import logging
import os
import re
import sqlite3
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING

from zoneinfo import ZoneInfo
from textwrap import dedent

# --- Telegram imports ---
# Во время тестов telegram не установлен, поэтому:
# - в runtime импортируем нормально
# - в pytest - типы доступны, но код не падает
if TYPE_CHECKING:
    from telegram import Update, Chat, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        CallbackQueryHandler,
    )
else:
    try:
        from telegram import Update, Chat, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import (
            Application,
            CommandHandler,
            ContextTypes,
            CallbackQueryHandler,
        )
    except ImportError:
        # pytest / test environment
        Update = Chat = InlineKeyboardButton = InlineKeyboardMarkup = object
        Application = CommandHandler = ContextTypes = CallbackQueryHandler = object

# Тип для context в хендлерах (чтобы pytest не падал)
try:
    CTX = ContextTypes.DEFAULT_TYPE  # type: ignore[attr-defined]
except Exception:
    from typing import Any
    CTX = Any

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

    # привязка пользователей (кто нажал /start в личке)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_chats (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_chats_username ON user_chats(username)"
    )

    conn.commit()
    conn.close()

def upsert_user_chat(user_id: int, chat_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO user_chats(user_id, chat_id, username, first_name, last_name, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            chat_id = excluded.chat_id,
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            chat_id,
            (username or "").lower() if username else None,
            first_name,
            last_name,
            datetime.now(TZ).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_user_chat_id_by_username(username: str) -> Optional[int]:
    uname = username.strip().lstrip("@").lower()
    if not uname:
        return None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM user_chats WHERE username = ? ORDER BY updated_at DESC LIMIT 1", (uname,))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return None

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

def get_active_reminders_created_by_for_chat(chat_id: int, created_by: int) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, remind_at, delivered, created_by, template_id
            FROM reminders
            WHERE chat_id = ?
              AND delivered = 0
              AND created_by = ?
            ORDER BY remind_at ASC
            """,
            (chat_id, created_by),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

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

def get_reminder_row(rid: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, remind_at, delivered, created_by, template_id
            FROM reminders
            WHERE id = ?
            """,
            (rid,),
        )
        row = c.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def get_recurring_template_row(tpl_id: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, created_at, active
            FROM recurring_templates
            WHERE id = ?
            """,
            (tpl_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        d = dict(row)
        # payload в базе у нас JSON-строка
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except Exception:
            d["payload"] = {}
        return d
    finally:
        conn.close()


def delete_reminder_with_snapshot(rid: int, target_chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Удаляет один reminder и возвращает снепшот для undo.
    Снепшот не зависит от телеграма, чисто данные.
    """
    r = get_reminder_row(rid)
    if not r:
        return None

    if int(r["chat_id"]) != int(target_chat_id):
        # защита: не даем удалить "чужой" rid через подмену индекса/контекста
        return None

    snapshot: Dict[str, Any] = {
        "reminder": r,
        "template": None,
    }

    tpl_id = r.get("template_id")
    if tpl_id is not None:
        tpl = get_recurring_template_row(int(tpl_id))
        snapshot["template"] = tpl

    deleted = delete_reminders([rid], target_chat_id)
    if not deleted:
        return None

    return snapshot


def restore_deleted_snapshot(snapshot: Dict[str, Any]) -> Optional[int]:
    """
    Восстанавливает удаленный reminder (и recurring template, если был).
    Возвращает новый reminder_id.
    """
    r = snapshot.get("reminder") or {}
    if not r:
        return None

    tpl = snapshot.get("template")

    new_tpl_id: Optional[int] = None
    if tpl:
        # создаем новый template (id будет новый)
        new_tpl_id = create_recurring_template(
            chat_id=int(tpl["chat_id"]),
            text=str(tpl["text"]),
            pattern_type=str(tpl["pattern_type"]),
            payload=dict(tpl.get("payload") or {}),
            time_hour=int(tpl["time_hour"]),
            time_minute=int(tpl["time_minute"]),
            created_by=tpl.get("created_by"),
        )

    # восстановим сам reminder
    remind_at = datetime.fromisoformat(str(r["remind_at"]))
    new_rid = add_reminder(
        chat_id=int(r["chat_id"]),
        text=str(r["text"]),
        remind_at=remind_at,
        created_by=r.get("created_by"),
        template_id=new_tpl_id,
    )
    return new_rid


def make_undo_token() -> str:
    # короткий токен, чтобы callback_data была маленькой
    return secrets.token_urlsafe(8)


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

def get_private_chat_id_by_username(username: str) -> Optional[int]:
    if not username:
        return None

    u = username.strip()
    if u.startswith("@"):
        u = u[1:]
    if not u:
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT chat_id
            FROM user_chats
            WHERE LOWER(username) = LOWER(?)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (u,),
        )
        row = c.fetchone()
        return int(row["chat_id"]) if row else None
    finally:
        conn.close()

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

TIME_TOKEN_RE = re.compile(r"^\d{1,2}[:.]\d{2}$")


def _split_expr_and_text(s: str) -> Tuple[str, str]:
    m = re.match(r"^(?P<expr>.+?)\s*[-–—]\s*(?P<text>.+)$", s.strip())
    if not m:
        raise ValueError("Ожидаю формат 'дата/время - текст'")
    expr = m.group("expr").strip()
    text = m.group("text").strip()
    if not expr or not text:
        raise ValueError("Ожидаю непустые дату/время и текст")
    return expr, text


def _extract_time_from_tokens(
    tokens: List[str],
    default_hour: int = 11,
    default_minute: int = 0,
) -> Tuple[List[str], int, int]:
    if tokens and TIME_TOKEN_RE.fullmatch(tokens[-1]):
        raw = tokens[-1]
        sep = ":" if ":" in raw else "."
        h_s, m_s = raw.split(sep, 1)

        # Важно: если это невалидное "время" (например 29.11), не падаем,
        # а считаем, что времени нет, и оставляем токен как есть.
        try:
            hour = int(h_s)
            minute = int(m_s)
        except ValueError:
            return tokens, default_hour, default_minute

        if 0 <= hour < 24 and 0 <= minute < 60:
            core = tokens[:-1]
            return core, hour, minute

        return tokens, default_hour, default_minute

    return tokens, default_hour, default_minute


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

MONTH_EN = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

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

    # 4) Меняем HH.MM -> HH:MM только если это действительно время (hour <= 23)
    parts = s.split()
    fixed: List[str] = []
    for p in parts:
        m = re.fullmatch(r"(\d{1,2})\.(\d{2})", p)
        if m:
            hh = int(m.group(1))
            mm = int(m.group(2))
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                fixed.append(f"{hh}:{m.group(2)}")
                continue
        fixed.append(p)

    s = " ".join(fixed)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _parse_next_expression(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.lower().strip()
    tokens = s.split()
    if not tokens:
        return None

    local = now.astimezone(TZ)

    next_words = {"next", "следующий", "следующая", "следующее", "следующие"}
    this_words = {"this", "coming", "этот", "эта", "это", "эти", "ближайший", "ближайшая", "ближайшее", "ближайшие"}
    ru_prefix_v = {"в"}  # "в четверг ..."

    first = tokens[0]

    # Определяем режим:
    # - "next X" -> строго следующий (не сегодня)
    # - "this/coming/этот/ближайший X" -> ближайший (может быть сегодня)
    # - "X" где X weekday -> ближайший (может быть сегодня)
    mode: Optional[str] = None  # "next" | "this"
    start_idx = 0

    if first in next_words:
        mode = "next"
        start_idx = 1
    elif first in this_words:
        mode = "this"
        start_idx = 1
    elif first in ru_prefix_v and len(tokens) >= 2 and (tokens[1] in WEEKDAY_RU):
        # "в четверг ..."
        mode = "this"
        start_idx = 1
    else:
        # без префикса: попробуем weekday
        mode = "this"
        start_idx = 0

    if start_idx >= len(tokens):
        return None

    second = tokens[start_idx]

    # next week / следующая неделя
    if mode in {"next", "this"} and second in {"week", "неделя", "неделю"}:
        base = local.date()
        cur_wd = base.weekday()
        days_until_next_monday = (7 - cur_wd) % 7

        if mode == "next":
            if days_until_next_monday == 0:
                days_until_next_monday = 7
        else:
            # this/coming week -> если сегодня пн, то сегодня (delta 0)
            # иначе ближайший понедельник (может быть через несколько дней)
            # (то есть фактически то же, что days_until_next_monday, но 0 разрешаем)
            pass

        rest_tokens = tokens[start_idx + 1 :]
        rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens)
        target_date = base + timedelta(days=days_until_next_monday)
        return datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=TZ)

    # next month / следующий месяц
    if mode in {"next", "this"} and second in {"month", "месяц", "месяца"}:
        rest_tokens = tokens[start_idx + 1 :]
        rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens)
        year = local.year
        month = local.month + 1 if mode == "next" else local.month

        if mode == "this":
            # this month -> сегодня, но час/минуты ставим на сегодня (если время уже прошло - завтра)
            dt = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt <= now:
                dt = dt + timedelta(days=1)
            return dt

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

    # weekday (en/ru)
    target_wd: Optional[int] = None
    rest_tokens: List[str] = []

    if second in WEEKDAY_EN:
        target_wd = WEEKDAY_EN[second]
        rest_tokens = tokens[start_idx + 1 :]
    elif second in WEEKDAY_RU:
        target_wd = WEEKDAY_RU[second]
        rest_tokens = tokens[start_idx + 1 :]
    else:
        return None

    rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens)

    base_date = local.date()
    cur_wd = base_date.weekday()
    delta = (target_wd - cur_wd + 7) % 7

    candidate = datetime(base_date.year, base_date.month, base_date.day, hour, minute, tzinfo=TZ) + timedelta(days=delta)

    if mode == "next":
        # строго следующий: если попали на сегодня, уходим на +7
        if delta == 0:
            candidate = candidate + timedelta(days=7)
        return candidate

    # this/coming/без префикса: сегодня разрешаем, но только если время впереди
    if candidate <= now:
        candidate = candidate + timedelta(days=7)
    return candidate


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

def _parse_month_name_date(expr: str, now: datetime) -> Optional[datetime]:
    """
    Понимает:
    - on January 25
    - on January 25 at 20:30
    - January 25
    - January 25 at 20:30
    - on 25 January
    - on 25 January at 20:30
    """
    s = expr.lower().strip()
    local = now.astimezone(TZ)

    # Нормализация: убираем лишний "on" в начале
    if s.startswith("on "):
        s = s[3:].strip()

    tokens = s.split()
    if not tokens:
        return None

    # Вынесем время, если в конце "at HH:MM" или просто "HH:MM"
    # Примеры:
    #   january 25 at 20:30
    #   january 25 20:30
    hour = 11
    minute = 0

    def _try_parse_time_token(tok: str) -> Optional[Tuple[int, int]]:
        m_time = re.fullmatch(r"(?P<h>\d{1,2})[:.](?P<m>\d{2})", tok)
        if not m_time:
            return None
        h = int(m_time.group("h"))
        m_ = int(m_time.group("m"))
        if not (0 <= h < 24 and 0 <= m_ < 60):
            return None
        return h, m_

    if len(tokens) >= 2 and tokens[-2] == "at":
        parsed = _try_parse_time_token(tokens[-1])
        if parsed is not None:
            hour, minute = parsed
            tokens = tokens[:-2]
    else:
        parsed = _try_parse_time_token(tokens[-1]) if tokens else None
        if parsed is not None:
            hour, minute = parsed
            tokens = tokens[:-1]

    # Если осталась не дата (а, например, было только "23:59") - это не наш формат
    if len(tokens) < 2:
        return None

    # Вариант A: "<month> <day>"
    if tokens[0] in MONTH_EN and tokens[1].isdigit():
        month = int(MONTH_EN[tokens[0]])
        day = int(tokens[1])
    # Вариант B: "<day> <month>"
    elif tokens[1] in MONTH_EN and tokens[0].isdigit():
        day = int(tokens[0])
        month = int(MONTH_EN[tokens[1]])
    else:
        return None

    if not (1 <= day <= 31):
        raise ValueError("Неверный день месяца")

    year = local.year
    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
    except ValueError as e:
        raise ValueError(f"Неверная дата или время: {e}") from e

    # Если дата уже прошла (с небольшим допуском) - переносим на следующий год
    if dt < now - timedelta(minutes=1):
        try:
            dt = dt.replace(year=year + 1)
        except ValueError as e:
            raise ValueError(
                f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
            ) from e

    return dt


def _parse_absolute(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.strip()
    local = now.astimezone(TZ)

    # 25.01 [11:00] / 25/01 [11:00]
    m = re.fullmatch(
        r"(?P<day>\d{1,2})[./](?P<month>\d{1,2})(?:\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2}))?",
        s,
    )
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

    # 25 december [20:30]
    m_name_dm = re.fullmatch(
        r"(?P<day>\d{1,2})\s+(?P<month_name>[a-zA-Z]+)(?:\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2}))?$",
        s.lower().strip(),
    )
    if m_name_dm:
        day = int(m_name_dm.group("day"))
        month_name = m_name_dm.group("month_name")
        if month_name not in MONTH_EN:
            raise ValueError("Не знаю такой месяц")

        month = int(MONTH_EN[month_name])

        if m_name_dm.group("hour") is not None:
            hour = int(m_name_dm.group("hour"))
            minute = int(m_name_dm.group("minute"))
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

    # january 25 [20:30]
    m_name_md = re.fullmatch(
        r"(?P<month_name>[a-zA-Z]+)\s+(?P<day>\d{1,2})(?:\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2}))?$",
        s.lower().strip(),
    )
    if m_name_md:
        month_name = m_name_md.group("month_name")
        if month_name not in MONTH_EN:
            raise ValueError("Не знаю такой месяц")

        month = int(MONTH_EN[month_name])
        day = int(m_name_md.group("day"))

        if m_name_md.group("hour") is not None:
            hour = int(m_name_md.group("hour"))
            minute = int(m_name_md.group("minute"))
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

    # только время: 23:59 или 23.59
    m2 = re.fullmatch(r"(?P<hour>\d{1,2})[:.](?P<minute>\d{2})", s)
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
    expr_lower = _normalize_on_at_phrase(expr_lower)
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

    dt = _parse_month_name_date(expr_lower, now)
    if dt is not None:
        return dt, text

    dt = _parse_absolute(expr_lower, now)
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
        candidate = local.replace(
            hour=time_hour,
            minute=time_minute,
            second=0,
            microsecond=0,
        )
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

    if pattern_type == "yearly":
        month = int(payload["month"])
        day = int(payload["day"])

        base = after_dt.astimezone(TZ)
        year = base.year

        # Если дата в этом году уже прошла - берем следующий год.
        # Плюс поддержка 29 февраля: ищем следующий валидный год.
        for _ in range(0, 12):
            try:
                candidate = datetime(year, month, day, time_hour, time_minute, tzinfo=TZ)
            except ValueError:
                year += 1
                continue

            if candidate <= after_dt:
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

    # yearly: every year on december 25 [10:00] - text
    # tokens: every year on december 25
    if pattern_type is None:
        if len(tokens_no_time) >= 4 and first == "every" and tokens_no_time[1] == "year":
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

def format_recurring_human(pattern_type: Optional[str], payload: Optional[Dict[str, Any]]) -> str:
    """
    Делает человекочитаемое описание регулярности для списка /list.
    pattern_type: daily / weekly / weekly_multi / monthly / yearly
    payload: {"weekday": 0} / {"days":[...]} / {"day":15} / {"month":12,"day":25}
    """
    if not pattern_type:
        return "повтор"

    payload = payload or {}

    weekday_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    month_short = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    if pattern_type == "daily":
        return "daily"

    if pattern_type == "weekly":
        wd = int(payload.get("weekday", 0))
        wd = max(0, min(6, wd))
        return f"weekly ({weekday_short[wd]})"

    if pattern_type == "weekly_multi":
        days = payload.get("days") or []
        days = sorted(set(int(x) for x in days))
        if days == [0, 1, 2, 3, 4]:
            return "weekdays"
        if days == [5, 6]:
            return "weekends"
        nice = ", ".join(weekday_short[max(0, min(6, d))] for d in days) if days else "weekly"
        return f"weekly ({nice})"

    if pattern_type == "monthly":
        day = int(payload.get("day", 1))
        return f"monthly (day {day})"

    if pattern_type == "yearly":
        m = int(payload.get("month", 1))
        d = int(payload.get("day", 1))
        m = max(1, min(12, m))
        return f"yearly ({month_short[m - 1]} {d})"

    return pattern_type

def format_deleted_human(remind_at_iso: str, text: str, tpl_pattern_type: Optional[str], tpl_payload: Optional[Dict[str, Any]]) -> str:
    dt = datetime.fromisoformat(remind_at_iso)
    ts = dt.strftime("%d.%m %H:%M")

    suffix = ""
    if tpl_pattern_type:
        human = format_recurring_human(tpl_pattern_type, tpl_payload or {})
        suffix = f"  🔁 {human}" if human else "  🔁"

    return f"{ts} - {text}{suffix}"

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
        # важное для новых "человеческих" форм
        "on",
        "at",
        "в",
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
        [
            InlineKeyboardButton("✅ Mark complete", callback_data=f"done:{reminder_id}"),
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

async def start(update: Update, context: CTX) -> None:
    chat = update.effective_chat
    user = update.effective_user

    if chat is None or user is None:
        return

    if chat.type == Chat.PRIVATE:
        upsert_user_chat(
            user_id=user.id,
            chat_id=chat.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

    text = dedent("""
        Привет. Я бот для напоминаний.

        Самое базовое:
        /remind DD.MM HH:MM - текст
        Пример: /remind 28.11 12:00 - завтра футбол

        Еще примеры:
        - Только дата (11:00 по умолчанию): /remind 29.11 - текст
        - Только время: /remind 23:59 - текст
        - Относительное: /remind in 2 hours - текст
        - Повторяющееся: /remind every day 10:00 - текст

        Список и удаление:
        /list - показать активные напоминания и удалить кнопками

        Подробности и все форматы: /help
    """).strip()

    await update.message.reply_text(text)


async def help_command(update: Update, context: CTX) -> None:
    message = update.effective_message
    if message is None:
        return

    text = dedent("""
        📌 Бот для напоминаний — подробная справка

        ======================
        БАЗОВЫЙ ФОРМАТ
        ======================
        /remind ДАТА ВРЕМЯ - текст

        Пример:
        /remind 28.11 12:00 - завтра футбол


        ======================
        РАЗОВЫЕ НАПОМИНАНИЯ
        ======================

        🔹 Только дата (время по умолчанию 11:00):
        /remind 29.11 - текст

        🔹 Только время:
        /remind 23:59 - текст
        (сегодня или завтра, если время уже прошло)

        🔹 Относительное время:
        /remind in 2 hours - текст
        /remind in 45 minutes - текст
        /remind через 3 часа - текст

        🔹 Сегодня / завтра / послезавтра:
        /remind today 18:00 - текст
        /remind tomorrow - текст
        /remind завтра 19:00 - текст
        /remind послезавтра - текст

        🔹 День недели:
        /remind next Monday 10:00 - текст
        /remind next week - текст
        /remind next month - текст

        🔹 Предлог on / at (английский):
        /remind on Thursday at 20:30 - текст
        /remind on 25 December at 20:30 - текст
        /remind on 25.12 20:30 - текст

        🔹 Выходные / будни:
        /remind weekend - текст
        /remind weekday - текст
        /remind workday - текст


        ======================
        ПОВТОРЯЮЩИЕСЯ
        ======================

        🔁 Каждый день:
        /remind every day 10:00 - текст
        /remind каждый день 10:00 - текст

        🔁 Каждую неделю:
        /remind every Monday 10:00 - текст
        /remind каждую среду 19:00 - текст

        🔁 Будни / выходные:
        /remind every weekday 09:00 - текст
        /remind every weekend 11:00 - текст
        /remind каждые выходные 11:00 - текст

        🔁 Каждый месяц:
        /remind every month 15 10:00 - текст
        /remind каждый месяц 15 10:00 - текст

        🔁 Каждый год:
        /remind every year on December 25 10:00 - текст


        ======================
        СПИСКИ И УДАЛЕНИЕ
        ======================

        📋 Показать активные напоминания:
        /list

        ❌ Удаление:
        - кнопками ❌ рядом с напоминаниями
        - после удаления появляется кнопка «Вернуть ремайндер»


        ======================
        АЛИАСЫ И ЛИЧКА
        ======================

        🔗 Привязка чата:
        В чате: /linkchat football

        💬 Использование в личке:
        /remind football 28.11 12:00 - матч
        /list football

        👤 Напоминания конкретному человеку (в личке):
        /list @username
        (показывает только те, которые ты ему поставил)


        ======================
        ПРОЧЕЕ
        ======================

        ⏰ После срабатывания напоминания доступны кнопки SNOOZE:
        +20 минут, +1 час, +3 часа, завтра, следующий понедельник,
        либо кастомная дата и время.
    """).strip()

    await message.reply_text(text)

async def linkchat_command(update: Update, context: CTX) -> None:
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


async def remind_command(update: Update, context: CTX) -> None:
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

    # В личке допускаем @username первым словом / первой строкой
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip()
            if first_token.startswith("@") and len(first_token) > 1:
                target = get_user_chat_id_by_username(first_token)
                if target is None:
                    await message.reply_text(
                        f"Я пока не могу написать {first_token} в личку, потому что он/она не нажимал(а) Start у бота.\n"
                        f"Пусть откроет бота и нажмет Start, потом повтори команду."
                    )
                    return

                # убираем @username из raw_args
                rest_first_line = first_line[len(first_token):].lstrip()
                rest_lines = "\n".join(raw_args.splitlines()[1:])
                parts = []
                if rest_first_line:
                    parts.append(rest_first_line)
                if rest_lines.strip():
                    parts.append(rest_lines)
                raw_args = "\n".join(parts).strip()

                if not raw_args:
                    await message.reply_text(
                        f"После {first_token} нужно указать дату и текст.\n"
                        f"Пример: /remind {first_token} tomorrow 10:00 - привет"
                    )
                    return

                target_chat_id = target
                used_alias = first_token  # просто чтобы показать в ответе, кого выбрали

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

    # если человек пишет боту в личке - запомним его chat_id
    if is_private:
        upsert_user_chat(
            user_id=user.id,
            chat_id=chat.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

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

    # Сначала пробуем как recurring
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

        human = format_recurring_human(pattern_type, payload)
        freq_part = f"\nПовтор: {human}" if human else ""

        if used_alias:
            await message.reply_text(
                f"Ок, создал повторяющееся напоминание в чате '{used_alias}'.\n"
                f"Первое напоминание будет {when_str}: {text}"
                f"{freq_part}"
            )
        else:
            await message.reply_text(
                f"Ок, создал повторяющееся напоминание.\n"
                f"Первое напоминание будет {when_str}: {text}"
                f"{freq_part}"
            )
        return

    # Обычное разовое напоминание
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
        if target_chat_id != chat.id and chat.type == Chat.PRIVATE:
            await message.reply_text(
                f"Ок, напомню этому человеку {when_str}: {text}"
            )
        else:
            await message.reply_text(
                f"Ок, напомню {when_str}: {text}"
            )


async def list_command(update: Update, context: CTX) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    # по умолчанию - показываем напоминания для текущего чата
    target_chat_id = chat.id
    used_alias: Optional[str] = None

    # ===== НОВЫЙ РЕЖИМ: /list @username (только в личке) =====
    if chat.type == Chat.PRIVATE and context.args:
        first_arg = context.args[0].strip()

        if first_arg.startswith("@"):
            owner_chat_id = get_private_chat_id_by_username(first_arg)

            if owner_chat_id is None:
                await message.reply_text(
                    f"Пользователь {first_arg} еще не писал боту.\n"
                    f"Он должен сначала нажать Start или поставить любой ремайндер."
                )
                return

            rows = get_active_reminders_created_by_for_chat(
                chat_id=owner_chat_id,
                created_by=user.id,
            )

            if not rows:
                await message.reply_text(
                    f"Ты не ставил напоминаний пользователю {first_arg}."
                )
                return

            lines = []
            ids: List[int] = []

            for idx, r in enumerate(rows, start=1):
                dt = datetime.fromisoformat(r["remind_at"])
                ts = dt.strftime("%d.%m %H:%M")

                suffix = ""
                tpl_id = r.get("template_id")
                if tpl_id is not None:
                    tpl = get_recurring_template(int(tpl_id))
                    if tpl:
                        human = format_recurring_human(
                            tpl.get("pattern_type"),
                            tpl.get("payload"),
                        )
                        suffix = f"  🔁 {human}" if human else "  🔁"
                    else:
                        suffix = "  🔁"

                lines.append(f"{idx}. {ts} - {r['text']}{suffix}")
                ids.append(r["id"])

            context.user_data["list_ids"] = ids
            context.user_data["list_chat_id"] = owner_chat_id

            reply = (
                f"Напоминания, которые ты поставил пользователю {first_arg}:\n\n"
                + "\n".join(lines)
            )

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

            await message.reply_text(reply, reply_markup=InlineKeyboardMarkup(buttons))
            return

    # ===== СТАРАЯ ЛОГИКА: /list alias =====
    if chat.type == Chat.PRIVATE and context.args:
        alias = context.args[0].strip()
        if alias:
            alias_chat_id = get_chat_id_by_alias(alias)
            if alias_chat_id is None:
                aliases = get_all_aliases()
                if not aliases:
                    await message.reply_text(
                        f"Alias '{alias}' не найден.\n"
                        f"Сначала зайди в нужный чат и выполни /linkchat название.\n"
                    )
                else:
                    known = ", ".join(a for a, _, _ in aliases)
                    await message.reply_text(
                        f"Alias '{alias}' не найден.\n"
                        f"Из известных: {known}"
                    )
                return
            target_chat_id = alias_chat_id
            used_alias = alias

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT
            r.id,
            r.text,
            r.remind_at,
            r.template_id,
            rt.pattern_type,
            rt.payload
        FROM reminders r
        LEFT JOIN recurring_templates rt ON rt.id = r.template_id
        WHERE r.chat_id = ? AND r.delivered = 0
        ORDER BY r.remind_at ASC
        """,
        (target_chat_id,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        if used_alias:
            await message.reply_text(f"В чате '{used_alias}' напоминаний нет.")
        else:
            await message.reply_text("Напоминаний нет.")
        return

    lines = []
    ids: List[int] = []
    for idx, (rid, text, remind_at_str, template_id, tpl_pattern_type, tpl_payload_json) in enumerate(rows, start=1):
        dt = datetime.fromisoformat(remind_at_str)
        ts = dt.strftime("%d.%m %H:%M")

        suffix = ""
        if template_id is not None:
            tpl_payload: Dict[str, Any] = {}
            if tpl_payload_json:
                try:
                    tpl_payload = json.loads(tpl_payload_json)
                except Exception:
                    tpl_payload = {}
            human = format_recurring_human(tpl_pattern_type, tpl_payload)
            suffix = f"  🔁 {human}"

        lines.append(f"{idx}. {ts} - {text}{suffix}")
        ids.append(rid)

    context.user_data["list_ids"] = ids
    context.user_data["list_chat_id"] = target_chat_id

    if used_alias:
        reply = f"Активные напоминания для чата '{used_alias}':\n\n" + "\n".join(lines)
    else:
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

async def delete_callback(update: Update, context: CTX) -> None:
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

    # Чат, для которого показывается список (может быть НЕ равен query.message.chat.id в личке)
    target_chat_id = context.user_data.get("list_chat_id")
    if target_chat_id is None:
        # на всякий случай - старое поведение
        chat = query.message.chat if query.message else None
        if chat is None:
            return
        target_chat_id = chat.id

    snapshot = delete_reminder_with_snapshot(rid, target_chat_id)
    if not snapshot:
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
        f"""
        SELECT
            r.id,
            r.text,
            r.remind_at,
            r.template_id,
            rt.pattern_type,
            rt.payload
        FROM reminders r
        LEFT JOIN recurring_templates rt ON rt.id = r.template_id
        WHERE r.id IN ({qmarks})
        ORDER BY r.remind_at ASC
        """,
        ids,
    )
    rows = c.fetchall()
    conn.close()

    lines = []
    for new_idx, (rid2, text, remind_at_str, template_id, tpl_pattern_type, tpl_payload_json) in enumerate(rows, start=1):
        dt = datetime.fromisoformat(remind_at_str)
        ts = dt.strftime("%d.%m %H:%M")

        suffix = ""
        if template_id is not None:
            tpl_payload: Dict[str, Any] = {}
            if tpl_payload_json:
                try:
                    tpl_payload = json.loads(tpl_payload_json)
                except Exception:
                    tpl_payload = {}

            human = format_recurring_human(tpl_pattern_type, tpl_payload)
            suffix = f"  🔁 {human}" if human else "  🔁"

        lines.append(f"{new_idx}. {ts} - {text}{suffix}")

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

    # Сообщение "удалено" + Undo
    tpl = snapshot.get("template") or {}
    tpl_pattern_type = tpl.get("pattern_type")
    tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}

    deleted_text = format_deleted_human(
        snapshot["reminder"]["remind_at"],
        snapshot["reminder"]["text"],
        tpl_pattern_type,
        tpl_payload,
    )

    token = make_undo_token()
    context.user_data["undo_tokens"] = context.user_data.get("undo_tokens") or {}
    context.user_data["undo_tokens"][token] = snapshot

    undo_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("↩️ Вернуть ремайндер", callback_data=f"undo:{token}")]]
    )

    if query.message:
        await query.message.reply_text(f"Удалил: {deleted_text}", reply_markup=undo_kb)

async def undo_callback(update: Update, context: CTX) -> None:
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    logger.info("UNDO pressed: data=%s", data)

    if not data.startswith("undo:"):
        await query.answer()
        return

    await query.answer("Ок, восстанавливаю...")

    token = data.split(":", 1)[1].strip()
    store = context.user_data.get("undo_tokens") or {}
    snapshot = store.get(token)
    if not snapshot:
        await query.answer("Undo уже недоступен", show_alert=True)
        return

    # одноразовый undo
    del store[token]
    context.user_data["undo_tokens"] = store

    new_rid = restore_deleted_snapshot(snapshot)
    if not new_rid:
        await query.answer("Не смог восстановить", show_alert=True)
        return

    tpl = snapshot.get("template") or {}
    tpl_pattern_type = tpl.get("pattern_type")
    tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}

    restored_text = format_deleted_human(
        snapshot["reminder"]["remind_at"],
        snapshot["reminder"]["text"],
        tpl_pattern_type,
        tpl_payload,
    )

    if query.message:
        await query.message.reply_text(f"Вернул: {restored_text}")


# ===== SNOOZE callback =====

async def snooze_callback(update: Update, context: CTX) -> None:
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    try:
        # mark complete
        if data.startswith("done:"):
            _, rid_str = data.split(":", 1)
            try:
                rid = int(rid_str)
            except ValueError:
                # даже если вдруг id не распарсился, просто пометим сообщение завершенным
                rid = None

            # исходный текст сообщения
            original_text = query.message.text if query.message and query.message.text else ""

            # если есть оригинальный текст ремайндерa в БД - можно взять его
            if rid is not None:
                r = get_reminder(rid)
            else:
                r = None

            base_text = r.text if r else original_text or "Напоминание"

            new_text = f"{base_text} (завершено ✅)"

            try:
                await query.edit_message_text(new_text)
            except Exception:
                # fallback: хотя бы уберем клавиатуру
                await query.edit_message_reply_markup(reply_markup=None)

            await query.answer("Отмечено как завершенное")
            return

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
    application.add_handler(CallbackQueryHandler(undo_callback, pattern=r"^undo:"))

    application.add_handler(
        CallbackQueryHandler(
            snooze_callback,
            pattern=r"^(snooze:|snooze_pickdate:|snooze_picktime:|snooze_cancel:|noop|done:)"
        )
    )

    logger.info("Запускаем бота polling...")
    application.run_polling()


if __name__ == "__main__":
    main()