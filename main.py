import asyncio
import logging
import os
import re
import sqlite3
import json
import secrets
import calendar
import inspect
import tempfile
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING
from types import SimpleNamespace
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
        MessageHandler,
        filters,
    )
else:
    try:
        from telegram import Update, Chat, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import (
            Application,
            CommandHandler,
            ContextTypes,
            CallbackQueryHandler,
            MessageHandler,
            filters,
        )
    except ImportError:
        # pytest / test environment
        Update = Chat = InlineKeyboardButton = InlineKeyboardMarkup = object
        Application = CommandHandler = ContextTypes = CallbackQueryHandler = MessageHandler = object

        class _DummyFilter:
            def __and__(self, other):
                return self

            def __invert__(self):
                return self

        class _DummyFilters:
            VOICE = _DummyFilter()
            TEXT = _DummyFilter()
            COMMAND = _DummyFilter()

        filters = _DummyFilters()

# Тип для context в хендлерах (чтобы pytest не падал)
try:
    CTX = ContextTypes.DEFAULT_TYPE  # type: ignore[attr-defined]
except Exception:
    from typing import Any
    CTX = Any

# ===== Настройки =====

TZ = ZoneInfo("Europe/Madrid")
DB_PATH = os.environ.get("DB_PATH", "/data/reminders.db")

LOG_PATH = os.environ.get("BOT_LOG_PATH", "/data/bot.log")

_log_handlers = [logging.StreamHandler()]

try:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    _log_handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))
except Exception:
    # В локальной/test-среде /data может не существовать или быть недоступен.
    # stdout/stderr handler все равно останется.
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=_log_handlers,
)

# Не печатаем Telegram API URLs с bot token-ом в логи.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def get_now() -> datetime:
    return datetime.now(TZ)

# ===== Модель данных =====

@dataclass
class Reminder:
    id: int
    chat_id: int
    text: str
    remind_at: datetime
    created_by: Optional[int]
    template_id: Optional[int] = None
    sent_at: Optional[datetime] = None


# ===== Работа с БД =====

def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        conn.commit()

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

    # миграция старых БД - добавляем отсутствующие колонки
    c.execute("PRAGMA table_info(reminders)")
    cols = [row[1] for row in c.fetchall()]

    if "template_id" not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN template_id INTEGER")
        logger.info("DB migration: added reminders.template_id column")

    if "acked" not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN acked INTEGER NOT NULL DEFAULT 0")
        logger.info("DB migration: added reminders.acked column")

    if "sent_at" not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN sent_at TEXT")
        logger.info("DB migration: added reminders.sent_at column")

    if "nudge_count" not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN nudge_count INTEGER NOT NULL DEFAULT 0")
        logger.info("DB migration: added reminders.nudge_count column")

    # индексы под worker-ы (идемпотентно)
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(delivered, remind_at)"
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_nudge ON reminders(delivered, acked, nudge_count, sent_at)"
    )

    # Telegram messages that represent the same reminder.
    # One reminder can have several messages: original delivery, nudges, etc.
    # This lets done/snooze clear stale buttons from all visible copies.
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS reminder_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(reminder_id, chat_id, message_id)
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminder_messages_reminder_id ON reminder_messages(reminder_id)"
    )

    # алиасы чатов
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_aliases (
            alias TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            title TEXT,
            created_by INTEGER NOT NULL,
            PRIMARY KEY (created_by, alias)
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

    # алиасы для пользователей
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_aliases (
            alias TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            username TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (created_by, alias)
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

def register_reminder_message(
    reminder_id: int,
    chat_id: int,
    message_id: int,
    kind: str,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT OR IGNORE INTO reminder_messages
            (reminder_id, chat_id, message_id, kind, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(reminder_id),
            int(chat_id),
            int(message_id),
            kind,
            get_now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_reminder_messages(reminder_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """
        SELECT reminder_id, chat_id, message_id, kind, created_at
        FROM reminder_messages
        WHERE reminder_id = ?
        ORDER BY id ASC
        """,
        (int(reminder_id),),
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

async def clear_reminder_message_keyboards(bot, reminder_id: int) -> None:
    rows = get_reminder_messages(reminder_id)

    for row in rows:
        try:
            await bot.edit_message_reply_markup(
                chat_id=int(row["chat_id"]),
                message_id=int(row["message_id"]),
                reply_markup=None,
            )
        except Exception:
            logger.exception(
                "Failed to clear reminder message keyboard reminder_id=%s chat_id=%s message_id=%s",
                reminder_id,
                row.get("chat_id"),
                row.get("message_id"),
            )

def migrate_alias_tables_to_owner_scope() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    def table_info(table_name: str):
        c.execute(f"PRAGMA table_info({table_name})")
        return c.fetchall()

    def primary_key_columns(table_name: str) -> List[str]:
        rows = table_info(table_name)
        pk_rows = [row for row in rows if int(row[5]) > 0]
        pk_rows.sort(key=lambda row: int(row[5]))
        return [str(row[1]) for row in pk_rows]

    # user_aliases: старую таблицу можно безопасно мигрировать, потому created_by уже есть.
    user_cols = [str(row[1]) for row in table_info("user_aliases")]
    user_pk = primary_key_columns("user_aliases")

    if user_cols and user_pk != ["created_by", "alias"]:
        c.execute("ALTER TABLE user_aliases RENAME TO user_aliases_old_owner_scope")
        c.execute(
            """
            CREATE TABLE user_aliases (
                alias TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                username TEXT,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (created_by, alias)
            )
            """
        )
        c.execute(
            """
            INSERT OR IGNORE INTO user_aliases(alias, user_id, chat_id, username, created_by, created_at)
            SELECT alias, user_id, chat_id, username, created_by, created_at
            FROM user_aliases_old_owner_scope
            WHERE created_by IS NOT NULL
            """
        )
        c.execute("DROP TABLE user_aliases_old_owner_scope")

    # chat_aliases: старую таблицу безопасно восстановить нельзя, потому owner там не хранился.
    # Поэтому старые global chat-aliases намеренно не мигрируем. Их надо пересоздать через /linkchat.
    chat_cols = [str(row[1]) for row in table_info("chat_aliases")]
    chat_pk = primary_key_columns("chat_aliases")

    if chat_cols and chat_pk != ["created_by", "alias"]:
        c.execute("ALTER TABLE chat_aliases RENAME TO chat_aliases_old_owner_scope")
        c.execute(
            """
            CREATE TABLE chat_aliases (
                alias TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                title TEXT,
                created_by INTEGER NOT NULL,
                PRIMARY KEY (created_by, alias)
            )
            """
        )

        if "created_by" in chat_cols:
            c.execute(
                """
                INSERT OR IGNORE INTO chat_aliases(alias, chat_id, title, created_by)
                SELECT alias, chat_id, title, created_by
                FROM chat_aliases_old_owner_scope
                WHERE created_by IS NOT NULL
                """
            )

        c.execute("DROP TABLE chat_aliases_old_owner_scope")

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

def get_user_chat_id_by_user_id(user_id: int) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT chat_id FROM user_chats WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
        (user_id,),
    )
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
        SELECT id, chat_id, text, remind_at, created_by, template_id, sent_at
        FROM reminders
        WHERE id = ?
        """,
        (reminder_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None

    rid, chat_id, text, remind_at_str, created_by, template_id, sent_at_str = row
    sent_at = datetime.fromisoformat(sent_at_str) if sent_at_str else None

    return Reminder(
        id=rid,
        chat_id=chat_id,
        text=text,
        remind_at=datetime.fromisoformat(remind_at_str),
        created_by=created_by,
        template_id=template_id,
        sent_at=sent_at,
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

def get_active_reminders_for_chat(chat_id: int) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, remind_at, created_by, created_at, delivered, template_id
            FROM reminders
            WHERE chat_id = ? AND delivered = 0
            ORDER BY remind_at ASC
            """,
            (chat_id,),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

from datetime import datetime
from typing import Optional

def mark_reminder_sent(reminder_id: int, sent_at: Optional[datetime] = None) -> None:
    if sent_at is None:
        sent_at = get_now()

    # на всякий случай, если кто-то передал строку
    if isinstance(sent_at, str):
        sent_at = datetime.fromisoformat(sent_at)

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            UPDATE reminders
            SET delivered = 1,
                sent_at = ?,
                acked = 0
            WHERE id = ?
            """,
            (sent_at.isoformat(), reminder_id),
        )
        conn.commit()
    finally:
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


def delete_recurring_one_instance_and_reschedule(rid: int, chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Удаляет ОДИН инстанс recurring-ремайндера и сразу создает следующий инстанс,
    не выключая серию.

    Возвращает snapshot для undo.
    Backward-compatible поля:
      - mode="one" (старые тесты)
      - kind="single" (новый общий undo)
    """
    r = get_reminder_row(rid)
    if not r:
        return None
    if int(r["chat_id"]) != int(chat_id):
        return None

    tpl_id = r.get("template_id")
    if tpl_id is None:
        return None

    tpl = get_recurring_template_row(int(tpl_id))
    if not tpl:
        return None
    if not tpl.get("active"):
        return None

    # 1) удаляем только этот инстанс (НЕ трогаем recurring_templates)
    deleted = delete_single_reminder_row(int(rid), int(chat_id))
    if not deleted:
        return None

    snapshot: Dict[str, Any] = {
        "mode": "one",          # важно для старых тестов
        "kind": "single",       # важно для текущего undo
        "reminder": r,
        "template": tpl,
        "next_created_id": None,
    }

    # 2) создаем следующий инстанс
    try:
        last_dt = datetime.fromisoformat(str(r["remind_at"]))
    except Exception:
        return snapshot

    pattern_type = str(tpl["pattern_type"])
    payload = tpl.get("payload") or {}
    time_hour = int(tpl["time_hour"])
    time_minute = int(tpl["time_minute"])

    next_dt = compute_next_occurrence(
        pattern_type,
        dict(payload),
        time_hour,
        time_minute,
        last_dt,
    )

    if next_dt is not None:
        next_id = add_reminder(
            chat_id=int(r["chat_id"]),
            text=str(r["text"]),
            remind_at=next_dt,
            created_by=r.get("created_by"),
            template_id=int(tpl["id"]),
        )
        snapshot["next_created_id"] = int(next_id)

    return snapshot

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

def delete_single_reminder_row(reminder_id: int, chat_id: int) -> int:
    """
    Удаляет ОДИН reminder, не трогая recurring_templates.
    Возвращает количество удаленных строк (0 или 1).
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "DELETE FROM reminders WHERE id = ? AND chat_id = ?",
        (reminder_id, chat_id),
    )
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted


def deactivate_recurring_template(template_id: int) -> int:
    """
    Ставит active=0 у recurring_templates. Возвращает количество обновленных строк (0 или 1).
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE recurring_templates SET active = 0 WHERE id = ?",
        (template_id,),
    )
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated


def activate_recurring_template(template_id: int) -> int:
    """
    Ставит active=1 у recurring_templates. Возвращает количество обновленных строк (0 или 1).
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE recurring_templates SET active = 1 WHERE id = ?",
        (template_id,),
    )
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated


def get_reminders_by_template_id(template_id: int, chat_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает reminders этой серии (для snapshot при удалении серии).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, remind_at, created_by, created_at, delivered, template_id
            FROM reminders
            WHERE chat_id = ? AND template_id = ?
            ORDER BY remind_at ASC
            """,
            (chat_id, template_id),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_recurring_series(template_id: int, chat_id: int) -> int:
    """
    Удаляет все reminders серии (template_id) и деактивирует recurring_templates.active=0.
    Возвращает количество удаленных reminders.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "DELETE FROM reminders WHERE chat_id = ? AND template_id = ?",
        (chat_id, template_id),
    )
    deleted = c.rowcount

    c.execute(
        "UPDATE recurring_templates SET active = 0 WHERE id = ?",
        (template_id,),
    )

    conn.commit()
    conn.close()
    return deleted


def delete_reminder_with_snapshot(rid: int, target_chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Backward-compatible: удаляет один reminder и возвращает snapshot.
    ВАЖНО: теперь это "single delete" и НЕ останавливает серию.
    """
    return delete_single_reminder_with_snapshot(rid, target_chat_id)


def delete_single_reminder_with_snapshot(rid: int, target_chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Удаляет один reminder и возвращает snapshot для undo.
    Если reminder был recurring (template_id != None), шаблон НЕ деактивируем.
    """
    r = get_reminder_row(rid)
    if not r:
        return None

    if int(r["chat_id"]) != int(target_chat_id):
        return None

    tpl = None
    tpl_id = r.get("template_id")
    if tpl_id is not None:
        tpl = get_recurring_template_row(int(tpl_id))

    deleted = delete_single_reminder_row(rid, target_chat_id)
    if not deleted:
        return None

    return {
        "kind": "single",
        "reminder": r,
        "template": tpl,
    }


def delete_recurring_series_with_snapshot(template_id: int, target_chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Удаляет всю серию и возвращает snapshot для undo:
    - template (как есть, с этим же id)
    - список reminders, которые были удалены
    """
    tpl = get_recurring_template_row(int(template_id))
    if not tpl:
        return None

    if int(tpl["chat_id"]) != int(target_chat_id):
        return None

    reminders = get_reminders_by_template_id(int(template_id), int(target_chat_id))
    if not reminders:
        # если по какой-то причине инстансов нет, все равно деактивируем шаблон
        deactivate_recurring_template(int(template_id))
        return {
            "kind": "series",
            "template": tpl,
            "reminders": [],
        }

    deleted = delete_recurring_series(int(template_id), int(target_chat_id))
    if deleted <= 0:
        return None

    return {
        "kind": "series",
        "template": tpl,
        "reminders": reminders,
    }


def restore_deleted_snapshot(snapshot: Dict[str, Any]) -> Optional[Any]:
    """
    Восстанавливает удаленный reminder или серию.
    Возвращает:
    - для single: новый reminder_id (int)
    - для series: список новых reminder_id (List[int])
    """
    kind = snapshot.get("kind") or "single"

    if kind == "single":
        r = snapshot.get("reminder") or {}
        if not r:
            return None

        next_id = snapshot.get("next_created_id")
        if next_id:
            delete_single_reminder_row(int(next_id), int(r["chat_id"]))

        tpl = snapshot.get("template")
        tpl_id = None
        if tpl and tpl.get("id") is not None:
            # Шаблон должен был остаться активным, но на всякий случай включим обратно.
            activate_recurring_template(int(tpl["id"]))
            tpl_id = int(tpl["id"])

        remind_at = datetime.fromisoformat(str(r["remind_at"]))
        new_rid = add_reminder(
            chat_id=int(r["chat_id"]),
            text=str(r["text"]),
            remind_at=remind_at,
            created_by=r.get("created_by"),
            template_id=tpl_id,
        )
        return new_rid

    if kind == "series":
        tpl = snapshot.get("template") or {}
        tpl_id = tpl.get("id")
        if tpl_id is None:
            return None

        activate_recurring_template(int(tpl_id))

        new_ids: List[int] = []
        for r in (snapshot.get("reminders") or []):
            remind_at = datetime.fromisoformat(str(r["remind_at"]))
            new_id = add_reminder(
                chat_id=int(r["chat_id"]),
                text=str(r["text"]),
                remind_at=remind_at,
                created_by=r.get("created_by"),
                template_id=int(tpl_id),
            )
            new_ids.append(int(new_id))

        return new_ids

    return None


def make_undo_token() -> str:
    # короткий токен, чтобы callback_data была маленькой
    return secrets.token_urlsafe(8)


def mark_reminder_acked(reminder_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET acked = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def mark_nudge_sent(reminder_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET nudge_sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def get_unacked_sent_before(dt: datetime) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, sent_at
        FROM reminders
        WHERE delivered = 1
          AND acked = 0
          AND nudge_sent = 0
          AND sent_at IS NOT NULL
          AND sent_at <= ?
        ORDER BY sent_at ASC
        """,
        (dt.isoformat(),),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _find_existing_alias_casefold(
    c: sqlite3.Cursor,
    table: str,
    alias: str,
    created_by: int,
) -> Optional[str]:
    target = alias.casefold()

    c.execute(
        f"""
        SELECT alias
        FROM {table}
        WHERE created_by = ?
        """,
        (created_by,),
    )

    for row in c.fetchall():
        existing_alias = str(row[0])
        if existing_alias.casefold() == target:
            return existing_alias

    return None


def set_chat_alias(alias: str, chat_id: int, title: Optional[str], created_by: int = 0) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    existing_alias = _find_existing_alias_casefold(c, "chat_aliases", alias, created_by)

    if existing_alias is not None:
        c.execute(
            """
            UPDATE chat_aliases
            SET chat_id = ?, title = ?
            WHERE alias = ? AND created_by = ?
            """,
            (chat_id, title, existing_alias, created_by),
        )
    else:
        c.execute(
            """
            INSERT INTO chat_aliases(alias, chat_id, title, created_by)
            VALUES (?, ?, ?, ?)
            """,
            (alias, chat_id, title, created_by),
        )

    conn.commit()
    conn.close()


def get_chat_id_by_alias(alias: str, created_by: int = 0) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    existing_alias = _find_existing_alias_casefold(c, "chat_aliases", alias, created_by)
    if existing_alias is None:
        conn.close()
        return None

    c.execute(
        """
        SELECT chat_id
        FROM chat_aliases
        WHERE alias = ? AND created_by = ?
        """,
        (existing_alias, created_by),
    )
    row = c.fetchone()
    conn.close()

    if row:
        return int(row[0])
    return None


def get_all_aliases(created_by: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT alias, chat_id, title
        FROM chat_aliases
        WHERE created_by = ?
        ORDER BY alias COLLATE NOCASE
        """,
        (created_by,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_alias(alias: str, created_by: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    existing_alias = _find_existing_alias_casefold(c, "user_aliases", alias, created_by)
    if existing_alias is None:
        conn.close()
        return None

    c.execute(
        """
        SELECT alias, user_id, chat_id, username, created_by, created_at
        FROM user_aliases
        WHERE alias = ? AND created_by = ?
        """,
        (existing_alias, created_by),
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    return dict(row)


def set_user_alias(
    alias: str,
    user_id: int,
    chat_id: int,
    username: Optional[str],
    created_by: int,
) -> None:
    now_iso = datetime.now(TZ).isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    existing_alias = _find_existing_alias_casefold(c, "user_aliases", alias, created_by)

    if existing_alias is not None:
        c.execute(
            """
            UPDATE user_aliases
            SET user_id = ?, chat_id = ?, username = ?, created_at = ?
            WHERE alias = ? AND created_by = ?
            """,
            (user_id, chat_id, username, now_iso, existing_alias, created_by),
        )
    else:
        c.execute(
            """
            INSERT INTO user_aliases(alias, user_id, chat_id, username, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (alias, user_id, chat_id, username, created_by, now_iso),
        )

    conn.commit()
    conn.close()

def get_user_alias_chat_id(alias: str, created_by: int = 0) -> Optional[int]:
    row = get_user_alias(alias, created_by)
    if not row:
        return None
    return int(row["chat_id"])


def get_all_user_aliases(created_by: int) -> List[Tuple[str, int]]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT alias, chat_id
        FROM user_aliases
        WHERE created_by = ?
        ORDER BY alias COLLATE NOCASE
        """,
        (created_by,),
    )
    rows = c.fetchall()
    conn.close()
    return [(str(alias), int(chat_id)) for alias, chat_id in rows]


def delete_chat_alias(alias: str, created_by: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    existing_alias = _find_existing_alias_casefold(c, "chat_aliases", alias, created_by)
    if existing_alias is None:
        conn.close()
        return False

    c.execute(
        "DELETE FROM chat_aliases WHERE alias = ? AND created_by = ?",
        (existing_alias, created_by),
    )
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def delete_user_alias(alias: str, created_by: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    existing_alias = _find_existing_alias_casefold(c, "user_aliases", alias, created_by)
    if existing_alias is None:
        conn.close()
        return False

    c.execute(
        "DELETE FROM user_aliases WHERE alias = ? AND created_by = ?",
        (existing_alias, created_by),
    )
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def rename_chat_alias(old_alias: str, new_alias: str, created_by: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    existing_old_alias = _find_existing_alias_casefold(c, "chat_aliases", old_alias, created_by)
    if existing_old_alias is None:
        conn.close()
        return False

    if old_alias.casefold() != new_alias.casefold():
        if _find_existing_alias_casefold(c, "chat_aliases", new_alias, created_by) is not None:
            conn.close()
            raise ValueError(f"Chat-alias '{new_alias}' уже существует")

    c.execute(
        """
        UPDATE chat_aliases
        SET alias = ?
        WHERE alias = ? AND created_by = ?
        """,
        (new_alias, existing_old_alias, created_by),
    )
    conn.commit()
    conn.close()
    return True


def rename_user_alias(old_alias: str, new_alias: str, created_by: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    existing_old_alias = _find_existing_alias_casefold(c, "user_aliases", old_alias, created_by)
    if existing_old_alias is None:
        conn.close()
        return False

    if old_alias.casefold() != new_alias.casefold():
        if _find_existing_alias_casefold(c, "user_aliases", new_alias, created_by) is not None:
            conn.close()
            raise ValueError(f"User-alias '{new_alias}' уже существует")

    c.execute(
        """
        UPDATE user_aliases
        SET alias = ?
        WHERE alias = ? AND created_by = ?
        """,
        (new_alias, existing_old_alias, created_by),
    )
    conn.commit()
    conn.close()
    return True

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


import re
from typing import Tuple


def _split_expr_and_text(s: str) -> Tuple[str, str]:
    raw = (s or "").strip()

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

VAGUE_TIME_WORDS = {
    "утром": (10, 0),
    "morning": (10, 0),
    "вечером": (18, 0),
    "evening": (18, 0),
}


def _extract_time_from_tokens(
    tokens: List[str],
    default_hour: int = 11,
    default_minute: int = 0,
) -> Tuple[List[str], int, int]:
    if tokens:
        last_token = tokens[-1].strip(" ,.!?:;").lower()
        if last_token in VAGUE_TIME_WORDS:
            hour, minute = VAGUE_TIME_WORDS[last_token]
            return tokens[:-1], hour, minute

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

def _add_months(dt: datetime, months: int) -> datetime:
    # months может быть > 12, < 0 - все ок
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    d = min(dt.day, last_day)
    return dt.replace(year=y, month=m, day=d)

def _parse_in_expression(tokens: List[str], now: datetime) -> Optional[datetime]:
    if not tokens:
        return None
    first = tokens[0]
    if first not in {"in", "через"}:
        return None
    if len(tokens) < 2:
        return None

    if len(tokens) >= 3:
        try:
            amount = int(tokens[1])
        except ValueError:
            return None
        unit = tokens[2]
    elif first == "через":
        amount = 1
        unit = tokens[1]
    else:
        return None

    # английские варианты
    en_minutes = {"minute", "minutes", "min", "mins", "m"}
    en_hours = {"hour", "hours", "h", "hr", "hrs"}
    en_days = {"day", "days", "d"}
    en_weeks = {"week", "weeks", "w"}
    en_months = {"month", "months", "mon"}  # mon опционально
    en_years = {"year", "years", "yr", "yrs", "y"}

    # русские варианты
    ru_minutes = {"минуту", "минуты", "минут", "мин", "м"}
    ru_hours = {"час", "часа", "часов", "ч"}
    ru_days = {"день", "дня", "дней"}
    ru_weeks = {"неделю", "недели", "недель", "нед"}
    ru_months = {"месяц", "месяца", "месяцев", "мес"}
    ru_years = {"год", "года", "лет", "г"}

    # 1) фиксированные единицы
    delta: Optional[timedelta] = None
    if unit in en_minutes or unit in ru_minutes:
        delta = timedelta(minutes=amount)
    elif unit in en_hours or unit in ru_hours:
        delta = timedelta(hours=amount)
    elif unit in en_days or unit in ru_days:
        delta = timedelta(days=amount)
    elif unit in en_weeks or unit in ru_weeks:
        delta = timedelta(weeks=amount)

    if delta is not None:
        dt = now + delta
        return dt.replace(second=0, microsecond=0)

    # 2) months/years (календарная арифметика)
    if unit in en_months or unit in ru_months:
        dt = _add_months(now, amount)
        return dt.replace(second=0, microsecond=0)

    if unit in en_years or unit in ru_years:
        dt = _add_months(now, amount * 12)
        return dt.replace(second=0, microsecond=0)

    return None


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

def _parse_standalone_vague_time(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.lower().strip()
    if s not in VAGUE_TIME_WORDS:
        return None

    hour, minute = VAGUE_TIME_WORDS[s]
    now_local = now.astimezone(TZ)
    target_date = now_local.date()

    if (now_local.hour, now_local.minute) >= (hour, minute):
        target_date += timedelta(days=1)

    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=TZ,
    )

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

def _parse_next_expression(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.lower().strip()
    tokens = s.split()
    if not tokens:
        return None

    local = now.astimezone(TZ)

    next_words = {
        "next",
        "следующий",
        "следующая",
        "следующее",
        "следующие",
        "следующую",
        "следующей",
        "следующем",
        "следующими",
    }
    this_words = {
        "this",
        "coming",
        "этот",
        "эта",
        "это",
        "эти",
        "эту",
        "этой",
        "этом",
        "ближайший",
        "ближайшая",
        "ближайшее",
        "ближайшие",
        "ближайшую",
        "ближайшей",
        "ближайшем",
    }

    # Русские предлоги не должны менять смысл:
    # "в следующую среду" == "следующую среду"
    # "на следующей неделе" == "следующей неделе"
    # "в четверг" == "четверг"
    if len(tokens) >= 2 and tokens[0] in {"в", "во", "на"}:
        tokens = tokens[1:]

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
    else:
        # без префикса: попробуем weekday
        mode = "this"
        start_idx = 0

    if start_idx >= len(tokens):
        return None

    second = tokens[start_idx]

    # next week / следующая неделя
    if mode in {"next", "this"} and second in {"week", "неделя", "неделю", "неделе", "недели"}:
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
    if (month, day) < (local.month, local.day):
        dt = dt.replace(year=year + 1)
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

    # DD.MM.YYYY HH:MM / DD.MM.YY HH:MM
    m = re.fullmatch(
        r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2})",
        s,
    )
    if m:
        day = int(m.group("day"))
        month = int(m.group("month"))
        year = int(m.group("year"))
        hour = int(m.group("hour"))
        minute = int(m.group("minute"))

        if year < 100:
            year += 2000

        try:
            return datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата или время: {e}") from e
    
    # DD.MM / DD.MM.YYYY без времени.
    # Важно: "23.10 - текст" = 23 октября, НЕ 23:10.
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", s)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year_raw = m.group(3)

        year = local.year
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000

        try:
            dt = datetime(year, month, day, 11, 0, tzinfo=TZ)
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

    # только время: 23:59 или 23.59
    # Важно: проверяем ПОСЛЕ DD.MM, чтобы "23.10" стало датой,
    # а "23.59" дошло сюда, потому что месяца 59 не существует.
    m2 = re.fullmatch(r"(?P<hour>\d{1,2})[:.](?P<minute>\d{2})", s)
    if m2:
        hour = int(m2.group("hour"))
        minute = int(m2.group("minute"))

        # защита: "29.11" - это дата, а не время
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            dt = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt < now - timedelta(minutes=1):
                dt = dt + timedelta(days=1)
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

    raise ValueError("Не понял дату/время. Ожидаю формат 'дата время - текст'. Обрати внимание, что нужен - перед текстом")


# ===== Парсинг recurring-форматов =====

def _add_months_clamped(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])

    return dt.replace(year=year, month=month, day=day)

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
            last_day = calendar.monthrange(year, month)[1]
            candidate_day = min(day, last_day)
            candidate = datetime(year, month, candidate_day, time_hour, time_minute, tzinfo=TZ)

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

    if pattern_type == "interval":
        value = int(payload.get("value", 0))
        unit = str(payload.get("unit", "")).lower()

        if value <= 0:
            return None

        base = after_dt.astimezone(TZ).replace(second=0, microsecond=0)

        if unit == "minutes":
            return base + timedelta(minutes=value)

        if unit == "hours":
            return base + timedelta(hours=value)

        if unit == "days":
            candidate = base + timedelta(days=value)
            return candidate.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)

        if unit == "weeks":
            candidate = base + timedelta(weeks=value)
            return candidate.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)

        if unit == "months":
            candidate = _add_months_clamped(base, value)
            return candidate.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)

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
    - every 3 days - текст
    - every 2 hours - текст
    - каждые 3 дня - текст
    - каждые 2 часа - текст
    """
    expr, text = _split_expr_and_text(raw)
    expr_lower = expr.lower().strip()
    tokens = expr_lower.split()
    if not tokens:
        raise ValueError("Не понял повторяющийся формат")

    tokens_no_time, hour, minute = _extract_time_from_tokens(
        tokens,
        default_hour=10,
        default_minute=0,
    )
    if not tokens_no_time:
        raise ValueError("Не понял повторяющийся формат")

    first = tokens_no_time[0]

    pattern_type: Optional[str] = None
    payload: Dict[str, Any] = {}

    interval_units_en = {
        "minute": "minutes",
        "minutes": "minutes",
        "min": "minutes",
        "mins": "minutes",
        "hour": "hours",
        "hours": "hours",
        "day": "days",
        "days": "days",
        "week": "weeks",
        "weeks": "weeks",
        "month": "months",
        "months": "months",
    }

    interval_units_ru = {
        "минута": "minutes",
        "минуту": "minutes",
        "минуты": "minutes",
        "минут": "minutes",
        "мин": "minutes",
        "час": "hours",
        "часа": "hours",
        "часов": "hours",
        "день": "days",
        "дня": "days",
        "дней": "days",
        "дни": "days",
        "неделя": "weeks",
        "неделю": "weeks",
        "недели": "weeks",
        "недель": "weeks",
        "месяц": "months",
        "месяца": "months",
        "месяцев": "months",
    }

    # interval: every 3 days / каждые 3 дня / biweekly / every other week / раз в две недели
    if tokens_no_time in (["biweekly"], ["fortnightly"]):
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

    # daily
    if (first == "every" and len(tokens_no_time) >= 2 and tokens_no_time[1] == "day") or (
        len(tokens_no_time) == 1 and first in {"everyday", "daily"}
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
        if tokens_no_time == ["weekly"]:
            pattern_type = "weekly"
            payload = {"weekday": now.astimezone(TZ).weekday()}
        elif len(tokens_no_time) >= 2:
            second = tokens_no_time[1]
            if first == "every" and second in WEEKDAY_EN:
                pattern_type = "weekly"
                payload = {"weekday": WEEKDAY_EN[second]}
            elif first == "every" and second in {"week", "weeks"}:
                pattern_type = "weekly"
                payload = {"weekday": now.astimezone(TZ).weekday()}
            elif first.startswith("кажд") and second in WEEKDAY_RU:
                pattern_type = "weekly"
                payload = {"weekday": WEEKDAY_RU[second]}
            elif first.startswith("кажд") and second in {"неделю", "недели", "недель"}:
                pattern_type = "weekly"
                payload = {"weekday": now.astimezone(TZ).weekday()}

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
        ordinal_ru = {
            "первого": 1,
            "первое": 1,
            "второго": 2,
            "третьего": 3,
            "четвертого": 4,
            "четвёртого": 4,
            "пятого": 5,
            "шестого": 6,
            "седьмого": 7,
            "восьмого": 8,
            "девятого": 9,
            "десятого": 10,
        }

        def _parse_day_token(token: str) -> Optional[int]:
            if token.isdigit():
                return int(token)

            m = re.match(r"^(\d+)(?:st|nd|rd|th)$", token)
            if m:
                return int(m.group(1))

            return ordinal_ru.get(token)

        day = None

        if tokens_no_time in (["monthly"],):
            day = now.astimezone(TZ).day

        elif len(tokens_no_time) >= 2 and first == "every" and tokens_no_time[1] in {"month", "months"}:
            day = now.astimezone(TZ).day
            if len(tokens_no_time) >= 3:
                parsed = _parse_day_token(tokens_no_time[2])
                if parsed is not None:
                    day = parsed

        elif len(tokens_no_time) >= 2 and first.startswith("кажд") and tokens_no_time[1].startswith("месяц"):
            day = now.astimezone(TZ).day
            if len(tokens_no_time) >= 3:
                parsed = _parse_day_token(tokens_no_time[2])
                if parsed is not None:
                    day = parsed

        elif len(tokens_no_time) >= 4 and tokens_no_time[0] in {"каждое", "каждый", "каждого"}:
            parsed = _parse_day_token(tokens_no_time[1])
            if parsed is not None and tokens_no_time[2] in {"число", "числа"}:
                day = parsed

        elif len(tokens_no_time) >= 5 and first == "every":
            parsed = _parse_day_token(tokens_no_time[1])
            if parsed is not None and tokens_no_time[2:] == ["of", "the", "month"]:
                day = parsed

        elif len(tokens_no_time) >= 4:
            parsed = _parse_day_token(tokens_no_time[0])
            if parsed is not None and tokens_no_time[1] in {"число", "числа"} and any(t.startswith("месяц") for t in tokens_no_time[2:]):
                day = parsed

        if day is not None:
            if not (1 <= day <= 31):
                raise ValueError("Неверный день месяца для повторяющегося напоминания")
            pattern_type = "monthly"
            payload = {"day": day}

    # yearly: yearly / every year / каждый год / every year on december 25 [10:00] - text
    if pattern_type is None:
        if tokens_no_time == ["yearly"]:
            now_local = now.astimezone(TZ)
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
                now_local = now.astimezone(TZ)
                pattern_type = "yearly"
                payload = {"month": now_local.month, "day": now_local.day}

        elif len(tokens_no_time) >= 2 and first.startswith("кажд") and tokens_no_time[1] in {"год", "года"}:
            now_local = now.astimezone(TZ)
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

    if pattern_type == "interval":
        value = int(payload.get("value", 0))
        unit = str(payload.get("unit", "")).lower()

        if unit == "minutes":
            return f"every {value} minute{'s' if value != 1 else ''}"
        if unit == "hours":
            return f"every {value} hour{'s' if value != 1 else ''}"
        if unit == "days":
            return f"every {value} day{'s' if value != 1 else ''}"
        if unit == "weeks":
            return f"every {value} week{'s' if value != 1 else ''}"
        if unit == "months":
            return f"every {value} month{'s' if value != 1 else ''}"

        return f"every {value} {unit}".strip()

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

def build_group_reminder_keyboard(reminder_id: int) -> Optional[InlineKeyboardMarkup]:
    try:
        buttons: List[List[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    "Напомнить мне лично",
                    callback_data=f"selfremind:ask:{reminder_id}",
                ),
            ],
        ]
        return InlineKeyboardMarkup(buttons)
    except TypeError:
        # В тестовой среде InlineKeyboardButton/Markup могут быть подменены на object.
        # В этом случае просто не рисуем клавиатуру, чтобы не ломать worker delivery tests.
        return None

def build_self_remind_mode_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                "📅 Обычное напоминание",
                callback_data=f"selfremind:mode:{reminder_id}:regular",
            ),
        ],
        [
            InlineKeyboardButton(
                '⏰ Напоминание "до события"',
                callback_data=f"selfremind:mode:{reminder_id}:event",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Я передумал, напоминание не нужно",
                callback_data=f"selfremind:cancel_personal:{reminder_id}",
            ),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

def build_self_remind_choice_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("⏰ +20 минут", callback_data=f"selfremind:set:{reminder_id}:20m"),
            InlineKeyboardButton("⏰ +1 час", callback_data=f"selfremind:set:{reminder_id}:1h"),
        ],
        [
            InlineKeyboardButton("⏰ +3 часа", callback_data=f"selfremind:set:{reminder_id}:3h"),
            InlineKeyboardButton("📅 Завтра (11:00)", callback_data=f"selfremind:set:{reminder_id}:tomorrow11"),
        ],
        [
            InlineKeyboardButton("📅 Следующий понедельник (11:00)", callback_data=f"selfremind:set:{reminder_id}:nextmon"),
            InlineKeyboardButton("📝 Кастом", callback_data=f"selfremind:set:{reminder_id}:custom"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data=f"selfremind:back:{reminder_id}"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def build_self_remind_event_before_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📅 За сутки", callback_data=f"selfremind:event_before:{reminder_id}:1d"),
            InlineKeyboardButton("⏰ За 10 часов", callback_data=f"selfremind:event_before:{reminder_id}:10h"),
        ],
        [
            InlineKeyboardButton("⏰ За 3 часа", callback_data=f"selfremind:event_before:{reminder_id}:3h"),
            InlineKeyboardButton("⏰ За 1 час", callback_data=f"selfremind:event_before:{reminder_id}:1h"),
        ],
        [
            InlineKeyboardButton("⏰ За 20 минут", callback_data=f"selfremind:event_before:{reminder_id}:20m"),
            InlineKeyboardButton("📝 Кастом", callback_data=f"selfremind:event_custom:{reminder_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data=f"selfremind:back:{reminder_id}"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

def compute_self_remind_time(option: str, now: datetime) -> datetime:
    now = now.astimezone(TZ)

    if option == "20m":
        return now + timedelta(minutes=20)

    if option == "1h":
        return now + timedelta(hours=1)

    if option == "3h":
        return now + timedelta(hours=3)

    if option == "tomorrow11":
        tomorrow = (now + timedelta(days=1)).date()
        return datetime(
            tomorrow.year,
            tomorrow.month,
            tomorrow.day,
            11,
            0,
            tzinfo=TZ,
        )

    if option == "nextmon":
        base = now.date()
        cur_wd = base.weekday()
        delta = (0 - cur_wd + 7) % 7
        if delta == 0:
            delta = 7
        target = base + timedelta(days=delta)
        return datetime(
            target.year,
            target.month,
            target.day,
            11,
            0,
            tzinfo=TZ,
        )

    raise ValueError(f"Unknown self reminder option: {option}")

def format_self_remind_text(source_chat_title: str, source_text: str) -> str:
    return f'Из чата "{source_chat_title}": {source_text}'


def get_query_source_chat_title(query) -> str:
    source_chat_title = "этого чата"
    if getattr(query, "message", None) is not None:
        chat_obj = getattr(query.message, "chat", None)
        if chat_obj is not None:
            source_chat_title = (
                getattr(chat_obj, "title", None)
                or getattr(chat_obj, "full_name", None)
                or "этого чата"
            )
    return source_chat_title

async def get_source_chat_title_for_self_remind(context: CTX, src, query) -> str:
    try:
        chat = await context.bot.get_chat(src.chat_id)
        return (
            getattr(chat, "title", None)
            or getattr(chat, "full_name", None)
            or getattr(chat, "username", None)
            or f"chat {src.chat_id}"
        )
    except Exception:
        return get_query_source_chat_title(query)

from calendar import monthrange
from datetime import date, datetime, timedelta

def build_custom_date_keyboard(
    reminder_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    callback_prefix: str = "snooze",
):
    """
    Красивый календарь на месяц:
    - Заголовок "Январь 2026"
    - Ряд дней недели
    - Сетка дней 7x6
    - Навигация prev/next месяц
    - Today и Cancel
    """
    today = datetime.now(TZ).date()

    if year is None or month is None:
        year = today.year
        month = today.month

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
    }
    title = f"{month_names.get(month, str(month))} {year}"

    first_weekday, days_in_month = monthrange(year, month)
    start_offset = first_weekday

    def _btn(text: str, cb: str):
        return InlineKeyboardButton(text=text, callback_data=cb)

    def _noop(text: str):
        return InlineKeyboardButton(text=text, callback_data="noop")

    keyboard: list[list[InlineKeyboardButton]] = [
        [_noop(title)],
        [_noop("Пн"), _noop("Вт"), _noop("Ср"), _noop("Чт"), _noop("Пт"), _noop("Сб"), _noop("Вс")],
    ]

    cells: list[InlineKeyboardButton] = []

    for _ in range(start_offset):
        cells.append(_noop(" "))

    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        iso = d.isoformat()

        label = str(day)
        if d == today:
            label = f"·{day}·"

        if d < today:
            cells.append(_btn(label, f"{callback_prefix}_pastdate:{reminder_id}:{iso}"))
        else:
            cells.append(_btn(label, f"{callback_prefix}_pickdate:{reminder_id}:{iso}"))

    while len(cells) % 7 != 0:
        cells.append(_noop(" "))

    while len(cells) < 42:
        cells.append(_noop(" "))

    for i in range(0, 42, 7):
        keyboard.append(cells[i:i + 7])

    prev_year = year
    prev_month = month - 1
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    next_year = year
    next_month = month + 1
    if next_month == 13:
        next_month = 1
        next_year += 1

    keyboard.append(
        [
            _btn("◀", f"{callback_prefix}_cal:{reminder_id}:{prev_year:04d}-{prev_month:02d}"),
            _btn("Today", f"{callback_prefix}_caltoday:{reminder_id}"),
            _btn("▶", f"{callback_prefix}_cal:{reminder_id}:{next_year:04d}-{next_month:02d}"),
        ]
    )

    keyboard.append([_btn("Cancel", f"{callback_prefix}_cancel:{reminder_id}")])

    return InlineKeyboardMarkup(keyboard)

from datetime import datetime, date

def build_custom_time_keyboard(reminder_id: int, date_str: str, callback_prefix: str = "snooze"):
    """
    Красивый выбор времени:
    - Заголовок "Время - 02.02.2026"
    - Сетка кнопок времени
    - Back (назад в календарь выбранного месяца)
    - Cancel
    """
    try:
        y, m, d = map(int, date_str.split("-"))
        chosen = date(y, m, d)
    except Exception:
        chosen = datetime.now(TZ).date()

    def _btn(text: str, cb: str):
        return InlineKeyboardButton(text=text, callback_data=cb)

    def _noop(text: str):
        return InlineKeyboardButton(text=text, callback_data="noop")

    title = chosen.strftime("Время - %d.%m.%Y")

    keyboard: list[list[InlineKeyboardButton]] = [
        [_noop(title)],
    ]

    times = [
        "10:00", "10:30", "11:00", "11:30",
        "12:00", "12:30", "13:00", "13:30",
        "14:00", "15:00", "16:00", "18:00",
        "20:00", "21:00", "22:00", "23:00",
    ]

    row: list[InlineKeyboardButton] = []
    for t in times:
        row.append(_btn(t, f"{callback_prefix}_picktime:{reminder_id}:{chosen.isoformat()}:{t}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append(
        [
            _btn("◀ Back", f"{callback_prefix}_cal:{reminder_id}:{chosen.year:04d}-{chosen.month:02d}"),
            _btn("Cancel", f"{callback_prefix}_cancel:{reminder_id}"),
        ]
    )

    return InlineKeyboardMarkup(keyboard)

# ===== Парсинг даты события из текста напоминания =====

def _nearest_future_time_from_base(hour: int, minute: int, base_now: datetime) -> datetime:
    local = base_now.astimezone(TZ)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate = candidate + timedelta(days=1)
    return candidate


def _parse_time_match(match: re.Match) -> Tuple[int, int]:
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError("Неверное время события")
    return hour, minute


def _build_event_datetime(year: int, month: int, day: int, hour: int, minute: int, base_now: datetime) -> datetime:
    local = base_now.astimezone(TZ)
    dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
    if dt <= local:
        try:
            dt = dt.replace(year=year + 1)
        except ValueError as e:
            raise ValueError(f"Неверная дата события: {e}") from e
    return dt


def extract_event_datetime_from_text(text: str, base_now: datetime) -> Optional[datetime]:
    """
    Best-effort парсер даты/времени события из текста reminder-а.

    Важно:
    - base_now = время прихода исходного reminder-а, а не время клика
    - не трогаем основной parse_date_time_smart
    """
    raw = (text or "").strip()
    if not raw:
        return None

    s = raw.lower()
    local = base_now.astimezone(TZ)

    time_re = r"(?P<hour>\d{1,2})[:.](?P<minute>\d{2})"

    relative_days = {
        "сегодня": 0,
        "today": 0,
        "завтра": 1,
        "tomorrow": 1,
        "послезавтра": 2,
        "day after tomorrow": 2,
    }

    # 1) Relative date где угодно + ближайшее время после нее:
    # "завтра футбол в 15:00", "football tomorrow at 15:00"
    for phrase, days in sorted(relative_days.items(), key=lambda x: -len(x[0])):
        m_date = re.search(rf"\b{re.escape(phrase)}\b", s)
        if not m_date:
            continue

        tail = s[m_date.end():]
        m_time = re.search(rf"(?:\bв\s+|\bat\s+)?{time_re}", tail)
        if not m_time:
            continue

        try:
            hour, minute = _parse_time_match(m_time)
        except ValueError:
            return None

        target_date = local.date() + timedelta(days=days)
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=TZ,
        )

    # 2) DD.MM / DD.MM.YYYY + время после даты, между ними могут быть слова:
    # "03.05 футбол в 15:00", "футбол 03.05 в 15:00"
    m = re.search(
        rf"(?P<day>\d{{1,2}})[./](?P<month>\d{{1,2}})(?:[./](?P<year>\d{{2,4}}))?"
        rf"(?P<middle>.{{0,80}}?)(?:\bв\s+|\bat\s+|\s+){time_re}",
        s,
    )
    if m:
        try:
            day = int(m.group("day"))
            month = int(m.group("month"))
            year_raw = m.group("year")
            if year_raw:
                year = int(year_raw)
                if year < 100:
                    year += 2000
            else:
                year = local.year

            hour, minute = _parse_time_match(m)
            return _build_event_datetime(year, month, day, hour, minute, base_now)
        except ValueError:
            return None

    # 3) Month name + day + время после даты:
    # "May 3 football at 15:00", "football on May 3 at 15:00"
    month_names = "|".join(sorted(MONTH_EN.keys(), key=len, reverse=True))
    m = re.search(
        rf"(?:\bon\s+)?(?P<month_name>{month_names})\s+(?P<day>\d{{1,2}})"
        rf"(?:\s+(?P<year>\d{{4}}))?"
        rf"(?P<middle>.{{0,80}}?)(?:\bв\s+|\bat\s+|\s+){time_re}",
        s,
    )
    if m:
        try:
            month = int(MONTH_EN[m.group("month_name")])
            day = int(m.group("day"))
            year = int(m.group("year")) if m.group("year") else local.year
            hour, minute = _parse_time_match(m)
            return _build_event_datetime(year, month, day, hour, minute, base_now)
        except ValueError:
            return None

    # 4) Day + month name + время после даты:
    # "3 May football at 15:00", "football on 3 May at 15:00"
    m = re.search(
        rf"(?:\bon\s+)?(?P<day>\d{{1,2}})\s+(?P<month_name>{month_names})"
        rf"(?:\s+(?P<year>\d{{4}}))?"
        rf"(?P<middle>.{{0,80}}?)(?:\bв\s+|\bat\s+|\s+){time_re}",
        s,
    )
    if m:
        try:
            month = int(MONTH_EN[m.group("month_name")])
            day = int(m.group("day"))
            year = int(m.group("year")) if m.group("year") else local.year
            hour, minute = _parse_time_match(m)
            return _build_event_datetime(year, month, day, hour, minute, base_now)
        except ValueError:
            return None

    # 5) Только время с явным предлогом:
    # "футбол в 15:00", "football at 15:00"
    m = re.search(rf"(?:\bв\s+|\bat\s+){time_re}", s)
    if m:
        try:
            hour, minute = _parse_time_match(m)
        except ValueError:
            return None
        return _nearest_future_time_from_base(hour, minute, base_now)

    return None


def normalize_relative_event_date_in_text(text: str, event_at: datetime) -> str:
    """
    Для event-based self-remind заменяем относительные даты на абсолютные,
    чтобы личный reminder не говорил "завтра", когда событие уже сегодня.

    Меняем только первое вхождение.
    """
    event_date = event_at.astimezone(TZ).strftime("%d.%m")

    replacements = [
        r"\bday after tomorrow\b",
        r"\btomorrow\b",
        r"\btoday\b",
        r"\bпослезавтра\b",
        r"\bзавтра\b",
        r"\bсегодня\b",
    ]

    result = text
    for pattern in replacements:
        result, count = re.subn(
            pattern,
            event_date,
            result,
            count=1,
            flags=re.IGNORECASE,
        )
        if count:
            return result

    return result


def get_self_remind_event_base(src: Reminder) -> datetime:
    return src.sent_at or src.remind_at


def compute_event_before_time(option: str, event_at: datetime) -> Optional[datetime]:
    if option == "20m":
        return event_at - timedelta(minutes=20)
    if option == "1h":
        return event_at - timedelta(hours=1)
    if option == "3h":
        return event_at - timedelta(hours=3)
    if option == "10h":
        return event_at - timedelta(hours=10)
    if option == "1d":
        return event_at - timedelta(days=1)
    return None


# ===== Хендлеры команд =====

async def safe_reply(message, text: str, **kwargs):
    if not message or not hasattr(message, "reply_text"):
        return

    res = message.reply_text(text, **kwargs)
    if inspect.isawaitable(res):
        await res

async def start(update: Update, context: CTX) -> None:
    chat = update.effective_chat
    user = update.effective_user

    if chat is None or user is None:
        return

    # В группах /start молчит (чтобы не спамить)
    if chat.type != Chat.PRIVATE:
        return

    upsert_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
    )

    text = dedent("""
        Привет. Я бот для напоминаний.

        Что я умею:
        • ставить обычные напоминания обычным текстом
        • ставить повторяющиеся напоминания
        • принимать голосовые в личке
        • напоминать тебе, другому человеку или в привязанный чат
        • показывать список активных напоминаний и удалять их кнопками

        Самый простой способ:
        просто напиши мне обычным текстом, что и когда напомнить.

        Например:
        напомни завтра в 11 купить молоко
        сегодня в 18:00 позвонить маме
        через 2 часа проверить духовку
        каждый вторник пить таблетки

        Голосом:
        Просто отправь мне голосовое в личке.
        Например: «напомни завтра в 11 купить молоко»
        Или: «напомни Наташе завтра в 12 позвонить» (если ты уже освоил алиасы)

        Быстрый старт:
        /remind завтра 11:00 - купить молоко
        /remind 29.11 - текст
        /remind 23:59 - текст
        /remind in 2 hours - текст

        Повторяющиеся:
        /remind каждый вторник - пить таблетки
        /remind every day 10:00 - пить воду

        Алиасы:
        /linkuser Наташа @username
        /linkchat football (в конкретном чате надо вводить команду)
        /aliases - показать все алиасы
        /unalias Наташа
        /renamealias Наташа -> Ната

        После этого:
        напомни Наташе завтра в 12 позвонить
        /remind football 28.11 12:00 - матч

        Список и удаление:
        /list - показать активные напоминания и удалить кнопками
        /list Наташа - напоминания для user-alias
        /list football - напоминания для chat-alias

        Все форматы и подробности: /help
    """).strip()

    msg = update.effective_message
    if msg and hasattr(msg, "reply_text"):
        res = msg.reply_text(text)
        if inspect.isawaitable(res):
            await res

async def start_command(update: Update, context: CTX) -> None:
    await start(update, context)

async def help_command(update: Update, context: CTX) -> None:
    message = update.effective_message
    if message is None:
        return

    text = dedent("""
        📌 Бот для напоминаний — подробная справка

        ======================
        САМЫЙ ПРОСТОЙ СПОСОБ
        ======================
        Просто напиши обычным текстом, что и когда напомнить.

        Примеры:
        напомни завтра в 11 купить молоко
        сегодня в 18:00 позвонить маме
        через 2 часа проверить духовку
        каждый вторник пить таблетки

        Голосом тоже можно:
        отправь голосовое в личке, например:
        «напомни завтра в 11 купить молоко»

        Команды тоже работают:
        /remind ДАТА ВРЕМЯ - текст
        /remind me ДАТА ВРЕМЯ - текст

        Примеры команд:
        /remind 28.11 12:00 - завтра футбол
        /remind me at 18.00 - купить молоко

        ======================
        РАЗОВЫЕ НАПОМИНАНИЯ
        ======================

        Можно писать как обычным текстом, так и через /remind.
        Если бот не понял обычный текст, попробуй явный формат:
        /remind ДАТА ВРЕМЯ - текст

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

        🔁 Каждый день / неделю / месяц / год:
        /remind every day 10:00 - текст
        /remind каждый день 10:00 - текст
        /remind every Monday 10:00 - текст
        /remind каждую среду 19:00 - текст
        /remind every month 15 10:00 - текст
        /remind every year on December 25 10:00 - текст

        🔁 Будни / выходные:
        /remind every weekday 09:00 - текст
        /remind каждые выходные 11:00 - текст

        🔁 Интервалы:
        /remind every 3 days - пить лекарство
        /remind каждые 2 часа - размяться
        /remind every 10 minutes - выпить воды
        /remind каждые 2 недели 09:00 - отчет

        Если время не указано, используется 11:00.

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

        🔗 Привязка chat-alias:
        В нужном чате:
            /linkchat football

        Использование в личке:
            напомни football завтра в 12 матч
            /remind football 28.11 12:00 - матч
            /list football

        👤 Привязка user-alias:
        В личке:
            /linkuser misha @username

        Использование:
            напомни misha завтра в 18 созвон
            /remind misha 28.11 18:00 - созвон
            /list misha

        📚 Управление алиасами:
            /aliases
            /unalias Наташа
            /renamealias Наташа -> Ната

        📨 Напоминания конкретному человеку:
            /list @username

        Показывает только те reminders,
        которые ТЫ поставил этому пользователю.

        ⚠️ User-alias работает только если
        пользователь уже писал боту в личку.


        ======================
        ПРОЧЕЕ
        ======================

        ⏰ После срабатывания напоминания доступны кнопки SNOOZE:
        +20 минут, +1 час, +3 часа, завтра, следующий понедельник,
        либо кастомная дата и время.
    """).strip()

    await safe_reply(message,text)


async def linkchat_command(update: Update, context: CTX) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    if chat.type == Chat.PRIVATE:
        await safe_reply(
            message,
            "Команду /linkchat нужно вызывать в групповом чате, который хочешь привязать."
        )
        return

    if not context.args:
        await safe_reply(
            message,
            "Формат: /linkchat alias\nНапример: /linkchat football"
        )
        return

    alias = context.args[0].strip()
    if not alias:
        await safe_reply(message, "Alias не должен быть пустым.")
        return

    title = chat.title or chat.username or str(chat.id)

    set_chat_alias_for_user(
        alias=alias,
        chat_id=chat.id,
        title=title,
        created_by=user.id,
    )

    await safe_reply(
        message,
        f"Ок, запомнил этот чат как '{alias}' для тебя.\n"
        f"Теперь в личке можно писать:\n"
        f"/remind {alias} 28.11 12:00 - завтра футбол"
    )

from typing import Tuple

async def aliases_command(update: Update, context: CTX) -> None:
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    user_aliases = []
    chat_aliases = []

    try:
        for alias, chat_id in get_all_user_aliases(user.id):
            row = get_user_alias(alias, user.id) or {}
            username = row.get("username")
            if username:
                user_aliases.append(f"• {alias} -> @{username} / chat_id={chat_id}")
            else:
                user_aliases.append(f"• {alias} -> chat_id={chat_id}")
    except Exception:
        logger.exception("Не смог получить user aliases")
        await safe_reply(message, "Не смог получить user-aliases.")
        return

    try:
        for alias, chat_id, title in get_all_aliases(user.id):
            if title:
                chat_aliases.append(f"• {alias} -> {title} / chat_id={chat_id}")
            else:
                chat_aliases.append(f"• {alias} -> chat_id={chat_id}")
    except Exception:
        logger.exception("Не смог получить chat aliases")
        await safe_reply(message, "Не смог получить chat-aliases.")
        return

    if not user_aliases and not chat_aliases:
        await safe_reply(
            message,
            "Алиасов пока нет.\n\n"
            "Создать chat-alias: /linkchat football\n"
            "Создать user-alias: /linkuser Наташа @username"
        )
        return

    parts = ["Текущие алиасы:"]

    if user_aliases:
        parts.append("\n👤 User aliases:")
        parts.extend(user_aliases)

    if chat_aliases:
        parts.append("\n💬 Chat aliases:")
        parts.extend(chat_aliases)

    parts.append(
        "\nКоманды:\n"
        "/unalias <alias>\n"
        "/renamealias <old> -> <new>"
    )

    await safe_reply(message, "\n".join(parts))

async def unalias_command(update: Update, context: CTX) -> None:
    message = update.effective_message
    if message is None:
        return

    alias = " ".join(getattr(context, "args", []) or []).strip()
    if not alias:
        await safe_reply(
            message,
            "Использование: /unalias <alias>\n"
            "Пример: /unalias Наташа"
        )
        return

    user = update.effective_user
    if user is None:
        return

    deleted_user = delete_user_alias(alias, user.id)
    deleted_chat = delete_chat_alias(alias, user.id)

    if not deleted_user and not deleted_chat:
        await safe_reply(message, f"Alias '{alias}' не найден.")
        return

    deleted_parts = []
    if deleted_user:
        deleted_parts.append("user-alias")
    if deleted_chat:
        deleted_parts.append("chat-alias")

    await safe_reply(
        message,
        f"Удалил alias '{alias}' из: {', '.join(deleted_parts)}."
    )

def parse_renamealias_args(args: List[str]) -> Tuple[Optional[str], Optional[str]]:
    if not args:
        return None, None

    if "->" in args:
        arrow_idx = args.index("->")
        old_alias = " ".join(args[:arrow_idx]).strip()
        new_alias = " ".join(args[arrow_idx + 1:]).strip()
        if not old_alias or not new_alias:
            return None, None
        return old_alias, new_alias

    if len(args) < 2:
        return None, None

    old_alias = args[0].strip()
    new_alias = " ".join(args[1:]).strip()

    if not old_alias or not new_alias:
        return None, None

    return old_alias, new_alias

async def renamealias_command(update: Update, context: CTX) -> None:
    message = update.effective_message
    if message is None:
        return

    old_alias, new_alias = parse_renamealias_args(getattr(context, "args", []) or [])
    if not old_alias or not new_alias:
        await safe_reply(
            message,
            "Использование: /renamealias <old> -> <new>\n"
            "Пример: /renamealias Наташа -> Натали"
        )
        return

    try:
        user = update.effective_user
        if user is None:
            return
        
        renamed_user = rename_user_alias(old_alias, new_alias, user.id)
        renamed_chat = rename_chat_alias(old_alias, new_alias, user.id)
    except ValueError as e:
        await safe_reply(message, str(e))
        return

    if not renamed_user and not renamed_chat:
        await safe_reply(message, f"Alias '{old_alias}' не найден.")
        return

    renamed_parts = []
    if renamed_user:
        renamed_parts.append("user-alias")
    if renamed_chat:
        renamed_parts.append("chat-alias")

    await safe_reply(
        message,
        f"Переименовал '{old_alias}' -> '{new_alias}' в: {', '.join(renamed_parts)}."
    )

def _rest_starts_like_datetime(s: str) -> bool:
    """
    True если строка начинается похоже на дату/время/относительное выражение.
    Достаточно для кейсов типа: "02.02 - hi", "02.02 12:00 - hi", "23:40 - hi", "tomorrow 10:00 - hi".
    """
    s = s.strip().lower()
    if not s:
        return False

    # DD.MM / DD/MM / DD-MM
    if re.match(r"^\d{1,2}[./-]\d{1,2}(\s|$)", s):
        return True

    # HH:MM / HH.MM
    if re.match(r"^\d{1,2}[:.]\d{2}(\s|$)", s):
        return True

    # дружественные фразы
    if re.match(r"^(today|tomorrow|day\s+after\s+tomorrow|сегодня|завтра|послезавтра)\b", s):
        return True

    # in/через
    if re.match(r"^(in|через)\b", s):
        return True

    return False


def _strip_leading_token_in_group(raw_args: str) -> Tuple[str, bool]:
    """
    В group-чате игнорируем возможные 'роутинг-токены' в начале:
    /remind TeamA 02.02 - hi
    /remind @someone 02.02 - hi

    Возвращает (новая_строка, изменилось_ли).
    """
    s = raw_args.strip()
    if not s:
        return raw_args, False

    # bulk не трогаем
    if "\n" in s:
        return raw_args, False

    parts = s.split(maxsplit=1)
    if len(parts) != 2:
        return raw_args, False

    first = parts[0].strip()
    rest = parts[1].strip()
    if not first or not rest:
        return raw_args, False

    if _rest_starts_like_datetime(rest):
        return rest, True

    return raw_args, False

def _create_single_reminder_from_line(
    *,
    line: str,
    now,
    target_chat_id: int,
    user,
):
    """
    Создает одно напоминание (oneoff или recurring) из строки.
    Бросает исключение при ошибке.
    """

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

def _format_bulk_result(
    *,
    created: int,
    failed: int,
    error_lines,
):
    parts = []

    parts.append(f"Готово. Создано напоминаний: {created}.")

    if failed:
        parts.append(f"Не удалось разобрать строк: {failed}.")

        preview = error_lines[:5]
        lines = ["", "Проблемные строки (до 5):"]
        for idx, original, error in preview:
            lines.append(f"{idx}) '{original}': {error}")

        parts.append("\n".join(lines))

    return " ".join(parts)

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
    replacements = {
        "первого": "1",
        "второго": "2",
        "третьего": "3",
        "четвертого": "4",
        "четвёртого": "4",
        "пятого": "5",
        "шестого": "6",
        "седьмого": "7",
        "восьмого": "8",
        "девятого": "9",
        "десятого": "10",
        "одиннадцатого": "11",
        "двенадцатого": "12",
        "тринадцатого": "13",
        "четырнадцатого": "14",
        "пятнадцатого": "15",
        "шестнадцатого": "16",
        "семнадцатого": "17",
        "восемнадцатого": "18",
        "девятнадцатого": "19",
        "двадцатого": "20",
        "двадцать первого": "21",
        "двадцать второго": "22",
        "двадцать третьего": "23",
        "двадцать четвертого": "24",
        "двадцать четвёртого": "24",
        "двадцать пятого": "25",
        "двадцать шестого": "26",
        "двадцать седьмого": "27",
        "двадцать восьмого": "28",
        "двадцать девятого": "29",
        "тридцатого": "30",
        "тридцать первого": "31",
        "ноль": "0",
        "один": "1",
        "два": "2",
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
        "тринадцать": "13",
        "четырнадцать": "14",
        "пятнадцать": "15",
        "шестнадцать": "16",
        "семнадцать": "17",
        "восемнадцать": "18",
        "девятнадцать": "19",
        "двадцать девять": "29",
        "двадцать восемь": "28",
        "двадцать семь": "27",
        "двадцать шесть": "26",
        "двадцать пять": "25",
        "двадцать четыре": "24",
        "двадцать три": "23",
        "двадцать два": "22",
        "двадцать один": "21",

        "тридцать девять": "39",
        "тридцать восемь": "38",
        "тридцать семь": "37",
        "тридцать шесть": "36",
        "тридцать пять": "35",
        "тридцать четыре": "34",
        "тридцать три": "33",
        "тридцать два": "32",
        "тридцать один": "31",

        "сорок девять": "49",
        "сорок восемь": "48",
        "сорок семь": "47",
        "сорок шесть": "46",
        "сорок пять": "45",
        "сорок четыре": "44",
        "сорок три": "43",
        "сорок два": "42",
        "сорок один": "41",

        "пятьдесят девять": "59",
        "пятьдесят восемь": "58",
        "пятьдесят семь": "57",
        "пятьдесят шесть": "56",
        "пятьдесят пять": "55",
        "пятьдесят четыре": "54",
        "пятьдесят три": "53",
        "пятьдесят два": "52",
        "пятьдесят один": "51",

        "двадцать": "20",
        "тридцать": "30",
        "сорок": "40",
        "пятьдесят": "50",
    }

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
    month_map = {
        "января": "january",
        "февраля": "february",
        "марта": "march",
        "апреля": "april",
        "мая": "may",
        "июня": "june",
        "июля": "july",
        "августа": "august",
        "сентября": "september",
        "октября": "october",
        "ноября": "november",
        "декабря": "december",
    }

    result = s
    for ru, en in month_map.items():
        result = re.sub(rf"\b{ru}\b", en, result, flags=re.IGNORECASE)

    return result

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
def _is_transient_gemini_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "500" in text
        or "internal" in text
        or "503" in text
        or "unavailable" in text
        or "high demand" in text
        or "temporar" in text
        or "deadline_exceeded" in text
        or "429" in text
        or "resource_exhausted" in text
    )

def _is_unsupported_gemini_model_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "404" in text
        and (
            "not_found" in text
            or "is not found" in text
            or "not supported for generatecontent" in text
            or "listmodels" in text
        )
    )

def _is_gemini_quota_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "429" in text
        and (
            "resource_exhausted" in text
            or "quota exceeded" in text
            or "check your plan and billing" in text
            or "free_tier" in text
            or "limit: 0" in text
        )
    )

def _format_known_aliases_for_voice_prompt(created_by: int) -> str:
    """
    Собираем известные aliases текущего пользователя для Gemini voice-normalization.

    Gemini не должен видеть чужие aliases и не должен придумывать aliases из воздуха.
    """
    user_aliases = []
    chat_aliases = []

    try:
        user_aliases = [a for a, _chat_id in get_all_user_aliases(created_by)]
    except Exception:
        logger.exception("Не смог получить user aliases для voice prompt")
        user_aliases = []

    try:
        chat_aliases = [a for a, _chat_id, _title in get_all_aliases(created_by)]
    except Exception:
        logger.exception("Не смог получить chat aliases для voice prompt")
        chat_aliases = []

    lines = [
        "Known aliases. Use these only if the spoken target clearly matches one of them.",
        "",
        "Known user aliases:",
    ]

    if user_aliases:
        for alias in sorted(set(user_aliases), key=str.lower):
            lines.append(f"- {alias}")
    else:
        lines.append("- none")

    lines.extend(["", "Known chat aliases:"])

    if chat_aliases:
        for alias in sorted(set(chat_aliases), key=str.lower):
            lines.append(f"- {alias}")
    else:
        lines.append("- none")

    return "\n".join(lines)

async def _gemini_transcribe_audio_with_retries(
    *,
    client,
    audio_bytes: bytes,
    attempts_per_model: Optional[int] = None,
    aliases_prompt: str = "",
) -> str:
    models_raw = os.environ.get(
        "GEMINI_TRANSCRIBE_MODELS",
        "gemini-2.5-flash-lite,gemini-2.5-flash",
    )

    models = [m.strip() for m in models_raw.split(",") if m.strip()]
    if not models:
        models = ["gemini-2.5-flash-lite"]

    last_error: Optional[Exception] = None
    if attempts_per_model is None:
        try:
            attempts_per_model = int(os.environ.get("GEMINI_TRANSCRIBE_ATTEMPTS", "1"))
        except ValueError:
            attempts_per_model = 1

    attempts_per_model = max(1, min(5, attempts_per_model))

    for model in models:
        for attempt in range(1, attempts_per_model + 1):
            try:
                result = client.models.generate_content(
                    model=model,
                    contents=[
                        genai_types.Part.from_bytes(
                            data=audio_bytes,
                            mime_type="audio/ogg",
                        ),
                        (
                            "You are normalizing a Telegram voice reminder.\n"
                            "\n"
                            "Listen to the audio and return only one line in this exact format:\n"
                            "<optional target alias> <date/time expression> - <reminder text>\n"
                            "\n"
                            "The output must be directly usable after '/remind '.\n"
                            "\n"
                            "Rules:\n"
                            "- Return only the normalized reminder command. No quotes. No markdown. No commentary.\n"
                            "- Preserve the reminder text meaning.\n"
                            "- Never change an explicitly spoken time. If the user says 'в 12', return '12:00'.\n"
                            "- If the user says 'в 14:55', return '14:55' exactly.\n"
                            "- Remove leading phrases like 'напомни', 'напомни мне', 'поставь напоминание', 'remind me'.\n"
                            "- Convert spoken Russian numbers to digits where needed.\n"
                            "- Convert Russian month names to English month names.\n"
                            "- Convert Russian number words to digits in intervals: 'два часа' -> '2 часа', 'три дня' -> '3 дня'.\n"
                            "- Convert fractional Russian intervals to parser-friendly units: 'полчаса' -> 'every 30 minutes', 'полтора часа' -> 'every 90 minutes'.\n"
                            "- Do not calculate actual dates. Keep relative expressions like 'завтра', 'следующий понедельник', '29 may'.\n"
                            "- Support one-off reminders, recurring reminders, private target aliases, and chat aliases.\n"
                            "- Use a target alias only if it appears in the known aliases list below.\n"
                            "- Do not invent aliases or usernames.\n"
                            "- If a spoken person name is an inflected form of a known user alias, normalize it to that alias.\n"
                            "- Examples: known alias 'Наташа': 'Наташе', 'Наташу', 'Наташи' -> 'Наташа'.\n"
                            "- Examples: known alias 'Миша': 'Мише', 'Мишу', 'Миши' -> 'Миша'.\n"
                            "- Examples: known alias 'Леша': 'Леше', 'Лёше', 'Лешу', 'Лёшу' -> 'Леша'.\n"
                            "- If the spoken person name is not in known aliases, keep it inside reminder text, not as target.\n"
                            "- If the user says only a time like 'в 11 купить молоко', return '11:00 - купить молоко'.\n"
                            "- If the user says 'завтра в 11 купить молоко', return 'завтра 11:00 - купить молоко'.\n"
                            "- If the user says 'напомни завтра в 14:55 позвонить доктору', return 'завтра 14:55 - позвонить доктору'.\n"
                            "- If the user says 'в следующий понедельник в 22:00 спросить как дела', return 'следующий понедельник 22:00 - спросить как дела'.\n"
                            "- If the user says 'двадцать девятого мая в восемнадцать сорок шесть спросить как дела', return '29 may 18:46 - спросить как дела'.\n"
                            "- If known user alias list contains 'Наташа' and user says 'напомнить Наташе завтра в 12 позвонить', return 'Наташа завтра 12:00 - позвонить'.\n"
                            "- If known user alias list does not contain 'Наташа', return 'завтра 12:00 - позвонить Наташе'.\n"
                            "- If known chat alias list contains 'football' and user says 'напомни football завтра в 12 матч', return 'football завтра 12:00 - матч'.\n"
                            "- For recurring reminders, keep a parser-friendly recurring expression with explicit time.\n"
                            "- If the user says 'каждый понедельник в 11 выпить таблетку', return 'каждый понедельник 11:00 - выпить таблетку'.\n"
                            "- If the user says 'каждый день в 9 пить воду', return 'каждый день 09:00 - пить воду'.\n"
                            "- If the user says 'напоминай каждые два часа пить воды', return 'каждые 2 часа - пить воды'.\n"
                            "- If the user says 'напоминай каждые полтора часа пить воды', return 'every 90 minutes - пить воды'.\n"
                            "- If the user says 'напоминай каждые полчаса пить воды', return 'every 30 minutes - пить воды'.\n"
                            "- If the user says 'every Monday at 11 take a pill', return 'every monday 11:00 - take a pill'.\n"
                            "- If the user says 'every day at 9 drink water', return 'every day 09:00 - drink water'.\n"
                            "\n"
                            f"{aliases_prompt}\n"
                        ),
                    ],
                )

                text = (getattr(result, "text", "") or "").strip()
                if text:
                    logger.info(
                        "GEMINI_TRANSCRIPTION_SUCCESS model=%s attempt=%s",
                        model,
                        attempt,
                    )
                    return text

                last_error = RuntimeError(f"Gemini model {model} returned empty transcription")

            except Exception as e:
                last_error = e

                unsupported_model = _is_unsupported_gemini_model_error(e)
                quota_error = _is_gemini_quota_error(e)
                transient = _is_transient_gemini_error(e) and not quota_error

                logger.warning(
                    "GEMINI_TRANSCRIPTION_FAILED model=%s attempt=%s transient=%s unsupported_model=%s quota_error=%s error_type=%s error=%s",
                    model,
                    attempt,
                    transient,
                    unsupported_model,
                    quota_error,
                    type(e).__name__,
                    e,
                )

                if unsupported_model:
                    break

                if quota_error:
                    raise RuntimeError(
                        "Gemini quota/billing limit exceeded. "
                        "Проверь лимиты проекта или включи billing для Gemini API."
                    ) from e

                if not transient:
                    raise
            await asyncio.sleep(0.8 * attempt)

    raise RuntimeError(
        "Gemini временно не смог распознать голосовое после retry/fallback. "
        f"Последняя ошибка: {type(last_error).__name__}: {last_error}"
    )

async def transcribe_voice_message(update: Update, context: CTX) -> str:
    message = update.effective_message
    user = update.effective_user
    if user is None:
        raise ValueError("Нет пользователя")

    if message is None or message.voice is None:
        raise ValueError("Нет голосового сообщения")

    token = os.environ.get("GEMINI_API_KEY", "").strip()
    if not token:
        raise RuntimeError("GEMINI_API_KEY не задан")

    if genai is None or genai_types is None:
        raise RuntimeError("Пакет google-genai не установлен")

    tg_file = await context.bot.get_file(message.voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)

        with open(tmp_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        if not audio_bytes:
            raise RuntimeError("Telegram voice file пустой")

        client = genai.Client(api_key=token)

        return await _gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=audio_bytes,
            aliases_prompt=_format_known_aliases_for_voice_prompt(update.effective_user.id),
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

async def normalize_plain_text_reminder_with_gemini(text: str, created_by: int) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    token = os.environ.get("GEMINI_API_KEY", "").strip()
    if not token:
        raise RuntimeError("GEMINI_API_KEY не задан")

    if genai is None:
        raise RuntimeError("Пакет google-genai не установлен")

    models_raw = os.environ.get(
        "GEMINI_TEXT_NORMALIZE_MODELS",
        os.environ.get("GEMINI_TRANSCRIBE_MODELS", "gemini-2.5-flash-lite,gemini-2.5-flash"),
    )
    models = [m.strip() for m in models_raw.split(",") if m.strip()]
    if not models:
        models = ["gemini-2.5-flash-lite"]

    aliases_prompt = _format_known_aliases_for_voice_prompt(created_by)
    client = genai.Client(api_key=token)
    last_error: Optional[Exception] = None

    prompt = (
        "You are normalizing a Telegram text message into a reminder command.\n"
        "\n"
        "Return only one line in this exact format:\n"
        "<optional target alias> <date/time expression> - <reminder text>\n"
        "\n"
        "If the message is not a reminder request, return exactly:\n"
        "NO_REMINDER\n"
        "\n"
        "Rules:\n"
        "- Return only the normalized reminder command or NO_REMINDER. No quotes. No markdown. No commentary.\n"
        "- Preserve the reminder text meaning.\n"
        "- Remove leading phrases like 'напомни', 'напомни мне', 'поставь напоминание', 'remind me'.\n"
        "- Never change an explicitly written time. If the user says 'в 18', return '18:00'.\n"
        "- Convert Russian month names to English month names.\n"
        "- Convert Russian number words to digits in intervals: 'два часа' -> '2 часа', 'три дня' -> '3 дня'.\n"
        "- Convert fractional Russian intervals to parser-friendly recurring commands: 'каждые полчаса' -> 'every 30 minutes', 'каждые полтора часа' -> 'every 90 minutes'.\n"
        "- Do not calculate actual dates. Keep relative expressions like 'сегодня', 'завтра', 'следующий понедельник', '29 may'.\n"
        "- Support one-off reminders, recurring reminders, private target aliases, and chat aliases.\n"
        "- Use a target alias only if it appears in the known aliases list below.\n"
        "- Do not invent aliases or usernames.\n"
        "- If a person name is not in known aliases, keep it inside reminder text, not as target.\n"
        "- If the user says 'напомни мне сегодня поздравить Саню часов в 6 вечера', return 'сегодня 18:00 - поздравить Саню'.\n"
        "- If the user says 'напомни завтра в 14:55 позвонить доктору', return 'завтра 14:55 - позвонить доктору'.\n"
        "- If the user says 'каждые 3 дня пить лекарство', return 'каждые 3 дня - пить лекарство'.\n"
        "- If the user says 'напоминай каждые два часа пить воды', return 'каждые 2 часа - пить воды'.\n"
        "- If the user says 'напоминай каждые полтора часа пить воды', return 'every 90 minutes - пить воды'.\n"
        "- If the user says 'напоминай каждые полчаса пить воды', return 'every 30 minutes - пить воды'.\n"
        "- If the user says 'every 2 hours stretch', return 'every 2 hours - stretch'.\n"
        "\n"
        f"{aliases_prompt}\n"
        "\n"
        f"User message:\n{raw}\n"
    )

    for model in models:
        try:
            result = client.models.generate_content(
                model=model,
                contents=[prompt],
            )
            normalized = (getattr(result, "text", "") or "").strip()
            if normalized:
                logger.info(
                    "GEMINI_TEXT_NORMALIZE_SUCCESS model=%s normalized_kind=%s raw_len=%s normalized_len=%s",
                    model,
                    "no_reminder" if normalized == "NO_REMINDER" else "reminder",
                    len(raw),
                    len(normalized),
                )
                return normalized
            last_error = RuntimeError(f"Gemini model {model} returned empty text normalization")
        except Exception as e:
            last_error = e

            unsupported_model = _is_unsupported_gemini_model_error(e)
            quota_error = _is_gemini_quota_error(e)
            transient = _is_transient_gemini_error(e) and not quota_error

            logger.warning(
                "GEMINI_TEXT_NORMALIZE_FAILED model=%s transient=%s unsupported_model=%s quota_error=%s error_type=%s error=%s",
                model,
                transient,
                unsupported_model,
                quota_error,
                type(e).__name__,
                e,
            )

            if unsupported_model:
                continue

            if quota_error:
                raise RuntimeError(
                    "Gemini quota/billing limit exceeded. "
                    "Проверь лимиты проекта или включи billing для Gemini API."
                ) from e

            if not transient:
                raise

    raise RuntimeError(
        "Gemini временно не смог нормализовать текст после fallback. "
        f"Последняя ошибка: {type(last_error).__name__}: {last_error}"
    )


def _normalize_reminder_text_fallback(text: str) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""

    if " - " not in normalized:
        fallback_normalized = normalize_voice_reminder_text(normalized)
        if fallback_normalized:
            normalized = fallback_normalized

    normalized = normalize_gemini_reminder_command_text(normalized)

    return normalized

async def voice_remind_command(update: Update, context: CTX) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    # В группах голосовые игнорируем, чтобы бот не слушал всё подряд.
    if chat.type != Chat.PRIVATE:
        return

    try:
        heard_text = await transcribe_voice_message(update, context)
    except Exception as e:
        logger.exception(
            "VOICE_REMIND_FAILED user_id=%s chat_id=%s error_type=%s error=%s",
            user.id,
            chat.id,
            type(e).__name__,
            e,
        )
        await safe_reply(
            message,
            "Не смог распознать голосовое: сервис распознавания сейчас перегружен. "
            "Попробуй еще раз чуть позже или напиши текстом."
        )
        return

    normalized = _normalize_reminder_text_fallback(heard_text)
    if not normalized:
        await safe_reply(message, "Не услышал текст в голосовом.")
        return

    class VoiceReminderMessageProxy:
        def __init__(self, original_message, command_text: str):
            self._original_message = original_message
            self.text = command_text
            self.voice = getattr(original_message, "voice", None)

        def __getattr__(self, name):
            return getattr(self._original_message, name)

        async def reply_text(self, text, **kwargs):
            await self._original_message.reply_text(
                "Я понял:\n"
                f"{normalized}\n\n"
                f"{text}",
                **kwargs,
            )

    proxy_message = VoiceReminderMessageProxy(
        message,
        f"/remind {normalized}",
    )

    proxy_update = SimpleNamespace(
        effective_chat=chat,
        effective_message=proxy_message,
        effective_user=user,
        message=proxy_message,
    )

    await remind_command(proxy_update, context)


async def plain_text_remind_command(update: Update, context: CTX) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    # Обычный свободный текст обрабатываем только в личке.
    # В группах нельзя, иначе бот будет реагировать на обычную переписку.
    if chat.type != Chat.PRIVATE:
        return

    raw_text = (getattr(message, "text", "") or "").strip()
    if not raw_text:
        return

    if raw_text.startswith("/"):
        return

    try:
        normalized = await normalize_plain_text_reminder_with_gemini(raw_text, user.id)
    except Exception as e:
        logger.exception(
            "TEXT_REMIND_FAILED user_id=%s chat_id=%s error_type=%s error=%s raw_text=%r",
            user.id,
            chat.id,
            type(e).__name__,
            e,
            raw_text,
        )
        normalized = _normalize_reminder_text_fallback(raw_text)

    normalized = (normalized or "").strip()
    normalized = normalize_gemini_reminder_command_text(normalized)

    if normalized == "NO_REMINDER" or not normalized:
        await safe_reply(
            message,
            "Не понял, что сделать с этим сообщением.\n"
            "Если хочешь поставить напоминание, напиши, например:\n"
            "/remind завтра 18:00 - поздравить Саню\n\n"
            "Подробнее: /help"
        )
        return

    if normalized.startswith("/remind "):
        normalized = normalized[len("/remind "):].strip()

    logger.info(
        "TEXT_REMIND_NORMALIZED user_id=%s chat_id=%s raw_len=%s normalized_len=%s",
        user.id,
        chat.id,
        len(raw_text),
        len(normalized),
    )

    if " - " not in normalized:
        normalized = _normalize_reminder_text_fallback(normalized)

    if not normalized or " - " not in normalized:
        await safe_reply(
            message,
            "Не понял, что сделать с этим сообщением.\n"
            "Если хочешь поставить напоминание, напиши, например:\n"
            "/remind завтра 18:00 - поздравить Саню\n\n"
            "Подробнее: /help"
        )
        return

    class PlainTextReminderMessageProxy:
        def __init__(self, original_message, command_text: str):
            self._original_message = original_message
            self.text = command_text
            self.voice = getattr(original_message, "voice", None)

        def __getattr__(self, name):
            return getattr(self._original_message, name)

        async def reply_text(self, text, **kwargs):
            await self._original_message.reply_text(
                "Я понял:\n"
                f"{normalized}\n\n"
                f"{text}",
                **kwargs,
            )

    proxy_message = PlainTextReminderMessageProxy(
        message,
        f"/remind {normalized}",
    )

    proxy_update = SimpleNamespace(
        effective_chat=chat,
        effective_message=proxy_message,
        effective_user=user,
        message=proxy_message,
    )

    await remind_command(proxy_update, context)
def get_chat_id_by_alias_for_user(alias: str, created_by: int):
    try:
        return get_chat_id_by_alias(alias, created_by)
    except TypeError as original_error:
        try:
            return get_chat_id_by_alias(alias)
        except TypeError:
            raise original_error


def get_user_alias_chat_id_for_user(alias: str, created_by: int):
    try:
        return get_user_alias_chat_id(alias, created_by)
    except TypeError as original_error:
        try:
            return get_user_alias_chat_id(alias)
        except TypeError:
            raise original_error


def set_chat_alias_for_user(alias: str, chat_id: int, title: Optional[str], created_by: int) -> None:
    try:
        set_chat_alias(
            alias=alias,
            chat_id=chat_id,
            title=title,
            created_by=created_by,
        )
    except TypeError as original_error:
        try:
            set_chat_alias(
                alias=alias,
                chat_id=chat_id,
                title=title,
            )
        except TypeError:
            raise original_error

async def remind_command(update: Update, context: CTX) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    now = get_now()

    raw_text = message.text or ""

    logger.info(
        "REMIND input chat_id=%s chat_type=%s user_id=%s raw_text=%r",
        chat.id,
        chat.type,
        user.id,
        raw_text,
    )

    had_newline = "\n" in raw_text

    if had_newline:
        first_line, rest = raw_text.split("\n", 1)

        parts = first_line.split(maxsplit=1)
        first_line_args = parts[1] if len(parts) == 2 else ""

        # НЕ удаляем факт многострочности: bulk должен сработать даже если строка одна
        raw_args = (first_line_args + "\n" + rest).strip("\n")
    else:
        raw_args = extract_after_command(raw_text)

    if not raw_args.strip():
        await safe_reply(
            message,
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

    # В group-чате запрещаем "переключатели" в начале команды:
    # - @username
    # - alias
    # Bulk (/remind\n- ...) не трогаем.
    if not is_private:
        raw_args = raw_args.strip()

        # Запрет только для single-line: bulk оставляем как есть
        if raw_args and "\n" not in raw_args:
            parts = raw_args.split(maxsplit=1)
            if parts:
                first_token = parts[0].strip()

                # @username в начале в группе запрещаем
                if first_token.startswith("@") and len(first_token) > 1:
                    await safe_reply(
                        message,
                        "В групповом чате нельзя начинать команду с @username.\n"
                        "Напиши так: /remind 02.02 - текст @someone\n"
                        "Или в личку боту: /remind @someone 02.02 - текст",
                    )
                    return

                # alias в начале в группе запрещаем
                try:
                    alias_chat_id = get_chat_id_by_alias_for_user(first_token, user.id)
                except Exception:
                    alias_chat_id = None

                if alias_chat_id is not None:
                    await safe_reply(
                        message,
                        "В групповом чате нельзя использовать alias в начале команды.\n"
                        "Напиши боту в личку: /remind <alias> 02.02 - текст",
                    )
                    return

    target_chat_id = chat.id
    used_alias: Optional[str] = None

    # В личке допускаем slack-style "/remind me ..."
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip().lower()

            if first_token == "me":
                rest_first_line = first_line[len(first_token):].lstrip()
                rest_lines = "\n".join(raw_args.splitlines()[1:])

                parts = []
                if rest_first_line:
                    parts.append(rest_first_line)
                if rest_lines.strip():
                    parts.append(rest_lines)

                raw_args = "\n".join(parts).strip()

                logger.info(
                    "REMIND me-stripped chat_id=%s user_id=%s raw_args=%r",
                    chat.id,
                    user.id,
                    raw_args,
                )

                if not raw_args:
                    await safe_reply(
                        message,
                        "После me нужно указать дату и текст.\n"
                        "Пример: /remind me on Tuesday - алкоголь под КС"
                    )
                    return

    # В личке допускаем @username первым словом / первой строкой
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip()
            if first_token.lower() == "me":
                rest_first_line = first_line[len(first_token):].lstrip()
                rest_lines = "\n".join(raw_args.splitlines()[1:])

                parts = []
                if rest_first_line:
                    parts.append(rest_first_line)
                if rest_lines.strip():
                    parts.append(rest_lines)

                raw_args = "\n".join(parts).strip()

                if not raw_args:
                    await safe_reply(
                        message,
                        "После me нужно указать дату и текст.\n"
                        "Пример: /remind me at 18:00 - купить молоко"
                    )
                    return
            if first_token.startswith("@") and len(first_token) > 1:
                target = get_user_chat_id_by_username(first_token)
                if target is None:
                    await safe_reply(
                        message,
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
                    await safe_reply(
                        message,
                        f"После {first_token} нужно указать дату и текст.\n"
                        f"Пример: /remind {first_token} tomorrow 10:00 - привет"
                    )
                    return

                target_chat_id = target
                used_alias = first_token  # просто чтобы показать в ответе, кого выбрали

    # Если пользователь пишет "/remind напомни ...", это не alias "напомни",
    # а вложенный командный префикс. Убираем его до alias-routing.
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip() if raw_args else ""
        nested_tokens = first_line.split(maxsplit=1)
        if nested_tokens:
            nested_first = nested_tokens[0].strip(" ,.!?:;").lower()
            if nested_first in {"напомни", "напомнить", "remind"} and len(nested_tokens) == 2:
                rest_first_line = nested_tokens[1].strip()
                rest_lines = "\n".join(raw_args.splitlines()[1:])

                parts = []
                if rest_first_line:
                    parts.append(rest_first_line)
                if rest_lines.strip():
                    parts.append(rest_lines)

                raw_args = "\n".join(parts).strip()
                had_newline = "\n" in raw_args

    # В личке допускаем alias первым словом / первой строкой
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip()

            if first_token and first_token.lower() == "me":
                rest_first_line = first_line[len(first_token):].lstrip()
                rest_lines = "\n".join(raw_args.splitlines()[1:])

                parts = []
                if rest_first_line:
                    parts.append(rest_first_line)
                if rest_lines.strip():
                    parts.append(rest_lines)

                raw_args = "\n".join(parts).strip()

                if not raw_args:
                    await safe_reply(
                        message,
                        "После me нужно указать дату и текст.\n"
                        "Пример: /remind me at 18:00 - купить молоко"
                    )
                    return

            # alias != @username и alias != me (эти кейсы обработаны выше)
            elif first_token and not first_token.startswith("@"):
                # Не трогаем обычные команды, которые уже начинаются с даты/времени/recurring.
                # Важно: используем общий helper, чтобы maybe_split_alias_first_token()
                # и remind_command() не расходились по списку smart-prefixes.
                if not first_token_looks_like_reminder_start(first_token):
                    rest_first_line = first_line[len(first_token):].lstrip()
                    rest_lines = "\n".join(raw_args.splitlines()[1:])

                    parts = []
                    if rest_first_line:
                        parts.append(rest_first_line)
                    if rest_lines.strip():
                        parts.append(rest_lines)

                    raw_args_without_first_token = "\n".join(parts).strip()

                    user_alias_chat_id = get_user_alias_chat_id_for_user(first_token, user.id)
                    if user_alias_chat_id is not None:
                        raw_args = raw_args_without_first_token
                        target_chat_id = user_alias_chat_id
                        used_alias = None

                        if not raw_args:
                            await safe_reply(
                                message,
                                "После alias нужно указать дату и текст.\n"
                                f"Пример:\n/remind {first_token} 28.11 12:00 - завтра футбол"
                            )
                            return
                    else:
                        alias_chat_id = get_chat_id_by_alias_for_user(first_token, user.id)
                        if alias_chat_id is not None:
                            raw_args = raw_args_without_first_token
                            target_chat_id = alias_chat_id
                            used_alias = first_token

                            if not raw_args:
                                await safe_reply(
                                    message,
                                    "После alias нужно указать дату и текст.\n"
                                    "Пример:\n"
                                    f"/remind {used_alias} 28.11 12:00 - завтра футбол"
                                )
                                return
                        elif raw_args_without_first_token and "\n" not in raw_args:
                            try:
                                parse_date_time_smart(raw_args_without_first_token, now)
                            except Exception:
                                pass
                            else:
                                await safe_reply(
                                    message,
                                    f'Алиаса "{first_token}" не существует. '
                                    "Используй команду без него, если хочешь поставить ремайндер себе, "
                                    f'или присвой "{first_token}" тому, кому нужно, с помощью команд /linkuser или /linkchat. '
                                    "Подробнее о них можешь прочитать в /help."
                                )
                                return

    # если человек пишет боту в личке - запомним его chat_id
    if is_private:
        upsert_user_chat(
            user_id=user.id,
            chat_id=chat.id,
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
        )

    logger.info(
        "REMIND normalized chat_id=%s target_chat_id=%s used_alias=%s raw_args=%r had_newline=%s",
        chat.id,
        target_chat_id,
        used_alias,
        raw_args,
        had_newline,
    )

    # Bulk или одиночный?
    if had_newline:
        raw_lines = [ln.strip() for ln in raw_args.splitlines() if ln.strip()]

        # Поддержка bulk без "- ":
        # - если первая строка не похожа на напоминание и есть другие строки,
        #   считаем ее "заголовком" и пропускаем (пример: "Каталония")
        lines = []
        if raw_lines:
            first = raw_lines[0].lstrip("-").strip()

            if len(raw_lines) > 1:
                # Заголовок пропускаем ТОЛЬКО если первая строка явно не похожа на напоминание.
                # Важно: НЕ дергаем parse_date_time_smart здесь, чтобы не было двойного парсинга
                # (и чтобы тесты с monkeypatch на parse_date_time_smart не ловили лишние вызовы).
                is_reminder_like = False

                if looks_like_recurring(first):
                    is_reminder_like = True
                else:
                    # Heuristic: строка похожа на одноразовое напоминание, если начинается с "даты/времени"
                    # или с month-name формата ("On March 1 ...", "March 1 ..."), или с relative ("in 2 hours ...").
                    if re.match(
                        r"^(?:"
                        r"(?:on\s+)?\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?(?:\s+\d{1,2}[:.]\d{2})?"
                        r"|"
                        r"\d{1,2}[:.]\d{2}"
                        r"|"
                        r"(?:today|tomorrow|day\s+after\s+tomorrow|сегодня|завтра|послезавтра)(?:\s+\d{1,2}[:.]\d{2})?"
                        r"|"
                        r"(?:in|через)\s+\d+\s+\w+"
                        r"|"
                        r"(?:on\s+)?[A-Za-z]{3,9}\s+\d{1,2}(?:\s+\d{4})?(?:\s+\d{1,2}[:.]\d{2})?"
                        r")\b",
                        first,
                        flags=re.IGNORECASE,
                    ):
                        is_reminder_like = True

                if not is_reminder_like:
                    raw_lines = raw_lines[1:]

            for ln in raw_lines:
                ln2 = ln
                if ln2.startswith("-"):
                    ln2 = ln2[1:].lstrip()
                lines.append(ln2)

        created = 0
        failed = 0
        error_lines: List[tuple[int, str, str]] = []

        for idx, line in enumerate(lines, start=1):
            original_line = line

            if line.startswith("-"):
                line = line[1:].lstrip()

            try:
                _create_single_reminder_from_line(
                    line=line,
                    now=now,
                    target_chat_id=target_chat_id,
                    user=user,
                )
                created += 1
            except Exception as e:
                failed += 1
                error_lines.append((idx, original_line, str(e)))

        reply = _format_bulk_result(
            created=created,
            failed=failed,
            error_lines=error_lines,
        )

        await safe_reply(message, reply)
        return

    # Одиночная строка
    raw_single = raw_args.strip()

    # Сначала пробуем как recurring
    if looks_like_recurring(raw_single):
        try:
            first_dt, text, pattern_type, payload, hour, minute = parse_recurring(raw_single, now)
        except ValueError as e:
            await safe_reply(message,f"Не смог понять повторяющийся формат: {e}")
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
            await safe_reply(
                message,
                f"Ок, создал повторяющееся напоминание в чате '{used_alias}'.\n"
                f"Первое напоминание будет {when_str}: {text}"
                f"{freq_part}"
            )
        else:
            await safe_reply(
                message,
                f"Ок, создал повторяющееся напоминание.\n"
                f"Первое напоминание будет {when_str}: {text}"
                f"{freq_part}"
            )
        return

    # Обычное разовое напоминание
    try:
        remind_at, text = parse_date_time_smart(raw_single, now)
    except ValueError as e:
        original_error = e
        normalized_single = None

        try:
            created_by = user.id if user else None
            gemini_result = await normalize_plain_text_reminder_with_gemini(raw_single, created_by)
            if gemini_result and gemini_result.strip().upper() != "NO_REMINDER":
                normalized_single = gemini_result.strip()

                if normalized_single.startswith("/remind"):
                    normalized_single = normalized_single[len("/remind"):].strip()

                normalized_single = normalize_gemini_reminder_command_text(normalized_single)
                normalized_single = _normalize_reminder_text_fallback(normalized_single)

                if normalized_single.startswith("/remind"):
                    normalized_single = normalized_single[len("/remind"):].strip()

                remind_at, text = parse_date_time_smart(normalized_single, now)
            else:
                raise original_error
        except Exception as fallback_error:
            logging.info(
                "REMIND parse failed user=%s chat=%s raw=%r normalized=%r error=%s fallback_error=%s",
                getattr(user, "id", None),
                chat.id,
                raw_single,
                normalized_single,
                original_error,
                fallback_error,
            )
            await safe_reply(message, f"Не смог понять дату и текст: {original_error}")
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
        await safe_reply(
            message,
            f"Ок, напомню в чате '{used_alias}' {when_str}: {text}"
        )
    else:
        if target_chat_id != chat.id and chat.type == Chat.PRIVATE:
            await safe_reply(
                message,
                f"Ок, напомню этому человеку {when_str}: {text}"
            )
        else:
            await safe_reply(
                message,
                f"Ок, напомню {when_str}: {text}"
            )

async def linkuser_command(update: Update, context: CTX) -> None:
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    if len(context.args or []) != 2:
        await safe_reply(
            message,
            "Формат:\n/linkuser alias @username\n\nПример:\n/linkuser misha @friend"
        )
        return

    alias = context.args[0].strip()
    username = context.args[1].strip()

    if not alias:
        await safe_reply(message, "Alias не может быть пустым.")
        return

    if alias.startswith("@"):
        await safe_reply(message, "Alias не должен начинаться с @. Напиши, например: /linkuser misha @friend")
        return

    if not username.startswith("@") or len(username) <= 1:
        await safe_reply(message, "Вторым аргументом нужен @username. Пример: /linkuser misha @friend")
        return

    if get_chat_id_by_alias(alias, user.id) is not None:
        await safe_reply(message, f"Alias '{alias}' уже занят chat-alias. Выбери другое имя.")
        return

    target_chat_id = get_user_chat_id_by_username(username)
    if target_chat_id is None:
        await safe_reply(
            message,
            f"Я пока не могу написать {username}, потому что он/она не нажимал(а) Start у бота."
        )
        return

    set_user_alias(
        alias=alias,
        user_id=int(target_chat_id),
        chat_id=int(target_chat_id),
        username=username.lstrip("@"),
        created_by=user.id,
    )

    await safe_reply(message, f"Ок, alias '{alias}' теперь указывает на {username}.")

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
                await safe_reply(
                    message,
                    f"Пользователь {first_arg} еще не писал боту.\n"
                    f"Он должен сначала нажать Start или поставить любой ремайндер."
                )
                return

            rows = get_active_reminders_created_by_for_chat(
                chat_id=owner_chat_id,
                created_by=user.id,
            )

            if not rows:
                await safe_reply(
                    message,
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

            await safe_reply(message,reply, reply_markup=InlineKeyboardMarkup(buttons))
            return

    # ===== /list alias: сначала user-alias, потом chat-alias =====
    if chat.type == Chat.PRIVATE and context.args:
        alias = context.args[0].strip()
        if alias:
            user_alias_chat_id = get_user_alias_chat_id_for_user(alias, user.id)
            if user_alias_chat_id is not None:
                target_chat_id = user_alias_chat_id
                used_alias = alias
            else:
                alias_chat_id = get_chat_id_by_alias_for_user(alias, user.id)
                if alias_chat_id is None:
                    aliases = get_all_aliases(user.id)
                    if not aliases:
                        await safe_reply(
                            message,
                            f"Alias '{alias}' не найден.\n"
                            f"Сначала зайди в нужный чат и выполни /linkchat название.\n"
                            f"Или создай user-alias: /linkuser {alias} @username"
                        )
                    else:
                        known = ", ".join(a for a, _, _ in aliases)
                        await safe_reply(
                            message,
                            f"Alias '{alias}' не найден.\n"
                            f"Из известных chat-alias: {known}"
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
            await safe_reply(message,f"В чате '{used_alias}' напоминаний нет.")
        else:
            await safe_reply(message,"Напоминаний нет.")
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
    await safe_reply(message,reply, reply_markup=keyboard)

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

    rid = int(ids[idx - 1])

    target_chat_id = context.user_data.get("list_chat_id")
    if target_chat_id is None:
        chat = query.message.chat if query.message else None
        if chat is None:
            return
        target_chat_id = chat.id

    r = get_reminder_row(rid)
    if not r:
        await query.answer("Уже удалено", show_alert=True)
        return

    # Если recurring - спрашиваем режим удаления
    tpl_id = r.get("template_id")
    if tpl_id is not None:
        tpl = get_recurring_template_row(int(tpl_id)) or {}
        tpl_pattern_type = tpl.get("pattern_type")
        tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}
        human = format_recurring_human(tpl_pattern_type, tpl_payload)

        dt = datetime.fromisoformat(str(r["remind_at"]))
        ts = dt.strftime("%d.%m %H:%M")
        title = str(r.get("text") or "")
        suffix = f"  🔁 {human}" if human else "  🔁"
        preview = f"{ts} - {title}{suffix}"

        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🗑 Удалить только ближайший", callback_data=f"del_one:{rid}")],
                [InlineKeyboardButton("🧨 Удалить всю серию", callback_data=f"del_series:{int(tpl_id)}")],
            ]
        )

        if query.message:
            await query.message.reply_text(
                "Это повторяющееся напоминание. Как удалить?\n\n" + preview,
                reply_markup=kb,
            )
        return

    # НЕ recurring - удаляем сразу + undo
    snapshot = delete_single_reminder_with_snapshot(rid, int(target_chat_id))
    if not snapshot:
        await query.answer("Уже удалено", show_alert=True)
        return

    ids.pop(idx - 1)
    context.user_data["list_ids"] = ids

    if not ids:
        if query.message:
            await query.edit_message_text("Напоминаний больше нет.")
    else:
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

        if query.message:
            await query.edit_message_text(reply, reply_markup=InlineKeyboardMarkup(buttons))

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


async def delete_choose_callback(update: Update, context: CTX) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    if not (data.startswith("del_one:") or data.startswith("del_series:")):
        return

    # Чат, для которого показывается список (может быть НЕ равен query.message.chat.id в личке)
    target_chat_id = context.user_data.get("list_chat_id")
    if target_chat_id is None:
        chat = query.message.chat if query.message else None
        if chat is None:
            return
        target_chat_id = chat.id

    ids: List[int] = context.user_data.get("list_ids") or []

    snapshot: Optional[Dict[str, Any]] = None
    deleted_label = ""

    if data.startswith("del_one:"):
        try:
            rid = int(data.split(":", 1)[1])
        except ValueError:
            return

        # ВАЖНО: для recurring "удалить ближайший" = удалить инстанс + пересоздать следующий
        snapshot = delete_recurring_one_instance_and_reschedule(rid, int(target_chat_id))
        if not snapshot:
            await query.answer("Не смог удалить", show_alert=True)
            return

        # убираем rid из текущего списка (если он там есть)
        ids = [x for x in ids if int(x) != int(rid)]
        context.user_data["list_ids"] = ids

        deleted_label = "Удалил ближайший из серии"

    elif data.startswith("del_series:"):
        try:
            tpl_id = int(data.split(":", 1)[1])
        except ValueError:
            return

        snapshot = delete_recurring_series_with_snapshot(tpl_id, int(target_chat_id))
        if not snapshot:
            await query.answer("Не смог удалить серию", show_alert=True)
            return

        removed_ids = {int(r["id"]) for r in (snapshot.get("reminders") or []) if r.get("id") is not None}
        ids = [x for x in ids if int(x) not in removed_ids]
        context.user_data["list_ids"] = ids

        deleted_label = "Удалил всю серию"

    # Обновляем сообщение со списком (если там еще что-то осталось)
    if not ids:
        if query.message:
            await query.edit_message_text("Напоминаний больше нет.")
    else:
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

        if query.message:
            await query.edit_message_text(reply, reply_markup=InlineKeyboardMarkup(buttons))

    if not snapshot:
        return

    # Сообщение "удалено" + Undo
    tpl = (snapshot or {}).get("template") or {}
    tpl_pattern_type = tpl.get("pattern_type")
    tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}

    if snapshot.get("kind") == "series":
        reminders = snapshot.get("reminders") or []
        if reminders:
            deleted_text = format_deleted_human(
                reminders[0]["remind_at"],
                tpl.get("text") or reminders[0].get("text") or "",
                tpl_pattern_type,
                tpl_payload,
            )
        else:
            deleted_text = str(tpl.get("text") or "серия")
            human = format_recurring_human(tpl_pattern_type, tpl_payload)
            if human:
                deleted_text = f"{deleted_text}  🔁 {human}"
        btn_text = "↩️ Вернуть серию"
    else:
        deleted_text = format_deleted_human(
            snapshot["reminder"]["remind_at"],
            snapshot["reminder"]["text"],
            tpl_pattern_type,
            tpl_payload,
        )
        btn_text = "↩️ Вернуть ближайший"

    token = make_undo_token()
    context.user_data["undo_tokens"] = context.user_data.get("undo_tokens") or {}
    context.user_data["undo_tokens"][token] = snapshot

    undo_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(btn_text, callback_data=f"undo:{token}")]]
    )

    if query.message:
        await query.message.reply_text(f"{deleted_label}: {deleted_text}", reply_markup=undo_kb)

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

    restored = restore_deleted_snapshot(snapshot)
    if not restored:
        await query.answer("Не смог восстановить", show_alert=True)
        return

    tpl = snapshot.get("template") or {}
    tpl_pattern_type = tpl.get("pattern_type")
    tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}

    if snapshot.get("kind") == "series":
        # restored = List[int]
        human = format_recurring_human(tpl_pattern_type, tpl_payload)
        series_text = str(tpl.get("text") or "серия")
        suffix = f"  🔁 {human}" if human else "  🔁"
        count = len(restored) if isinstance(restored, list) else 0

        if query.message:
            await query.message.reply_text(
                f"Вернул серию: {series_text}{suffix} (инстансов: {count})"
            )
        return

    # single
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
        if (
            data.startswith("snooze_pastdate:")
            or data.startswith("selfremind_pastdate:")
            or data.startswith("selfremind_event_pastdate:")
        ):
            await query.answer("Эта дата уже прошла. Выбери другую.", show_alert=True)
            return

        if data.startswith("selfremind:ask:"):
            _, _, rid_str = data.split(":", 2)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer("Не удалось определить пользователя", show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)

            await context.bot.send_message(
                chat_id=target_chat_id,
                text=f'Как тебе напомнить о "{src.text}" из чата "{source_chat_title}"?',
                reply_markup=build_self_remind_mode_keyboard(rid),
            )
            await query.answer("Отправил варианты в личку")
            return

        if data.startswith("selfremind:cancel_personal:"):
            _, _, rid_str = data.split(":", 2)

            try:
                int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            if query.message:
                await query.edit_message_text("Ок, личное напоминание не создаю.")

            await query.answer("Ок")
            return

        if data.startswith("selfremind:back:"):
            _, _, rid_str = data.split(":", 2)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)

            await query.edit_message_text(
                f'Как тебе напомнить о "{src.text}" из чата "{source_chat_title}"?',
                reply_markup=build_self_remind_mode_keyboard(rid),
            )
            await query.answer("Вернул выбор")
            return

        if data.startswith("selfremind:mode:"):
            _, _, rid_str, mode = data.split(":", 3)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer("Не удалось определить пользователя", show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            if mode == "regular":
                source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)
                await query.edit_message_text(
                    f'Когда напомнить тебе о "{src.text}" из чата "{source_chat_title}"?',
                    reply_markup=build_self_remind_choice_keyboard(rid),
                )
                await query.answer("Выбери время")
                return

            if mode == "event":
                base_now = get_self_remind_event_base(src)
                event_at = extract_event_datetime_from_text(src.text, base_now)

                if event_at is None:
                    await query.edit_message_text(
                        "Я не смог понять дату события из текста.\n"
                        "Ты можешь поставить себе обычный ремайндер:",
                        reply_markup=build_self_remind_choice_keyboard(rid),
                    )
                    await query.answer("Не смог понять дату события")
                    return

                event_str = event_at.strftime("%d.%m %H:%M")
                await query.edit_message_text(
                    f"Я понял, что событие из напоминания состоится {event_str}.\n"
                    "За сколько до этого времени напомнить?",
                    reply_markup=build_self_remind_event_before_keyboard(rid),
                )
                await query.answer("Выбери время")
                return

            await query.answer("Неизвестный режим", show_alert=True)
            return

        if data.startswith("selfremind:event_custom:"):
            _, _, rid_str = data.split(":", 2)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            kb = build_custom_date_keyboard(rid, callback_prefix="selfremind_event")
            await query.edit_message_reply_markup(reply_markup=kb)
            await query.answer("Выбери дату")
            return

        if data.startswith("selfremind:event_before:"):
            _, _, rid_str, option = data.split(":", 3)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer("Не удалось определить пользователя", show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            base_now = get_self_remind_event_base(src)
            event_at = extract_event_datetime_from_text(src.text, base_now)
            if event_at is None:
                await query.answer("Я не смог понять дату события из текста", show_alert=True)
                return

            remind_at = compute_event_before_time(option, event_at)
            if remind_at is None:
                await query.answer("Неизвестный вариант времени", show_alert=True)
                return

            if remind_at <= get_now():
                await query.answer("Это время уже прошло. Выбери другое время.", show_alert=True)
                return

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)
            normalized_src_text = normalize_relative_event_date_in_text(src.text, event_at)
            personal_text = format_self_remind_text(source_chat_title, normalized_src_text)

            add_reminder(
                chat_id=target_chat_id,
                text=personal_text,
                remind_at=remind_at,
                created_by=user_id,
            )

            when_str = remind_at.strftime("%d.%m %H:%M")
            await query.edit_message_text(f"Ок, напомню {when_str}: {personal_text}")
            await query.answer("Личное напоминание создано")
            return

        if data.startswith("selfremind:set:"):
            _, _, rid_str, option = data.split(":", 3)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer("Не удалось определить пользователя", show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            if option == "custom":
                kb = build_custom_date_keyboard(rid, callback_prefix="selfremind")
                await query.edit_message_reply_markup(reply_markup=kb)
                await query.answer("Выбери дату")
                return

            remind_at = compute_self_remind_time(option, get_now())

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)
            personal_text = format_self_remind_text(source_chat_title, src.text)

            add_reminder(
                chat_id=target_chat_id,
                text=personal_text,
                remind_at=remind_at,
                created_by=user_id,
                template_id=None,
            )

            when_str = remind_at.strftime("%d.%m %H:%M")
            await query.edit_message_text(f"Ок, напомню {when_str}: {personal_text}")
            await query.answer("Личное напоминание создано")
            return

        if data.startswith("selfremind_cal:") or data.startswith("selfremind_event_cal:"):
            _, rid_str, ym = data.split(":", 2)
            rid = int(rid_str)

            year_str, month_str = ym.split("-", 1)
            year = int(year_str)
            month = int(month_str)

            callback_prefix = "selfremind_event" if data.startswith("selfremind_event_") else "selfremind"
            kb = build_custom_date_keyboard(rid, year=year, month=month, callback_prefix=callback_prefix)
            await query.edit_message_reply_markup(reply_markup=kb)
            await query.answer()
            return

        if data.startswith("selfremind_caltoday:") or data.startswith("selfremind_event_caltoday:"):
            _, rid_str = data.split(":", 1)
            rid = int(rid_str)

            today = datetime.now(TZ).date()
            callback_prefix = "selfremind_event" if data.startswith("selfremind_event_") else "selfremind"
            kb = build_custom_date_keyboard(
                rid,
                year=today.year,
                month=today.month,
                callback_prefix=callback_prefix,
            )

            try:
                await query.edit_message_reply_markup(reply_markup=kb)
            except Exception:
                pass

            await query.answer()
            return

        if data.startswith("selfremind_pickdate:") or data.startswith("selfremind_event_pickdate:"):
            _, rid_str, date_str = data.split(":", 2)
            rid = int(rid_str)

            callback_prefix = "selfremind_event" if data.startswith("selfremind_event_") else "selfremind"
            kb = build_custom_time_keyboard(rid, date_str, callback_prefix=callback_prefix)
            await query.edit_message_reply_markup(reply_markup=kb)
            await query.answer("Выбери время")
            return

        if data.startswith("selfremind_picktime:") or data.startswith("selfremind_event_picktime:"):
            _, rid_str, date_str, time_str = data.split(":", 3)
            rid = int(rid_str)

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer("Не удалось определить пользователя", show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            try:
                year, month, day = map(int, date_str.split("-"))
                hour, minute = map(int, time_str.split(":"))
                remind_at = datetime(year, month, day, hour, minute, tzinfo=TZ)
            except Exception:
                await query.answer("Не смог понять дату/время", show_alert=True)
                return

            if remind_at <= get_now():
                await query.answer("Это время уже прошло. Выбери другое время.", show_alert=True)
                return

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)
            personal_text = format_self_remind_text(source_chat_title, src.text)

            add_reminder(
                chat_id=target_chat_id,
                text=personal_text,
                remind_at=remind_at,
                created_by=user_id,
                template_id=None,
            )

            when_str = remind_at.strftime("%d.%m %H:%M")
            await query.edit_message_text(f"Ок, напомню {when_str}: {personal_text}")
            await query.answer("Личное напоминание создано")
            return

        if data.startswith("selfremind_event_cancel:"):
            _, rid_str = data.split(":", 1)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            base_now = get_self_remind_event_base(src)
            event_at = extract_event_datetime_from_text(src.text, base_now)

            if event_at is None:
                await query.edit_message_text(
                    "Я не смог понять дату события из текста.\n"
                    "Ты можешь поставить себе обычный ремайндер:",
                    reply_markup=build_self_remind_choice_keyboard(rid),
                )
                await query.answer("Вернул варианты")
                return

            event_str = event_at.strftime("%d.%m %H:%M")
            await query.edit_message_text(
                f"Я понял, что событие из напоминания состоится {event_str}.\n"
                "За сколько до этого времени напомнить?",
                reply_markup=build_self_remind_event_before_keyboard(rid),
            )
            await query.answer("Вернул варианты до события")
            return

        if data.startswith("selfremind_cancel:"):
            _, rid_str = data.split(":", 1)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer("Некорректный reminder id", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer("Исходное напоминание не найдено", show_alert=True)
                return

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)

            await query.edit_message_text(
                f'Когда напомнить тебе о "{src.text}" из чата "{source_chat_title}"?'
            )

            await query.edit_message_reply_markup(
                reply_markup=build_self_remind_choice_keyboard(rid)
            )

            await query.answer("Вернул варианты")
            return

        # mark complete
        if data.startswith("done:"):
            _, rid_str = data.split(":", 1)
            try:
                rid = int(rid_str)
            except ValueError:
                # даже если вдруг id не распарсился, просто пометим сообщение завершенным
                rid = None

            if rid is not None:
                mark_reminder_acked(rid)
                await clear_reminder_message_keyboards(context.bot, rid)

            # исходный текст сообщения
            original_text = query.message.text if query.message and query.message.text else ""

            # если есть оригинальный текст ремайндерa в БД - можно взять его
            if rid is not None:
                r = get_reminder(rid)
            else:
                r = None

            base_text = r.text if r else original_text or "Напоминание"
            new_text = f"{base_text} (завершено ✅)"

            # Пытаемся обновить сообщение, но в тестах этих методов может не быть
            if hasattr(query, "edit_message_text"):
                try:
                    await query.edit_message_text(new_text)
                except Exception:
                    pass

            if hasattr(query, "edit_message_reply_markup"):
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass

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
                # ACK на вход в кастомный flow тоже считаем реакцией
                mark_reminder_acked(rid)

                kb = build_custom_date_keyboard(rid)
                await query.edit_message_reply_markup(reply_markup=kb)
                await query.answer("Выбери дату", show_alert=False)
                return
            else:
                await query.answer("Неизвестное действие", show_alert=True)
                return

            # УСПЕШНЫЙ snooze = реакция пользователя
            mark_reminder_acked(rid)
            await clear_reminder_message_keyboards(context.bot, rid)

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

        if data.startswith("snooze_cal:"):
            _, rid_str, ym = data.split(":", 2)
            rid = int(rid_str)

            year_str, month_str = ym.split("-", 1)
            year = int(year_str)
            month = int(month_str)

            kb = build_custom_date_keyboard(rid, year=year, month=month)
            await query.edit_message_reply_markup(reply_markup=kb)
            await query.answer()
            return

        if data.startswith("snooze_caltoday:"):
            _, rid_str = data.split(":", 1)
            rid = int(rid_str)

            today = datetime.now(TZ).date()
            kb = build_custom_date_keyboard(rid, year=today.year, month=today.month)

            try:
                await query.edit_message_reply_markup(reply_markup=kb)
            except Exception:
                pass

            await query.answer()
            return

        if data.startswith("snooze_pickdate:"):
            _, rid_str, date_str = data.split(":", 2)
            rid = int(rid_str)

            # выбор даты - реакция
            mark_reminder_acked(rid)

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

            if new_dt <= get_now():
                await query.answer("Это время уже прошло. Выбери другое время.", show_alert=True)
                return

            # успешный picktime - реакция
            mark_reminder_acked(rid)
            await clear_reminder_message_keyboards(context.bot, rid)

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
            _, rid_str = data.split(":", 1)
            try:
                rid = int(rid_str)
            except ValueError:
                rid = None

            if rid is not None:
                mark_reminder_acked(rid)

                await query.edit_message_reply_markup(
                    reply_markup=build_snooze_keyboard(rid)
                )
                await query.answer("Вернул варианты")
                return

            await query.answer("Некорректный reminder id", show_alert=True)
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

async def _safe_get_chat_type(app: Application, chat_id: int) -> Optional[str]:
    try:
        chat = await app.bot.get_chat(chat_id)
        return getattr(chat, "type", None)
    except Exception:
        return None

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
                    chat_type = await _safe_get_chat_type(app, r.chat_id)

                    chat_type_value = getattr(chat_type, "value", chat_type)
                    chat_type_value = str(chat_type_value).lower() if chat_type_value is not None else None

                    reply_markup = (
                        build_group_reminder_keyboard(r.id)
                        if chat_type_value in {"group", "supergroup", "channel"}
                        else build_snooze_keyboard(r.id)
                    )

                    sent_message = await app.bot.send_message(
                        chat_id=r.chat_id,
                        text=r.text,
                        reply_markup=reply_markup,
                    )

                    sent_message_id = getattr(sent_message, "message_id", None)
                    if sent_message_id is not None:
                        register_reminder_message(
                            reminder_id=r.id,
                            chat_id=r.chat_id,
                            message_id=sent_message_id,
                            kind="delivery",
                        )

                    mark_reminder_sent(r.id, sent_at=now)

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
                    logger.exception(
                        "Ошибка при отправке напоминания id=%s",
                        r.id,
                    )

        except Exception:
            logger.exception("Ошибка в worker напоминаний")

        await asyncio.sleep(10)

async def reminders_nudge_worker(app: Application) -> None:
    logger.info("Запущен фоновой nudge worker напоминаний")
    while True:
        try:
            now = get_now()

            rows = get_due_nudges(now)
            for r in rows:
                try:
                    # строго: nudges только в личке
                    chat_type = await _safe_get_chat_type(app, r["chat_id"])

                    if chat_type != Chat.PRIVATE:
                        continue

                    text = (
                        "Ты никак не отреагировал на напоминание.\n"
                        "Посмотри и нажми кнопку:\n\n"
                        f"{r['text']}"
                    )

                    reply_markup = build_snooze_keyboard(r["id"])

                    sent_message = await app.bot.send_message(
                        chat_id=r["chat_id"],
                        text=text,
                        reply_markup=reply_markup,
                    )

                    sent_message_id = getattr(sent_message, "message_id", None)
                    if sent_message_id is not None:
                        register_reminder_message(
                            reminder_id=int(r["id"]),
                            chat_id=int(r["chat_id"]),
                            message_id=sent_message_id,
                            kind="nudge",
                        )

                    increment_nudge_count(r["id"])
                except Exception:
                    logger.exception("Ошибка при отправке nudge reminder id=%s", r["id"])
        except Exception:
            logger.exception("Ошибка в nudge worker")

        await asyncio.sleep(30)

BACKGROUND_WORKER_TASK_KEYS = (
    "reminders_worker_task",
    "reminders_nudge_worker_task",
)


def _start_background_worker(application: Application, task_key: str, coro_factory) -> asyncio.Task:
    existing_task = application.bot_data.get(task_key)
    if existing_task is not None and not existing_task.done():
        return existing_task

    task = asyncio.create_task(coro_factory())
    application.bot_data[task_key] = task
    return task


async def _cancel_background_worker(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def post_init(application: Application) -> None:
    init_db()
    migrate_alias_tables_to_owner_scope()

    _start_background_worker(
        application,
        "reminders_worker_task",
        lambda: reminders_worker(application),
    )
    _start_background_worker(
        application,
        "reminders_nudge_worker_task",
        lambda: reminders_nudge_worker(application),
    )

    logger.info("Фоновые worker напоминаний запущены из post_init")


async def post_shutdown(application: Application) -> None:
    for task_key in BACKGROUND_WORKER_TASK_KEYS:
        task = application.bot_data.pop(task_key, None)
        if task is not None:
            await _cancel_background_worker(task)

    logger.info("Фоновые worker напоминаний остановлены из post_shutdown")

def _nudge_threshold_minutes(nudge_count: int) -> Optional[int]:
    # кумулятивно от sent_at:
    # 1) +20m
    # 2) +20m +60m = 80m
    # 3) +80m +240m = 320m
    # 4) +320m +720m = 1040m
    thresholds = [20, 80, 320, 1040]
    if 0 <= nudge_count < len(thresholds):
        return thresholds[nudge_count]
    return None


def get_due_nudges(now: datetime) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, chat_id, text, sent_at, nudge_count
            FROM reminders
            WHERE delivered = 1
              AND acked = 0
              AND nudge_count < 4
              AND sent_at IS NOT NULL
            """,
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                sent_at = datetime.fromisoformat(r["sent_at"])
            except Exception:
                continue

            threshold = _nudge_threshold_minutes(int(r["nudge_count"]))
            if threshold is None:
                continue

            if now >= sent_at + timedelta(minutes=threshold):
                out.append(dict(r))
        return out
    finally:
        conn.close()


def increment_nudge_count(reminder_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "UPDATE reminders SET nudge_count = nudge_count + 1 WHERE id = ?",
            (reminder_id,),
        )
        conn.commit()
    finally:
        conn.close()


def exhaust_nudges(reminder_id: int) -> None:
    # чтобы никогда не пытаться нуджить в group/channel
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "UPDATE reminders SET nudge_count = 4 WHERE id = ?",
            (reminder_id,),
        )
        conn.commit()
    finally:
        conn.close()


# ===== main =====

def build_snooze_callback_pattern() -> str:
    return (
        r"^(selfremind:ask:|selfremind:back:|selfremind:cancel_personal:|selfremind:set:|selfremind:mode:|selfremind:event_before:"
        r"|selfremind:event_custom:|selfremind_cal:|selfremind_caltoday:|selfremind_pastdate:"
        r"|selfremind_pickdate:|selfremind_picktime:|selfremind_cancel:|selfremind_event_cal:"
        r"|selfremind_event_caltoday:|selfremind_event_pastdate:|selfremind_event_pickdate:"
        r"|selfremind_event_picktime:|selfremind_event_cancel:"
        r"|snooze:|snooze_cal:|snooze_caltoday:|snooze_pastdate:|snooze_pickdate:"
        r"|snooze_picktime:|snooze_cancel:|noop|done:)"
    )


def main() -> None:
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("Не задан BOT_TOKEN")

    application = (
        Application.builder()
        .token(bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("linkchat", linkchat_command))
    application.add_handler(CommandHandler("linkuser", linkuser_command))
    application.add_handler(CommandHandler("aliases", aliases_command))
    application.add_handler(CommandHandler("unalias", unalias_command))
    application.add_handler(CommandHandler("renamealias", renamealias_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(MessageHandler(filters.VOICE, voice_remind_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_remind_command))
    application.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del:\d+$"))
    application.add_handler(CallbackQueryHandler(delete_choose_callback, pattern=r"^del_(one|series):"))
    application.add_handler(CallbackQueryHandler(undo_callback, pattern=r"^undo:"))
    application.add_handler(
        CallbackQueryHandler(
            snooze_callback,
            pattern=build_snooze_callback_pattern(),
        )
    )

    logger.info("Запускаем бота polling...")
    application.run_polling()


if __name__ == "__main__":
    main()