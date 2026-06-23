import asyncio
import logging
import os
import re
import sqlite3
import json
import secrets
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None
from datetime import datetime, timedelta, date
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING
from types import SimpleNamespace
from zoneinfo import ZoneInfo

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

SYSTEM_DEFAULT_REMINDER_HOUR = 10
SYSTEM_DEFAULT_REMINDER_MINUTE = 0

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

from callback_contracts import (
    CREATED_COMPLETE_PATTERN,
    CREATED_DELETE_PATTERN,
    CREATED_SNOOZE_CUSTOM_PATTERN,
    CREATED_SNOOZE_PATTERN,
    DELETE_CHOICE_PATTERN,
    DONE_PATTERN,
    NOOP_PATTERN,
    SELFREMIND_EVENT_CUSTOM_PATTERN,
    SELFREMIND_PATTERN,
    SNOOZE_CALENDAR_PATTERN,
    SNOOZE_CUSTOM_PATTERN,
    SNOOZE_PATTERN,
    UNDO_PATTERN,
    cb_created_complete,
    cb_created_delete,
    cb_created_snooze,
    cb_created_snooze_custom,
    cb_del,
    cb_del_cancel,
    cb_del_one,
    cb_del_series,
    cb_done,
    cb_selfremind_ask,
    cb_selfremind_back,
    cb_selfremind_cancel_personal,
    cb_selfremind_event_before,
    cb_selfremind_event_custom,
    cb_selfremind_mode,
    cb_selfremind_set,
    cb_snooze,
    cb_snooze_custom,
    cb_undo,
)

import keyboards as keyboard_builders
from presentation import (
    build_active_reminders_list_response,
    build_target_user_presentation_rows,
    build_target_user_reminders_list_response,
    format_completed_reminder_text,
    format_created_reminder_text,
    format_created_recurring_reminder_text,
    format_empty_active_reminders_list_text,
    format_deleted_human,
    format_deleted_snapshot_text,
    format_recurring_human,
    format_restored_series_text,
    format_restored_single_text,
    format_snoozed_answer_text,
    format_snoozed_reminder_text,
)

def get_now() -> datetime:
    return datetime.now(TZ)


# ===== User-facing messages =====
from messages import (
    MSG_DELETE_FAILED_SHORT,
    MSG_DELETE_FAILED_TEXT,
    MSG_DELETE_SERIES_FAILED,
    MSG_EVENT_DATE_NOT_FOUND,
    MSG_GROUP_ALIAS_PREFIX_FORBIDDEN,
    MSG_GROUP_USERNAME_PREFIX_FORBIDDEN,
    MSG_INVALID_REMINDER_ID,
    MSG_NOT_UNDERSTOOD_PLAIN_TEXT,
    MSG_PARSE_DATE_TEXT_FAILED,
    MSG_REMINDER_ALREADY_DELETED_ALERT,
    MSG_REMINDER_ALREADY_DELETED_TEXT,
    MSG_REMINDER_NOT_FOUND,
    MSG_REMIND_USAGE,
    MSG_RESCHEDULE_BAD_DATETIME,
    MSG_RESCHEDULE_OPEN_FAILED_TEXT,
    MSG_RESCHEDULE_PAST_TIME,
    MSG_RESCHEDULE_UNKNOWN_ACTION,
    MSG_SOURCE_REMINDER_NOT_FOUND,
    MSG_UNDO_EXPIRED,
    MSG_UNDO_RESTORE_FAILED,
    MSG_UNEXPECTED_CALLBACK_ERROR,
    MSG_UNKNOWN_SELF_REMIND_MODE,
    MSG_UNKNOWN_TIME_OPTION,
    MSG_USER_CONTEXT_MISSING,
    msg_after_me_requires_date_and_text,
    msg_after_target_requires_date_and_text,
    msg_recurring_missing_dash,
    msg_recurring_parse_failed,
    msg_user_has_not_started_bot,
)

from parser_split import _split_expr_and_text
from parser_time_tokens import TIME_TOKEN_RE, VAGUE_TIME_WORDS, _extract_time_from_tokens
from parser_in_expression import _add_months, _parse_in_expression
from parser_relative_day import _parse_standalone_vague_time, _parse_today_tomorrow
from parser_normalization import _normalize_on_at_phrase
from parser_next_expression import _parse_next_expression
from parser_weekend_weekday import _parse_weekend_weekday
from parser_month_name_date import _parse_month_name_date
from parser_absolute import _parse_absolute
from parser_date_time_smart import parse_date_time_smart
from parser_recurring_detection import looks_like_recurring
from bulk_header_detection import drop_optional_bulk_header
from bulk_single_reminder import create_single_reminder_from_line
from single_recurring_reminder import try_handle_single_recurring_reminder
from single_oneoff_reminder import handle_single_oneoff_reminder
from snooze_apply import apply_snooze_to_reminder
from snooze_custom_flow import enter_custom_snooze_flow
from snooze_calendar_nav import show_custom_snooze_calendar
from snooze_time_picker import enter_custom_snooze_time_picker
from snooze_picktime_flow import handle_custom_snooze_picktime
from snooze_cancel_flow import handle_custom_snooze_cancel
from snooze_direct_flow import handle_direct_snooze_action
from reminder_done_flow import handle_done_callback
from callback_data_parsing import parse_optional_int_callback_id, parse_snooze_action_callback_data, parse_snooze_calendar_callback_data, parse_snooze_pickdate_callback_data, parse_snooze_picktime_callback_data, parse_required_int_callback_id
from parser_recurring_schedule import _add_months_clamped, compute_next_occurrence
from parser_recurring import parse_recurring
from parser_default_time_adapter import parse_with_optional_default_time
from self_remind_time import compute_self_remind_time
from reply_utils import safe_reply
from reminder_message_proxy import NormalizedReminderMessageProxy
from voice_file_io import download_telegram_file_bytes
from plain_text_local_normalization import normalize_plain_text_reminder_locally
from voice_text_normalization import (
    _normalize_plain_text_relative_reminder_locally,
    _normalize_voice_ru_months,
    _normalize_voice_spoken_numbers,
    _strip_voice_reminder_prefix,
    normalize_gemini_reminder_command_text,
    normalize_voice_reminder_text,
)
from gemini_transcription import gemini_transcribe_audio_with_retries
from gemini_errors import (
    _is_gemini_quota_error,
    _is_transient_gemini_error,
    _is_unsupported_gemini_model_error,
)
from voice_alias_prompt import format_known_aliases_for_voice_prompt
from command_messages import HELP_TEXT, START_TEXT
from models import Reminder
from default_time import _default_time_or, format_default_time_value, parse_default_time_value
from remind_arg_utils import strip_first_token_from_first_line
from remind_group_routing import reject_group_remind_target_prefix_if_needed
from command_text import (
    MONTH_REMINDER_PREFIXES,
    SMART_REMINDER_PREFIXES,
    extract_after_command,
    first_token_looks_like_reminder_start,
    maybe_split_alias_first_token,
)
from self_remind_source import (
    format_self_remind_text,
    get_query_source_chat_title,
    get_source_chat_title_for_self_remind,
)
from event_datetime import (
    _build_event_datetime,
    _nearest_future_time_from_base,
    _parse_time_match,
    compute_event_before_time,
    extract_event_datetime_from_text,
    get_self_remind_event_base,
    normalize_relative_event_date_in_text,
)
from parser_lexicon import (
    VOICE_SPOKEN_NUMBER_REPLACEMENTS,
    VOICE_RU_MONTH_NORMALIZATION_MAP,
    MONTH_EN,
    WEEKDAY_RU,
    WEEKDAY_EN,
    is_recurring_missing_dash_candidate,
)

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

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            default_hour INTEGER,
            default_minute INTEGER,
            updated_at TEXT NOT NULL
        )
        """
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


def get_user_default_time(user_id: Optional[int]) -> Optional[Tuple[int, int]]:
    if user_id is None:
        return None

    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT default_hour, default_minute
            FROM user_settings
            WHERE user_id = ?
            """,
            (int(user_id),),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    hour, minute = row
    if hour is None or minute is None:
        return None

    try:
        return int(hour), int(minute)
    except Exception:
        return None


def set_user_default_time(user_id: int, hour: int, minute: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO user_settings(user_id, default_hour, default_minute, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                default_hour = excluded.default_hour,
                default_minute = excluded.default_minute,
                updated_at = excluded.updated_at
            """,
            (int(user_id), int(hour), int(minute), get_now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def clear_user_default_time(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "DELETE FROM user_settings WHERE user_id = ?",
            (int(user_id),),
        )
        conn.commit()
    finally:
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


def update_reminder_time(reminder_id: int, new_dt: datetime) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        UPDATE reminders
        SET remind_at = ?,
            delivered = 0,
            acked = 0,
            sent_at = NULL,
            nudge_count = 0
        WHERE id = ?
        """,
        (new_dt.isoformat(), int(reminder_id)),
    )
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed

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

# ===== SNOOZE клавиатуры =====

def build_created_reminder_actions_keyboard_for_reminder(reminder_id: int) -> Optional[InlineKeyboardMarkup]:
    reminder = get_reminder(reminder_id)
    if reminder is None:
        return None
    is_recurring = bool(getattr(reminder, "template_id", None))
    return build_created_reminder_actions_keyboard(reminder_id, is_recurring=is_recurring)


def _sync_keyboard_builder_classes() -> None:
    keyboard_builders.InlineKeyboardButton = InlineKeyboardButton
    keyboard_builders.InlineKeyboardMarkup = InlineKeyboardMarkup


def build_list_delete_keyboard(reminder_id: int):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_list_delete_keyboard(reminder_id)


def build_recurring_delete_choice_keyboard(reminder_id: int, template_id: int):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_recurring_delete_choice_keyboard(reminder_id, template_id)


def build_created_reminder_actions_keyboard(reminder_id: int, is_recurring: bool = False):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_created_reminder_actions_keyboard(reminder_id, is_recurring=is_recurring)


def build_created_reschedule_keyboard(reminder_id: int):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_created_reschedule_keyboard(reminder_id)


def build_snooze_keyboard(reminder_id: int):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_snooze_keyboard(reminder_id)


def build_group_reminder_keyboard(reminder_id: int):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_group_reminder_keyboard(reminder_id)


def build_self_remind_mode_keyboard(reminder_id: int):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_self_remind_mode_keyboard(reminder_id)


def build_self_remind_choice_keyboard(reminder_id: int):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_self_remind_choice_keyboard(reminder_id)


def build_self_remind_event_before_keyboard(reminder_id: int):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_self_remind_event_before_keyboard(reminder_id)


def build_custom_date_keyboard(
    reminder_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    callback_prefix: str = "snooze",
):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_custom_date_keyboard(
        reminder_id,
        year=year,
        month=month,
        callback_prefix=callback_prefix,
    )


def build_custom_time_keyboard(reminder_id: int, date_str: str, callback_prefix: str = "snooze"):
    _sync_keyboard_builder_classes()
    return keyboard_builders.build_custom_time_keyboard(
        reminder_id,
        date_str,
        callback_prefix=callback_prefix,
    )


# ===== Хендлеры команд =====


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

    text = START_TEXT

    msg = update.effective_message
    await safe_reply(msg, text)

async def start_command(update: Update, context: CTX) -> None:
    await start(update, context)

async def help_command(update: Update, context: CTX) -> None:
    message = update.effective_message
    if message is None:
        return

    text = HELP_TEXT

    await safe_reply(message, text)


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
        f"напомни {alias} 28.11 12:00 завтра футбол\n"
        f"или командой:\n"
        f"/remind {alias} 28.11 12:00 - завтра футбол"
    )

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
    default_time: Optional[Tuple[int, int]] = None,
):
    return create_single_reminder_from_line(
        line=line,
        now=now,
        target_chat_id=target_chat_id,
        user=user,
        default_time=default_time,
        looks_like_recurring=looks_like_recurring,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_recurring=parse_recurring,
        parse_date_time_smart=parse_date_time_smart,
        create_recurring_template=create_recurring_template,
        add_reminder=add_reminder,
        logger=logger,
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


def _format_known_aliases_for_voice_prompt(created_by: int) -> str:
    return format_known_aliases_for_voice_prompt(
        created_by,
        get_all_user_aliases=get_all_user_aliases,
        get_all_aliases=get_all_aliases,
        logger=logger,
    )


async def _gemini_transcribe_audio_with_retries(
    *,
    client,
    audio_bytes: bytes,
    attempts_per_model: Optional[int] = None,
    aliases_prompt: str = "",
) -> str:
    return await gemini_transcribe_audio_with_retries(
        client=client,
        audio_bytes=audio_bytes,
        genai_types=genai_types,
        logger=logger,
        attempts_per_model=attempts_per_model,
        aliases_prompt=aliases_prompt,
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
    audio_bytes = await download_telegram_file_bytes(tg_file, suffix=".ogg")

    client = genai.Client(api_key=token)

    return await _gemini_transcribe_audio_with_retries(
        client=client,
        audio_bytes=audio_bytes,
        aliases_prompt=_format_known_aliases_for_voice_prompt(update.effective_user.id),
    )

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
            model_timeout = float(
                os.environ.get(
                    "GEMINI_MODEL_CALL_TIMEOUT_SECONDS",
                    os.environ.get("GEMINI_REMINDER_PARSE_TIMEOUT_SECONDS", "10"),
                )
            )
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=[prompt],
                ),
                timeout=model_timeout,
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
        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning(
                "GEMINI_TEXT_NORMALIZE_TIMEOUT model=%s timeout=%s raw_len=%s",
                model,
                model_timeout,
                len(raw),
            )
            continue        
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

    proxy_message = NormalizedReminderMessageProxy(
        message,
        f"/remind {normalized}",
        normalized,
    )

    proxy_update = SimpleNamespace(
        effective_chat=chat,
        effective_message=proxy_message,
        effective_user=user,
        message=proxy_message,
    )

    await remind_command(proxy_update, context)


def _normalize_plain_text_reminder_locally(raw_text: str) -> Optional[str]:
    return normalize_plain_text_reminder_locally(
        raw_text,
        split_expr_and_text=_split_expr_and_text,
        parse_date_time_smart=parse_date_time_smart,
        get_now=get_now,
    )


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

    normalization_source = "local"
    normalized = _normalize_plain_text_reminder_locally(raw_text)

    if not normalized:
        normalization_source = "local_relative"
        normalized = _normalize_plain_text_relative_reminder_locally(raw_text)

    if not normalized:
        normalization_source = "gemini"
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
            normalization_source = "fallback"
            normalized = _normalize_reminder_text_fallback(raw_text)

    normalized = (normalized or "").strip()
    normalized = normalize_gemini_reminder_command_text(normalized)

    if normalized == "NO_REMINDER" or not normalized:
        await safe_reply(
            message,
            MSG_NOT_UNDERSTOOD_PLAIN_TEXT
        )
        return

    if normalized.startswith("/remind "):
        normalized = normalized[len("/remind "):].strip()

    logger.info(
        "TEXT_REMIND_NORMALIZED source=%s user_id=%s chat_id=%s raw_len=%s normalized_len=%s",
        normalization_source,
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
            MSG_NOT_UNDERSTOOD_PLAIN_TEXT
        )
        return

    proxy_message = NormalizedReminderMessageProxy(
        message,
        f"/remind {normalized}",
        normalized,
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

async def defaulttime_command(update: Update, context: CTX) -> None:
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    args = list(context.args or [])

    if not args:
        current = get_user_default_time(user.id)
        if current is None:
            await safe_reply(
                message,
                "Время по умолчанию не задано. Для напоминаний без явно указанного времени бот использует 10:00.\n\n"
                "Поставить: /defaulttime 09:30\n"
                "Сбросить: /defaulttime reset"
            )
            return

        await safe_reply(
            message,
            f"Текущее время по умолчанию: {format_default_time_value(*current)}\n\n"
            "Изменить: /defaulttime 09:30\n"
            "Сбросить: /defaulttime reset"
        )
        return

    value = args[0].strip().lower()

    if value in {"reset", "default", "off", "сброс", "сбросить"}:
        clear_user_default_time(user.id)
        await safe_reply(message, "Ок, сбросил время по умолчанию. Теперь для напоминаний без явно указанного времени бот снова использует 10:00.")
        return

    try:
        hour, minute = parse_default_time_value(value)
    except ValueError:
        await safe_reply(
            message,
            "Не понял время. Формат: /defaulttime 09:30"
        )
        return

    set_user_default_time(user.id, hour, minute)
    await safe_reply(
        message,
        f"Ок, время по умолчанию: {format_default_time_value(hour, minute)}."
    )


async def remind_command(update: Update, context: CTX) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    now = get_now()
    default_time = get_user_default_time(user.id)

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
            MSG_REMIND_USAGE
        )
        return

    is_private = chat.type == Chat.PRIVATE

    group_prefix_rejected, raw_args = await reject_group_remind_target_prefix_if_needed(
        is_private=is_private,
        raw_args=raw_args,
        user_id=user.id,
        message=message,
        safe_reply=safe_reply,
        get_chat_id_by_alias_for_user=get_chat_id_by_alias_for_user,
        msg_group_username_prefix_forbidden=MSG_GROUP_USERNAME_PREFIX_FORBIDDEN,
        msg_group_alias_prefix_forbidden=MSG_GROUP_ALIAS_PREFIX_FORBIDDEN,
    )
    if group_prefix_rejected:
        return

    if is_recurring_missing_dash_candidate(raw_args) and " - " not in raw_args:
        await safe_reply(message, msg_recurring_missing_dash(is_private))
        return

    target_chat_id = chat.id
    used_alias: Optional[str] = None

    # В личке допускаем slack-style "/remind me ..."
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip().lower()

            if first_token == "me":
                raw_args = strip_first_token_from_first_line(raw_args, first_token)

                logger.info(
                    "REMIND me-stripped chat_id=%s user_id=%s raw_args=%r",
                    chat.id,
                    user.id,
                    raw_args,
                )

                if not raw_args:
                    await safe_reply(
                        message,
                        msg_after_me_requires_date_and_text("Пример: /remind me on Tuesday - алкоголь под КС")
                    )
                    return

    # В личке допускаем @username первым словом / первой строкой
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip()
            if first_token.lower() == "me":
                raw_args = strip_first_token_from_first_line(raw_args, first_token)

                if not raw_args:
                    await safe_reply(
                        message,
                        msg_after_me_requires_date_and_text("Пример: /remind me at 18:00 - купить молоко")
                    )
                    return
            if first_token.startswith("@") and len(first_token) > 1:
                target = get_user_chat_id_by_username(first_token)
                if target is None:
                    await safe_reply(
                        message,
                        msg_user_has_not_started_bot(first_token)
                    )
                    return

                # убираем @username из raw_args
                raw_args = strip_first_token_from_first_line(raw_args, first_token)

                if not raw_args:
                    await safe_reply(
                        message,
                        msg_after_target_requires_date_and_text(first_token, f"Пример: /remind {first_token} tomorrow 10:00 - привет")
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
                raw_args = strip_first_token_from_first_line(raw_args, first_token)

                if not raw_args:
                    await safe_reply(
                        message,
                        msg_after_me_requires_date_and_text("Пример: /remind me at 18:00 - купить молоко")
                    )
                    return

            # alias != @username и alias != me (эти кейсы обработаны выше)
            elif first_token and not first_token.startswith("@"):
                # Не трогаем обычные команды, которые уже начинаются с даты/времени/recurring.
                # Важно: используем общий helper, чтобы maybe_split_alias_first_token()
                # и remind_command() не расходились по списку smart-prefixes.
                if not first_token_looks_like_reminder_start(first_token):
                    raw_args_without_first_token = strip_first_token_from_first_line(raw_args, first_token)

                    user_alias_chat_id = get_user_alias_chat_id_for_user(first_token, user.id)
                    if user_alias_chat_id is not None:
                        raw_args = raw_args_without_first_token
                        target_chat_id = user_alias_chat_id
                        used_alias = None

                        if not raw_args:
                            await safe_reply(
                                message,
                                "После alias нужно указать дату и текст.\n"
                                f"Пример:\nнапомни {first_token} 28.11 12:00 завтра футбол\n"
                                f"или командой:\n/remind {first_token} 28.11 12:00 - завтра футбол"
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
                                parse_with_optional_default_time(parse_date_time_smart, raw_args_without_first_token, now, default_time=default_time)
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
        raw_lines = drop_optional_bulk_header(
            raw_lines,
            looks_like_recurring=looks_like_recurring,
        )

        lines = []
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

    recurring_handled = await try_handle_single_recurring_reminder(
        raw_single=raw_single,
        now=now,
        target_chat_id=target_chat_id,
        used_alias=used_alias,
        chat=chat,
        user=user,
        message=message,
        is_private=is_private,
        default_time=default_time,
        looks_like_recurring=looks_like_recurring,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_recurring=parse_recurring,
        create_recurring_template=create_recurring_template,
        add_reminder=add_reminder,
        build_created_reminder_actions_keyboard=build_created_reminder_actions_keyboard,
        format_recurring_human=format_recurring_human,
        format_created_recurring_reminder_text=format_created_recurring_reminder_text,
        msg_recurring_parse_failed=msg_recurring_parse_failed,
        safe_reply=safe_reply,
        logger=logger,
    )
    if recurring_handled:
        return

    await handle_single_oneoff_reminder(
        raw_single=raw_single,
        now=now,
        target_chat_id=target_chat_id,
        used_alias=used_alias,
        chat=chat,
        user=user,
        message=message,
        default_time=default_time,
        private_chat_type=Chat.PRIVATE,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_date_time_smart=parse_date_time_smart,
        normalize_plain_text_reminder_with_gemini=normalize_plain_text_reminder_with_gemini,
        normalize_gemini_reminder_command_text=normalize_gemini_reminder_command_text,
        normalize_reminder_text_fallback=_normalize_reminder_text_fallback,
        add_reminder=add_reminder,
        build_created_reminder_actions_keyboard=build_created_reminder_actions_keyboard,
        format_created_reminder_text=format_created_reminder_text,
        msg_parse_date_text_failed=MSG_PARSE_DATE_TEXT_FAILED,
        safe_reply=safe_reply,
        logger=logger,
    )
    return


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

            presentation_rows = build_target_user_presentation_rows(
                rows,
                recurring_template_loader=get_recurring_template,
            )

            reply, ids, keyboard = build_target_user_reminders_list_response(
                presentation_rows,
                target_label=first_arg,
                list_delete_keyboard_builder=build_list_delete_keyboard,
            )

            if not ids:
                await safe_reply(message, reply)
                return

            context.user_data["list_ids"] = ids
            context.user_data["list_chat_id"] = owner_chat_id

            await safe_reply(
                message,
                reply,
                reply_markup=keyboard,
            )
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
        await safe_reply(
            message,
            format_empty_active_reminders_list_text(chat_alias=used_alias),
        )
        return

    header = f"Активные напоминания для чата '{used_alias}':" if used_alias else "Активные напоминания:"
    reply, ids, keyboard = build_active_reminders_list_response(
        rows,
        header=header,
        now_local=get_now(),
        list_delete_keyboard_builder=build_list_delete_keyboard,
    )

    context.user_data["list_ids"] = ids
    context.user_data["list_chat_id"] = target_chat_id

    await safe_reply(message, reply, reply_markup=keyboard)

def compute_snooze_target_time(action: str, now: datetime, default_time: Optional[Tuple[int, int]] = None) -> datetime:
    now = now.astimezone(TZ)

    if action == "20m":
        return now + timedelta(minutes=20)
    if action == "1h":
        return now + timedelta(hours=1)
    if action == "3h":
        return now + timedelta(hours=3)
    if action == "tomorrow":
        base = (now + timedelta(days=1)).date()
        return datetime(base.year, base.month, base.day, *_default_time_or(default_time, 10, 0), tzinfo=TZ)
    if action == "nextmon":
        base = now.date()
        cur_wd = base.weekday()
        delta = (0 - cur_wd + 7) % 7
        if delta == 0:
            delta = 7
        target = base + timedelta(days=delta)
        return datetime(target.year, target.month, target.day, 10, 0, tzinfo=TZ)

    raise ValueError(f"Unknown snooze action: {action}")

async def created_delete_callback(update: Update, context: CTX) -> None:
    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_DELETE_FAILED_SHORT, show_alert=True)
        await query.edit_message_text(MSG_DELETE_FAILED_TEXT, reply_markup=None)
        return

    row = get_reminder_row(reminder_id)
    if not row:
        await query.answer(MSG_REMINDER_ALREADY_DELETED_ALERT, show_alert=True)
        await query.edit_message_text(MSG_REMINDER_ALREADY_DELETED_TEXT, reply_markup=None)
        return

    template_id = row["template_id"] if "template_id" in row.keys() else None
    if template_id is not None:
        keyboard = build_recurring_delete_choice_keyboard(reminder_id, int(template_id))
        context.user_data["delete_choice_source"] = "created"

        await query.answer()
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    snapshot = delete_single_reminder_with_snapshot(reminder_id, int(row["chat_id"]))
    if not snapshot:
        await query.answer(MSG_REMINDER_ALREADY_DELETED_ALERT, show_alert=True)
        await query.edit_message_text(MSG_REMINDER_ALREADY_DELETED_TEXT, reply_markup=None)
        return

    token = make_undo_token()
    context.user_data["undo_tokens"] = context.user_data.get("undo_tokens") or {}
    context.user_data["undo_tokens"][token] = snapshot

    tpl = snapshot.get("template") or {}
    tpl_pattern_type = tpl.get("pattern_type")
    tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}

    deleted_text = format_deleted_human(
        snapshot["reminder"]["remind_at"],
        snapshot["reminder"]["text"],
        tpl_pattern_type,
        tpl_payload,
    )

    undo_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("↩️ Вернуть ремайндер", callback_data=cb_undo(token))]]
    )

    await query.answer("Удалено")
    await query.edit_message_text(f"Удалил: {deleted_text}", reply_markup=undo_kb)


async def _answer_created_action_reminder_missing(query) -> None:
    await query.answer(MSG_REMINDER_NOT_FOUND, show_alert=True)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("Failed to clear created-action keyboard for missing reminder")


async def _ensure_created_action_reminder_exists(query, reminder_id: int) -> bool:
    if get_reminder(reminder_id) is not None:
        return True
    await _answer_created_action_reminder_missing(query)
    return False


async def created_reschedule_callback(update: Update, context: CTX) -> None:
    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_RESCHEDULE_OPEN_FAILED_TEXT, show_alert=True)
        await query.edit_message_text(MSG_RESCHEDULE_OPEN_FAILED_TEXT, reply_markup=None)
        return

    if not await _ensure_created_action_reminder_exists(query, reminder_id):
        return

    await query.answer()
    await query.edit_message_reply_markup(reply_markup=build_created_reschedule_keyboard(reminder_id))


async def created_snooze_callback(update: Update, context: CTX) -> None:
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""

    try:
        if data.startswith("created_snooze:"):
            _, rid_str, action = data.split(":", 2)
            rid = int(rid_str)

            r = get_reminder(rid)
            if not r:
                await _answer_created_action_reminder_missing(query)
                return

            try:
                new_dt = compute_snooze_target_time(action, get_now(), default_time=get_user_default_time(getattr(getattr(query, 'from_user', None), 'id', None)))
            except ValueError:
                await query.answer(MSG_RESCHEDULE_UNKNOWN_ACTION, show_alert=True)
                return

            if not update_reminder_time(rid, new_dt):
                await _answer_created_action_reminder_missing(query)
                return

            when_str = new_dt.strftime("%d.%m %H:%M")
            await query.edit_message_text(
                f"Перенёс напоминание на {when_str}: {r.text}",
                reply_markup=build_created_reminder_actions_keyboard_for_reminder(rid),
            )
            await query.answer(f"Перенесено на {when_str}")
            return

        if data.startswith("created_snooze_cal:"):
            _, rid_str, ym = data.split(":", 2)
            rid = int(rid_str)
            if not await _ensure_created_action_reminder_exists(query, rid):
                return

            year_str, month_str = ym.split("-", 1)
            keyboard = build_custom_date_keyboard(
                rid,
                year=int(year_str),
                month=int(month_str),
                callback_prefix="created_snooze",
            )
            await query.edit_message_reply_markup(reply_markup=keyboard)
            await query.answer()
            return

        if data.startswith("created_snooze_caltoday:"):
            _, rid_str = data.split(":", 1)
            rid = int(rid_str)
            if not await _ensure_created_action_reminder_exists(query, rid):
                return

            today = get_now().date()
            keyboard = build_custom_date_keyboard(
                rid,
                year=today.year,
                month=today.month,
                callback_prefix="created_snooze",
            )
            await query.edit_message_reply_markup(reply_markup=keyboard)
            await query.answer()
            return

        if data.startswith("created_snooze_pickdate:"):
            _, rid_str, date_str = data.split(":", 2)
            rid = int(rid_str)
            if not await _ensure_created_action_reminder_exists(query, rid):
                return

            keyboard = build_custom_time_keyboard(
                rid,
                date_str,
                callback_prefix="created_snooze",
            )
            await query.edit_message_reply_markup(reply_markup=keyboard)
            await query.answer("Выбери время")
            return

        if data.startswith("created_snooze_pastdate:"):
            await query.answer(MSG_RESCHEDULE_PAST_TIME, show_alert=True)
            return

        if data.startswith("created_snooze_picktime:"):
            _, rid_str, date_str, time_str = data.split(":", 3)
            rid = int(rid_str)

            r = get_reminder(rid)
            if not r:
                await _answer_created_action_reminder_missing(query)
                return

            try:
                year, month, day = map(int, date_str.split("-"))
                hour, minute = map(int, time_str.split(":"))
                new_dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
            except Exception:
                await query.answer(MSG_RESCHEDULE_BAD_DATETIME, show_alert=True)
                return

            if new_dt <= get_now():
                await query.answer(MSG_RESCHEDULE_PAST_TIME, show_alert=True)
                return

            if not update_reminder_time(rid, new_dt):
                await _answer_created_action_reminder_missing(query)
                return

            when_str = new_dt.strftime("%d.%m %H:%M")
            await query.edit_message_text(
                f"Перенёс напоминание на {when_str}: {r.text}",
                reply_markup=build_created_reminder_actions_keyboard_for_reminder(rid),
            )
            await query.answer(f"Перенесено на {when_str}")
            return

        if data.startswith("created_snooze_cancel:"):
            _, rid_str = data.split(":", 1)
            rid = int(rid_str)
            if not await _ensure_created_action_reminder_exists(query, rid):
                return

            await query.edit_message_reply_markup(reply_markup=build_created_reschedule_keyboard(rid))
            await query.answer("Вернул варианты")
            return

    except ValueError:
        await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
        return
    except Exception:
        logger.exception("Ошибка в created_snooze_callback")
        try:
            await query.answer(MSG_UNEXPECTED_CALLBACK_ERROR, show_alert=True)
        except Exception:
            pass


async def created_snooze_custom_callback(update: Update, context: CTX) -> None:
    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
        return

    if not await _ensure_created_action_reminder_exists(query, reminder_id):
        return

    keyboard = build_custom_date_keyboard(reminder_id, callback_prefix="created_snooze")

    await query.edit_message_reply_markup(reply_markup=keyboard)
    await query.answer("Выбери дату")
    return


async def created_snooze_cancel_callback(update: Update, context: CTX) -> None:
    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
        return

    if not await _ensure_created_action_reminder_exists(query, reminder_id):
        return

    await query.edit_message_reply_markup(reply_markup=build_created_reschedule_keyboard(reminder_id))
    await query.answer("Вернул варианты")
    return


async def created_back_callback(update: Update, context: CTX) -> None:
    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if not await _ensure_created_action_reminder_exists(query, reminder_id):
        return

    await query.answer()
    await query.edit_message_reply_markup(
        reply_markup=build_created_reminder_actions_keyboard_for_reminder(reminder_id)
    )


def _build_active_list_response_for_ids(ids):
    if not ids:
        return "Напоминаний больше нет.", None, ids

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

    reply, rebuilt_ids, keyboard = build_active_reminders_list_response(
        rows,
        header="Активные напоминания:",
        now_local=get_now(),
        list_delete_keyboard_builder=build_list_delete_keyboard,
)
    return reply, keyboard, rebuilt_ids


async def _edit_stored_list_message_after_delete(context, ids):
    ref = context.user_data.get("list_message_ref") or {}
    chat_id = ref.get("chat_id")
    message_id = ref.get("message_id")

    if chat_id is None or message_id is None:
        return

    reply, keyboard, rebuilt_ids = _build_active_list_response_for_ids(ids)
    context.user_data["list_ids"] = rebuilt_ids

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=reply,
        reply_markup=keyboard,
    )


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
        await query.answer(MSG_REMINDER_ALREADY_DELETED_ALERT, show_alert=True)
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

        kb = build_recurring_delete_choice_keyboard(rid, int(tpl_id))

        context.user_data["delete_choice_source"] = "list"
        if query.message:
            context.user_data["list_message_ref"] = {
                "chat_id": query.message.chat.id,
                "message_id": query.message.message_id,
            }
            await query.message.reply_text(
                "Это повторяющееся напоминание. Как удалить?\n\n" + preview,
                reply_markup=kb,
            )
        return

    # НЕ recurring - удаляем сразу + undo
    snapshot = delete_single_reminder_with_snapshot(rid, int(target_chat_id))
    if not snapshot:
        await query.answer(MSG_REMINDER_ALREADY_DELETED_ALERT, show_alert=True)
        return

    ids.pop(idx - 1)
    context.user_data["list_ids"] = ids

    if query.message:
        reply, keyboard, ids = _build_active_list_response_for_ids(ids)
        context.user_data["list_ids"] = ids
        await query.edit_message_text(reply, reply_markup=keyboard)

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
        [[InlineKeyboardButton("↩️ Вернуть ремайндер", callback_data=cb_undo(token))]]
    )

    if query.message:
        await query.message.reply_text(f"Удалил: {deleted_text}", reply_markup=undo_kb)


async def delete_choose_callback(update: Update, context: CTX) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    if not (data.startswith("del_one:") or data.startswith("del_series:") or data.startswith("del_cancel:")):
        return

    if data.startswith("del_cancel:"):
        try:
            rid = int(data.split(":", 1)[1])
        except ValueError:
            return

        source = context.user_data.pop("delete_choice_source", None)
        if source == "created":
            await query.edit_message_reply_markup(
                reply_markup=build_created_reminder_actions_keyboard(rid, is_recurring=True)
            )
        else:
            await query.edit_message_text("Ок, ничего не удалил.", reply_markup=None)
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
            await query.answer(MSG_DELETE_FAILED_SHORT, show_alert=True)
            return

        # убираем rid из текущего списка (если он там есть)
        ids = [x for x in ids if int(x) != int(rid)]
        context.user_data["list_ids"] = ids

        deleted_label = "Удалил ближайшее повторяющееся напоминание"

    elif data.startswith("del_series:"):
        try:
            tpl_id = int(data.split(":", 1)[1])
        except ValueError:
            return

        snapshot = delete_recurring_series_with_snapshot(tpl_id, int(target_chat_id))
        if not snapshot:
            await query.answer(MSG_DELETE_SERIES_FAILED, show_alert=True)
            return

        removed_ids = {int(r["id"]) for r in (snapshot.get("reminders") or []) if r.get("id") is not None}
        ids = [x for x in ids if int(x) not in removed_ids]
        context.user_data["list_ids"] = ids

        deleted_label = "Удалил всю серию"

    source = context.user_data.pop("delete_choice_source", None)
    if source == "list":
        await _edit_stored_list_message_after_delete(context, ids)

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
        [[InlineKeyboardButton(btn_text, callback_data=cb_undo(token))]]
    )

    if query.message:
        await query.edit_message_text(format_deleted_snapshot_text(deleted_label, deleted_text), reply_markup=undo_kb)

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
        await query.answer(MSG_UNDO_EXPIRED, show_alert=True)
        return

    # одноразовый undo
    del store[token]
    context.user_data["undo_tokens"] = store

    restored = restore_deleted_snapshot(snapshot)
    if not restored:
        await query.answer(MSG_UNDO_RESTORE_FAILED, show_alert=True)
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

        restored_id = None
        if isinstance(restored, list) and restored:
            try:
                restored_id = int(restored[0])
            except (TypeError, ValueError):
                restored_id = None

        reply_markup = None
        if restored_id is not None:
            reply_markup = build_created_reminder_actions_keyboard_for_reminder(restored_id)

        await query.edit_message_text(
            format_restored_series_text(series_text, suffix, count),
            reply_markup=reply_markup,
        )
        return

    # single
    restored_text = format_deleted_human(
        snapshot["reminder"]["remind_at"],
        snapshot["reminder"]["text"],
        tpl_pattern_type,
        tpl_payload,
    )

    restored_id = None
    try:
        restored_id = int(restored)
    except (TypeError, ValueError):
        restored_id = None

    reply_markup = None
    if restored_id is not None:
        reply_markup = build_created_reminder_actions_keyboard_for_reminder(restored_id)

    if tpl:
        restored_prefix = "Вернул ближайшее повторяющееся напоминание"
    else:
        restored_prefix = "Вернул"

    await query.edit_message_text(format_restored_single_text(restored_prefix, restored_text), reply_markup=reply_markup)

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
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
                return

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer(MSG_USER_CONTEXT_MISSING, show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
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
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
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
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
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
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
                return

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer(MSG_USER_CONTEXT_MISSING, show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
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
                        MSG_EVENT_DATE_NOT_FOUND,
                        reply_markup=build_self_remind_choice_keyboard(rid),
                    )
                    await query.answer("Не смог понять дату события. Выбери обычное напоминание или время вручную.")
                    return

                event_str = event_at.strftime("%d.%m %H:%M")
                await query.edit_message_text(
                    f"Я понял, что событие из напоминания состоится {event_str}.\n"
                    "За сколько до этого времени напомнить?",
                    reply_markup=build_self_remind_event_before_keyboard(rid),
                )
                await query.answer("Выбери время")
                return

            await query.answer(MSG_UNKNOWN_SELF_REMIND_MODE, show_alert=True)
            return

        if data.startswith("selfremind:event_custom:"):
            _, _, rid_str = data.split(":", 2)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
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
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
                return

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer(MSG_USER_CONTEXT_MISSING, show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
                return

            base_now = get_self_remind_event_base(src)
            event_at = extract_event_datetime_from_text(src.text, base_now)
            if event_at is None:
                await query.answer(MSG_EVENT_DATE_NOT_FOUND, show_alert=True)
                return

            remind_at = compute_event_before_time(option, event_at)
            if remind_at is None:
                await query.answer(MSG_UNKNOWN_TIME_OPTION, show_alert=True)
                return

            if remind_at <= get_now():
                await query.answer(MSG_RESCHEDULE_PAST_TIME, show_alert=True)
                return

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)
            normalized_src_text = normalize_relative_event_date_in_text(src.text, event_at)
            personal_text = format_self_remind_text(source_chat_title, normalized_src_text)

            new_reminder_id = add_reminder(
                chat_id=target_chat_id,
                text=personal_text,
                remind_at=remind_at,
                created_by=user_id,
            )

            when_str = remind_at.strftime("%d.%m %H:%M")
            await query.edit_message_text(
                format_created_reminder_text(when_str, personal_text),
                reply_markup=build_created_reminder_actions_keyboard_for_reminder(new_reminder_id),
            )
            await query.answer("Личное напоминание создано")
            return

        if data.startswith("selfremind:set:"):
            _, _, rid_str, option = data.split(":", 3)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
                return

            user_id = getattr(query.from_user, "id", None)
            if user_id is None:
                await query.answer(MSG_USER_CONTEXT_MISSING, show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
                return

            if option == "custom":
                kb = build_custom_date_keyboard(rid, callback_prefix="selfremind")
                await query.edit_message_reply_markup(reply_markup=kb)
                await query.answer("Выбери дату")
                return

            remind_at = compute_self_remind_time(option, get_now())

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)
            personal_text = format_self_remind_text(source_chat_title, src.text)

            new_reminder_id = add_reminder(
                chat_id=target_chat_id,
                text=personal_text,
                remind_at=remind_at,
                created_by=user_id,
                template_id=None,
            )

            when_str = remind_at.strftime("%d.%m %H:%M")
            await query.edit_message_text(
                format_created_reminder_text(when_str, personal_text),
                reply_markup=build_created_reminder_actions_keyboard_for_reminder(new_reminder_id),
            )
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
                await query.answer(MSG_USER_CONTEXT_MISSING, show_alert=True)
                return

            target_chat_id = get_user_chat_id_by_user_id(user_id)
            if target_chat_id is None:
                await query.answer("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
                return

            try:
                year, month, day = map(int, date_str.split("-"))
                hour, minute = map(int, time_str.split(":"))
                remind_at = datetime(year, month, day, hour, minute, tzinfo=TZ)
            except Exception:
                await query.answer(MSG_RESCHEDULE_BAD_DATETIME, show_alert=True)
                return

            if remind_at <= get_now():
                await query.answer(MSG_RESCHEDULE_PAST_TIME, show_alert=True)
                return

            source_chat_title = await get_source_chat_title_for_self_remind(context, src, query)
            personal_text = format_self_remind_text(source_chat_title, src.text)

            new_reminder_id = add_reminder(
                chat_id=target_chat_id,
                text=personal_text,
                remind_at=remind_at,
                created_by=user_id,
                template_id=None,
            )

            when_str = remind_at.strftime("%d.%m %H:%M")
            await query.edit_message_text(
                format_created_reminder_text(when_str, personal_text),
                reply_markup=build_created_reminder_actions_keyboard_for_reminder(new_reminder_id),
            )
            await query.answer("Личное напоминание создано")
            return

        if data.startswith("selfremind_event_cancel:"):
            _, rid_str = data.split(":", 1)

            try:
                rid = int(rid_str)
            except ValueError:
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
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
            try:
                rid = parse_required_int_callback_id(data, prefix="selfremind_cancel:")
            except ValueError:
                await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
                return

            src = get_reminder(rid)
            if not src:
                await query.answer(MSG_SOURCE_REMINDER_NOT_FOUND, show_alert=True)
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
            rid = parse_optional_int_callback_id(data, prefix="done:")

            await handle_done_callback(
                reminder_id=rid,
                query=query,
                context=context,
                mark_reminder_acked=mark_reminder_acked,
                clear_reminder_message_keyboards=clear_reminder_message_keyboards,
                get_reminder=get_reminder,
                format_completed_reminder_text=format_completed_reminder_text,
            )
            return

        if data.startswith("snooze:"):
            rid, action = parse_snooze_action_callback_data(data)

            await handle_direct_snooze_action(
                reminder_id=rid,
                action=action,
                query=query,
                context=context,
                get_now=get_now,
                get_user_default_time=get_user_default_time,
                get_reminder=get_reminder,
                compute_snooze_target_time=compute_snooze_target_time,
                enter_custom_snooze_flow=enter_custom_snooze_flow,
                apply_snooze_to_reminder=apply_snooze_to_reminder,
                mark_reminder_acked=mark_reminder_acked,
                clear_reminder_message_keyboards=clear_reminder_message_keyboards,
                add_reminder=add_reminder,
                build_custom_date_keyboard=build_custom_date_keyboard,
                format_snoozed_reminder_text=format_snoozed_reminder_text,
                format_snoozed_answer_text=format_snoozed_answer_text,
                msg_reminder_not_found=MSG_REMINDER_NOT_FOUND,
                msg_reschedule_unknown_action=MSG_RESCHEDULE_UNKNOWN_ACTION,
            )
            return

        if data.startswith("snooze_cal:"):
            rid, year, month = parse_snooze_calendar_callback_data(data)

            await show_custom_snooze_calendar(
                reminder_id=rid,
                query=query,
                year=year,
                month=month,
                build_custom_date_keyboard=build_custom_date_keyboard,
            )
            return

        if data.startswith("snooze_caltoday:"):
            rid = parse_required_int_callback_id(data, prefix="snooze_caltoday:")

            today = datetime.now(TZ).date()
            await show_custom_snooze_calendar(
                reminder_id=rid,
                query=query,
                year=today.year,
                month=today.month,
                build_custom_date_keyboard=build_custom_date_keyboard,
                ignore_edit_errors=True,
            )
            return

        if data.startswith("snooze_pickdate:"):
            rid, date_str = parse_snooze_pickdate_callback_data(data)

            await enter_custom_snooze_time_picker(
                reminder_id=rid,
                date_str=date_str,
                query=query,
                mark_reminder_acked=mark_reminder_acked,
                build_custom_time_keyboard=build_custom_time_keyboard,
            )
            return

        if data.startswith("snooze_picktime:"):
            rid, date_str, time_str = parse_snooze_picktime_callback_data(data)

            await handle_custom_snooze_picktime(
                reminder_id=rid,
                date_str=date_str,
                time_str=time_str,
                query=query,
                context=context,
                tz=TZ,
                get_now=get_now,
                get_reminder=get_reminder,
                mark_reminder_acked=mark_reminder_acked,
                clear_reminder_message_keyboards=clear_reminder_message_keyboards,
                add_reminder=add_reminder,
                apply_snooze_to_reminder=apply_snooze_to_reminder,
                format_snoozed_reminder_text=format_snoozed_reminder_text,
                format_snoozed_answer_text=format_snoozed_answer_text,
                msg_reminder_not_found=MSG_REMINDER_NOT_FOUND,
                msg_reschedule_bad_datetime=MSG_RESCHEDULE_BAD_DATETIME,
                msg_reschedule_past_time=MSG_RESCHEDULE_PAST_TIME,
            )
            return

        if data.startswith("snooze_cancel:"):
            rid = parse_optional_int_callback_id(data, prefix="snooze_cancel:")

            await handle_custom_snooze_cancel(
                reminder_id=rid,
                query=query,
                mark_reminder_acked=mark_reminder_acked,
                build_snooze_keyboard=build_snooze_keyboard,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
            )
            return

        if data == "noop":
            await query.answer()
            return

    except Exception:
        logger.exception("Ошибка в snooze_callback")
        try:
            await query.answer(MSG_UNEXPECTED_CALLBACK_ERROR, show_alert=True)
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
    return SNOOZE_PATTERN

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
    application.add_handler(CommandHandler("defaulttime", defaulttime_command))
    application.add_handler(CommandHandler("linkchat", linkchat_command))
    application.add_handler(CommandHandler("linkuser", linkuser_command))
    application.add_handler(CommandHandler("aliases", aliases_command))
    application.add_handler(CommandHandler("unalias", unalias_command))
    application.add_handler(CommandHandler("renamealias", renamealias_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(MessageHandler(filters.VOICE, voice_remind_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_remind_command))
    application.add_handler(CallbackQueryHandler(created_delete_callback, pattern=r"^created_del:\d+$"))
    application.add_handler(CallbackQueryHandler(created_reschedule_callback, pattern=r"^created_resched:\d+$"))
    application.add_handler(CallbackQueryHandler(created_snooze_custom_callback, pattern=CREATED_SNOOZE_CUSTOM_PATTERN))
    application.add_handler(CallbackQueryHandler(created_snooze_callback, pattern=CREATED_SNOOZE_PATTERN))
    application.add_handler(CallbackQueryHandler(created_snooze_cancel_callback, pattern=r"^created_snooze_cancel:\d+$"))
    application.add_handler(CallbackQueryHandler(created_back_callback, pattern=r"^created_back:\d+$"))
    application.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del:\d+$"))
    application.add_handler(CallbackQueryHandler(delete_choose_callback, pattern=DELETE_CHOICE_PATTERN))
    application.add_handler(CallbackQueryHandler(undo_callback, pattern=UNDO_PATTERN))
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
