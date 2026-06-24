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
from self_remind_cancel_flow import handle_self_remind_cancel
from self_remind_event_cancel_flow import handle_self_remind_event_cancel
from self_remind_calendar_flow import handle_self_remind_calendar_month, handle_self_remind_calendar_today, handle_self_remind_pickdate
from self_remind_picktime_flow import handle_self_remind_picktime
from self_remind_create_flow import handle_self_remind_event_custom, handle_self_remind_event_before, handle_self_remind_set
from self_remind_initial_flow import handle_self_remind_ask, handle_self_remind_cancel_personal, handle_self_remind_back, handle_self_remind_mode
from callback_simple_flows import handle_done_callback_data, handle_noop_callback, handle_pastdate_callback, handle_self_remind_cancel_callback, handle_self_remind_event_cancel_callback, handle_snooze_cancel_callback_data, handle_snooze_current_month_callback
from reminder_callback_router import handle_reminder_callback
from reminder_callback_deps import build_reminder_callback_deps
from created_snooze_router import handle_created_snooze_callback
from created_snooze_deps import build_created_snooze_callback_deps
from delete_undo_router import handle_delete_callback, handle_delete_choose_callback, handle_undo_callback
from delete_undo_deps import build_delete_undo_callback_deps
from created_delete_router import handle_created_delete_callback
from reminders_workers import _safe_get_chat_type as _worker_safe_get_chat_type, run_reminders_nudge_worker, run_reminders_worker
from parser_recurring_schedule import _add_months_clamped, compute_next_occurrence
from parser_recurring import parse_recurring
from parser_default_time_adapter import parse_with_optional_default_time
from self_remind_time import compute_self_remind_time
from reply_utils import safe_reply
from reminder_message_proxy import NormalizedReminderMessageProxy
from voice_file_io import download_telegram_file_bytes
from plain_text_local_normalization import normalize_plain_text_reminder_locally
from plain_text_gemini_normalization import normalize_plain_text_reminder_with_gemini_impl
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
from remind_target_resolution import resolve_remind_target_and_args
from remind_dispatch import dispatch_remind_creation
from remind_command_router import handle_remind_command
from remind_command_deps import build_remind_command_deps
from list_command_flow import handle_list_command_flow
from alias_settings_commands import handle_aliases_command, handle_defaulttime_command, handle_linkchat_command, handle_linkuser_command, handle_renamealias_command, handle_unalias_command
from plain_text_remind_flow import handle_plain_text_remind_command
from voice_remind_flow import handle_voice_remind_command
from voice_transcription import transcribe_voice_message_impl
from reminder_text_normalization import normalize_reminder_text_fallback_impl
from reminder_message_store import clear_reminder_message_keyboards_impl, get_reminder_messages_impl, register_reminder_message_impl
from alias_settings_deps import build_alias_settings_command_deps
from voice_transcription_deps import build_voice_transcription_deps
from reminder_text_normalization_deps import build_reminder_text_normalization_deps
from voice_remind_deps import build_voice_remind_command_deps
from plain_text_remind_deps import build_plain_text_remind_command_deps
from list_command_deps import build_list_command_deps
from created_delete_deps import build_created_delete_callback_deps
from reminders_worker_deps import build_reminders_worker_deps
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

def _build_reminder_message_store_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        get_now=get_now,
        logger=logger,
        sqlite3=sqlite3,
    )

def register_reminder_message(
    reminder_id: int,
    chat_id: int,
    message_id: int,
    kind: str,
) -> None:
    return register_reminder_message_impl(
        reminder_id,
        chat_id,
        message_id,
        kind,
        _build_reminder_message_store_deps(),
    )


def get_reminder_messages(reminder_id: int) -> list[dict]:
    return get_reminder_messages_impl(reminder_id, _build_reminder_message_store_deps())


async def clear_reminder_message_keyboards(bot, reminder_id: int) -> None:
    await clear_reminder_message_keyboards_impl(bot, reminder_id, _build_reminder_message_store_deps())


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


def _build_alias_settings_command_deps():
    return build_alias_settings_command_deps(globals())

async def linkchat_command(update: Update, context: CTX) -> None:
    await handle_linkchat_command(update, context, _build_alias_settings_command_deps())

async def aliases_command(update: Update, context: CTX) -> None:
    await handle_aliases_command(update, context, _build_alias_settings_command_deps())

async def unalias_command(update: Update, context: CTX) -> None:
    await handle_unalias_command(update, context, _build_alias_settings_command_deps())

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
    await handle_renamealias_command(update, context, _build_alias_settings_command_deps())

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


def _build_voice_transcription_deps():
    return build_voice_transcription_deps(globals())

async def transcribe_voice_message(update: Update, context: CTX) -> Optional[str]:
    return await transcribe_voice_message_impl(update, context, _build_voice_transcription_deps())

async def normalize_plain_text_reminder_with_gemini(text: str, created_by: int) -> str:
    return await normalize_plain_text_reminder_with_gemini_impl(
        text,
        created_by,
        genai=genai,
        logger=logger,
        format_known_aliases_for_voice_prompt=_format_known_aliases_for_voice_prompt,
        is_unsupported_gemini_model_error=_is_unsupported_gemini_model_error,
        is_gemini_quota_error=_is_gemini_quota_error,
        is_transient_gemini_error=_is_transient_gemini_error,
    )


def _build_reminder_text_normalization_deps():
    return build_reminder_text_normalization_deps(globals())

def _normalize_reminder_text_fallback(text: str) -> str:
    return normalize_reminder_text_fallback_impl(text, _build_reminder_text_normalization_deps())

def _build_voice_remind_command_deps():
    return build_voice_remind_command_deps(globals())

async def voice_remind_command(update: Update, context: CTX) -> None:
    await handle_voice_remind_command(update, context, _build_voice_remind_command_deps())


def _normalize_plain_text_reminder_locally(raw_text: str) -> Optional[str]:
    return normalize_plain_text_reminder_locally(
        raw_text,
        split_expr_and_text=_split_expr_and_text,
        parse_date_time_smart=parse_date_time_smart,
        get_now=get_now,
    )


def _build_plain_text_remind_command_deps():
    return build_plain_text_remind_command_deps(globals())

async def plain_text_remind_command(update: Update, context: CTX) -> None:
    await handle_plain_text_remind_command(update, context, _build_plain_text_remind_command_deps())


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
    await handle_defaulttime_command(update, context, _build_alias_settings_command_deps())


def _build_remind_command_deps():
    return build_remind_command_deps(globals())

async def remind_command(update: Update, context: CTX) -> None:
    await handle_remind_command(update, context, _build_remind_command_deps())

async def linkuser_command(update: Update, context: CTX) -> None:
    await handle_linkuser_command(update, context, _build_alias_settings_command_deps())


def _build_list_command_deps():
    return build_list_command_deps(globals())


async def list_command(update: Update, context: CTX) -> None:
    await handle_list_command_flow(update, context, _build_list_command_deps())

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

def _build_created_delete_callback_deps():
    return build_created_delete_callback_deps(globals())

async def created_delete_callback(update: Update, context: CTX) -> None:
    await handle_created_delete_callback(update, context, _build_created_delete_callback_deps())


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


def _build_created_snooze_callback_deps():
    return build_created_snooze_callback_deps(globals())

async def created_snooze_callback(update: Update, context: CTX) -> None:
    await handle_created_snooze_callback(update, context, _build_created_snooze_callback_deps())


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


def _build_delete_undo_callback_deps():
    return build_delete_undo_callback_deps(globals())

async def delete_callback(update: Update, context: CTX) -> None:
    await handle_delete_callback(update, context, _build_delete_undo_callback_deps())


async def delete_choose_callback(update: Update, context: CTX) -> None:
    await handle_delete_choose_callback(update, context, _build_delete_undo_callback_deps())


async def undo_callback(update: Update, context: CTX) -> None:
    await handle_undo_callback(update, context, _build_delete_undo_callback_deps())

# ===== SNOOZE callback =====


def _build_reminder_callback_deps():
    return build_reminder_callback_deps(globals())

async def snooze_callback(update: Update, context: CTX) -> None:
    await handle_reminder_callback(update, context, _build_reminder_callback_deps())


# ===== Фоновый worker =====

async def _safe_get_chat_type(app: Application, chat_id: int) -> Optional[str]:
    return await _worker_safe_get_chat_type(app, chat_id)

def _build_reminders_worker_deps():
    return build_reminders_worker_deps(globals())
async def reminders_worker(app: Application) -> None:
    await run_reminders_worker(app, _build_reminders_worker_deps())

async def reminders_nudge_worker(app: Application) -> None:
    await run_reminders_nudge_worker(app, _build_reminders_worker_deps())

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
