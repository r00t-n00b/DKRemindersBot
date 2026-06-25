import asyncio
import logging
import os
import re
import sqlite3
import json
import inspect
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
from keyboard_builder_proxy import (
    _sync_keyboard_builder_classes_impl,
    build_created_reminder_actions_keyboard_for_reminder_impl,
    build_created_reminder_actions_keyboard_impl,
    build_created_reschedule_keyboard_impl,
    build_custom_date_keyboard_impl,
    build_custom_time_keyboard_impl,
    build_group_reminder_keyboard_impl,
    build_list_delete_keyboard_impl,
    build_recurring_delete_choice_keyboard_impl,
    build_self_remind_choice_keyboard_impl,
    build_self_remind_event_before_keyboard_impl,
    build_self_remind_mode_keyboard_impl,
    build_snooze_keyboard_impl,
)
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
from app_lifecycle import (
    _cancel_background_worker_impl,
    _start_background_worker_impl,
    post_init_impl,
    post_shutdown_impl,
)
from callback_simple_flows import handle_done_callback_data, handle_noop_callback, handle_pastdate_callback, handle_self_remind_cancel_callback, handle_self_remind_event_cancel_callback, handle_snooze_cancel_callback_data, handle_snooze_current_month_callback
from reminder_callback_router import handle_reminder_callback
from reminder_callback_deps import build_reminder_callback_deps
from created_snooze_router import handle_created_snooze_callback
from created_action_callbacks import (
    answer_created_action_reminder_missing_impl,
    ensure_created_action_reminder_exists_impl,
    handle_created_back_callback,
    handle_created_reschedule_callback,
    handle_created_snooze_cancel_callback,
    handle_created_snooze_custom_callback,
)
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
from command_helper_utils import (
    _format_bulk_result_impl,
    _rest_starts_like_datetime_impl,
    _strip_leading_token_in_group_impl,
    parse_renamealias_args_impl,
)
from alias_settings_commands import handle_aliases_command, handle_defaulttime_command, handle_linkchat_command, handle_linkuser_command, handle_renamealias_command, handle_unalias_command
from plain_text_remind_flow import handle_plain_text_remind_command
from voice_remind_flow import handle_voice_remind_command
from voice_transcription import transcribe_voice_message_impl
from reminder_text_normalization import normalize_reminder_text_fallback_impl
from reminder_message_store import clear_reminder_message_keyboards_impl, get_reminder_messages_impl, register_reminder_message_impl
from storage_user_chats import get_user_chat_id_by_user_id_impl, get_user_chat_id_by_username_impl, upsert_user_chat_impl
from storage_schema import _ensure_column_impl, init_db_impl, migrate_alias_tables_to_owner_scope_impl
from storage_delete_restore import activate_recurring_template_impl, deactivate_recurring_template_impl, delete_recurring_one_instance_and_reschedule_impl, delete_recurring_series_impl, delete_recurring_series_with_snapshot_impl, delete_reminder_with_snapshot_impl, delete_reminders_impl, delete_single_reminder_row_impl, delete_single_reminder_with_snapshot_impl, restore_deleted_snapshot_impl
from storage_aliases import delete_chat_alias_impl, delete_user_alias_impl, get_all_aliases_impl, get_all_user_aliases_impl, get_chat_id_by_alias_impl, get_private_chat_id_by_username_impl, get_user_alias_chat_id_impl, get_user_alias_impl, rename_chat_alias_impl, rename_user_alias_impl, set_chat_alias_for_user_impl, set_chat_alias_impl, set_user_alias_impl
from storage_user_settings import clear_user_default_time_impl, get_user_default_time_impl, set_user_default_time_impl
from storage_write import add_reminder_impl, create_recurring_template_impl, mark_nudge_sent_impl, mark_reminder_acked_impl, mark_reminder_sent_impl, update_reminder_time_impl
from storage_nudges import _nudge_threshold_minutes_impl, exhaust_nudges_impl, get_due_nudges_impl, increment_nudge_count_impl
from storage_read import get_active_reminders_created_by_for_chat_impl, get_active_reminders_for_chat_impl, get_due_reminders_impl, get_recurring_template_impl, get_recurring_template_row_impl, get_reminder_impl, get_reminder_row_impl, get_reminders_by_template_id_impl, get_unacked_sent_before_impl
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

def _build_storage_schema_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        logger=logger,
        sqlite3=sqlite3,
    )

def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    return _ensure_column_impl(conn, table, column, ddl, deps=_build_storage_schema_deps())

def init_db() -> None:
    return init_db_impl(deps=_build_storage_schema_deps())

def migrate_alias_tables_to_owner_scope() -> None:
    return migrate_alias_tables_to_owner_scope_impl(deps=_build_storage_schema_deps())


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


async def clear_reminder_message_keyboards(
    bot,
    reminder_id: int,
    replacement_text: str | None = None,
) -> None:
    await clear_reminder_message_keyboards_impl(
        bot,
        reminder_id,
        _build_reminder_message_store_deps(),
        replacement_text=replacement_text,
    )


def _build_storage_user_chats_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        TZ=TZ,
        sqlite3=sqlite3,
    )

def upsert_user_chat(user_id: int, chat_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> None:
    return upsert_user_chat_impl(user_id, chat_id, username, first_name, last_name, deps=_build_storage_user_chats_deps())

def get_user_chat_id_by_username(username: str) -> Optional[int]:
    return get_user_chat_id_by_username_impl(username, deps=_build_storage_user_chats_deps())

def get_user_chat_id_by_user_id(user_id: int) -> Optional[int]:
    return get_user_chat_id_by_user_id_impl(user_id, deps=_build_storage_user_chats_deps())


def _build_storage_user_settings_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        get_now=get_now,
        sqlite3=sqlite3,
    )

def get_user_default_time(user_id: Optional[int]) -> Optional[Tuple[int, int]]:
    return get_user_default_time_impl(user_id, deps=_build_storage_user_settings_deps())

def set_user_default_time(user_id: int, hour: int, minute: int) -> None:
    return set_user_default_time_impl(user_id, hour, minute, deps=_build_storage_user_settings_deps())

def clear_user_default_time(user_id: int) -> None:
    return clear_user_default_time_impl(user_id, deps=_build_storage_user_settings_deps())


def _build_storage_write_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        TZ=TZ,
        get_now=get_now,
        json=json,
        sqlite3=sqlite3,
    )

def add_reminder(chat_id: int, text: str, remind_at: datetime, created_by: Optional[int], template_id: Optional[int]=None) -> int:
    return add_reminder_impl(chat_id, text, remind_at, created_by, template_id, deps=_build_storage_write_deps())

def update_reminder_time(reminder_id: int, new_dt: datetime) -> bool:
    return update_reminder_time_impl(reminder_id, new_dt, deps=_build_storage_write_deps())

def mark_reminder_sent(reminder_id: int, sent_at: Optional[datetime]=None) -> None:
    return mark_reminder_sent_impl(reminder_id, sent_at, deps=_build_storage_write_deps())

def mark_reminder_acked(reminder_id: int) -> None:
    return mark_reminder_acked_impl(reminder_id, deps=_build_storage_write_deps())

def mark_nudge_sent(reminder_id: int) -> None:
    return mark_nudge_sent_impl(reminder_id, deps=_build_storage_write_deps())

def create_recurring_template(chat_id: int, text: str, pattern_type: str, payload: Dict[str, Any], time_hour: int, time_minute: int, created_by: Optional[int]) -> int:
    return create_recurring_template_impl(chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, deps=_build_storage_write_deps())


def _build_storage_read_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        json=json,
        sqlite3=sqlite3,
    )

def get_due_reminders(now: datetime) -> List[Reminder]:
    return get_due_reminders_impl(now, _build_storage_read_deps())

def get_reminder(reminder_id: int) -> Optional[Reminder]:
    return get_reminder_impl(reminder_id, _build_storage_read_deps())

def get_active_reminders_created_by_for_chat(chat_id: int, created_by: int) -> List[Dict[str, Any]]:
    return get_active_reminders_created_by_for_chat_impl(chat_id, created_by, _build_storage_read_deps())

def get_active_reminders_for_chat(chat_id: int) -> List[Dict[str, Any]]:
    return get_active_reminders_for_chat_impl(chat_id, _build_storage_read_deps())

def get_reminder_row(rid: int) -> Optional[Dict[str, Any]]:
    return get_reminder_row_impl(rid, _build_storage_read_deps())

def get_recurring_template_row(tpl_id: int) -> Optional[Dict[str, Any]]:
    return get_recurring_template_row_impl(tpl_id, _build_storage_read_deps())

def get_reminders_by_template_id(template_id: int, chat_id: int) -> List[Dict[str, Any]]:
    return get_reminders_by_template_id_impl(template_id, chat_id, _build_storage_read_deps())

def get_unacked_sent_before(dt: datetime) -> List[Dict[str, Any]]:
    return get_unacked_sent_before_impl(dt, _build_storage_read_deps())

def get_recurring_template(template_id: int) -> Optional[Dict[str, Any]]:
    return get_recurring_template_impl(template_id, _build_storage_read_deps())


from datetime import datetime
from typing import Optional


def _build_storage_delete_restore_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        add_reminder=add_reminder,
        compute_next_occurrence=compute_next_occurrence,
        get_recurring_template_row=get_recurring_template_row,
        get_reminder_row=get_reminder_row,
        get_reminders_by_template_id=get_reminders_by_template_id,
        sqlite3=sqlite3,
    )

def delete_reminders(reminder_ids: List[int], chat_id: int) -> int:
    return delete_reminders_impl(reminder_ids, chat_id, deps=_build_storage_delete_restore_deps())

def delete_recurring_one_instance_and_reschedule(rid: int, chat_id: int) -> Optional[Dict[str, Any]]:
    return delete_recurring_one_instance_and_reschedule_impl(rid, chat_id, deps=_build_storage_delete_restore_deps())

def delete_single_reminder_row(reminder_id: int, chat_id: int) -> int:
    return delete_single_reminder_row_impl(reminder_id, chat_id, deps=_build_storage_delete_restore_deps())

def deactivate_recurring_template(template_id: int) -> int:
    return deactivate_recurring_template_impl(template_id, deps=_build_storage_delete_restore_deps())

def activate_recurring_template(template_id: int) -> int:
    return activate_recurring_template_impl(template_id, deps=_build_storage_delete_restore_deps())

def delete_recurring_series(template_id: int, chat_id: int) -> int:
    return delete_recurring_series_impl(template_id, chat_id, deps=_build_storage_delete_restore_deps())

def delete_reminder_with_snapshot(rid: int, target_chat_id: int) -> Optional[Dict[str, Any]]:
    return delete_reminder_with_snapshot_impl(rid, target_chat_id, deps=_build_storage_delete_restore_deps())

def delete_single_reminder_with_snapshot(rid: int, target_chat_id: int) -> Optional[Dict[str, Any]]:
    return delete_single_reminder_with_snapshot_impl(rid, target_chat_id, deps=_build_storage_delete_restore_deps())

def delete_recurring_series_with_snapshot(template_id: int, target_chat_id: int) -> Optional[Dict[str, Any]]:
    return delete_recurring_series_with_snapshot_impl(template_id, target_chat_id, deps=_build_storage_delete_restore_deps())

def restore_deleted_snapshot(snapshot: Dict[str, Any]) -> Optional[Any]:
    return restore_deleted_snapshot_impl(snapshot, deps=_build_storage_delete_restore_deps())


def make_undo_token() -> str:
    # короткий токен, чтобы callback_data была маленькой
    return secrets.token_urlsafe(8)


def _build_storage_aliases_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        TZ=TZ,
        sqlite3=sqlite3,
    )

def set_chat_alias(alias: str, chat_id: int, title: Optional[str], created_by: int=0) -> None:
    return set_chat_alias_impl(alias, chat_id, title, created_by, deps=_build_storage_aliases_deps())

def get_chat_id_by_alias(alias: str, created_by: int=0) -> Optional[int]:
    return get_chat_id_by_alias_impl(alias, created_by, deps=_build_storage_aliases_deps())

def get_all_aliases(created_by: int):
    return get_all_aliases_impl(created_by, deps=_build_storage_aliases_deps())

def get_user_alias(alias: str, created_by: int) -> Optional[Dict[str, Any]]:
    return get_user_alias_impl(alias, created_by, deps=_build_storage_aliases_deps())

def set_user_alias(alias: str, user_id: int, chat_id: int, username: Optional[str], created_by: int) -> None:
    return set_user_alias_impl(alias, user_id, chat_id, username, created_by, deps=_build_storage_aliases_deps())

def get_user_alias_chat_id(alias: str, created_by: int=0) -> Optional[int]:
    return get_user_alias_chat_id_impl(alias, created_by, deps=_build_storage_aliases_deps())

def get_all_user_aliases(created_by: int) -> List[Tuple[str, int]]:
    return get_all_user_aliases_impl(created_by, deps=_build_storage_aliases_deps())

def delete_chat_alias(alias: str, created_by: int) -> bool:
    return delete_chat_alias_impl(alias, created_by, deps=_build_storage_aliases_deps())

def delete_user_alias(alias: str, created_by: int) -> bool:
    return delete_user_alias_impl(alias, created_by, deps=_build_storage_aliases_deps())

def rename_chat_alias(old_alias: str, new_alias: str, created_by: int) -> bool:
    return rename_chat_alias_impl(old_alias, new_alias, created_by, deps=_build_storage_aliases_deps())

def rename_user_alias(old_alias: str, new_alias: str, created_by: int) -> bool:
    return rename_user_alias_impl(old_alias, new_alias, created_by, deps=_build_storage_aliases_deps())

def get_private_chat_id_by_username(username: str) -> Optional[int]:
    return get_private_chat_id_by_username_impl(username, deps=_build_storage_aliases_deps())

def _set_chat_alias_accepts_created_by() -> bool:
    try:
        return "created_by" in inspect.signature(set_chat_alias).parameters
    except (TypeError, ValueError):
        return True


def set_chat_alias_for_user(alias: str, chat_id: int, title: Optional[str], created_by: int = 0) -> None:
    return set_chat_alias(alias=alias, chat_id=chat_id, title=title, **({"created_by": created_by} if _set_chat_alias_accepts_created_by() else {}))


# ===== Повторяющиеся шаблоны =====


# ===== SNOOZE клавиатуры =====

def _build_keyboard_builder_proxy_deps():
    return SimpleNamespace(
        InlineKeyboardButton=InlineKeyboardButton,
        InlineKeyboardMarkup=InlineKeyboardMarkup,
        get_reminder=get_reminder,
        keyboard_builders=keyboard_builders,
    )

def build_created_reminder_actions_keyboard_for_reminder(reminder_id: int) -> Optional[InlineKeyboardMarkup]:
    reminder = get_reminder(reminder_id)
    return None if reminder is None else build_created_reminder_actions_keyboard(reminder_id, is_recurring=bool(getattr(reminder, "template_id", None)))

def _sync_keyboard_builder_classes() -> None:
    return _sync_keyboard_builder_classes_impl(deps=_build_keyboard_builder_proxy_deps())

def build_list_delete_keyboard(reminder_id: int):
    return build_list_delete_keyboard_impl(reminder_id, deps=_build_keyboard_builder_proxy_deps())

def build_recurring_delete_choice_keyboard(reminder_id: int, template_id: int):
    return build_recurring_delete_choice_keyboard_impl(reminder_id, template_id, deps=_build_keyboard_builder_proxy_deps())

def build_created_reminder_actions_keyboard(reminder_id: int, is_recurring: bool=False):
    return build_created_reminder_actions_keyboard_impl(reminder_id, is_recurring, deps=_build_keyboard_builder_proxy_deps())

def build_created_reschedule_keyboard(reminder_id: int):
    return build_created_reschedule_keyboard_impl(reminder_id, deps=_build_keyboard_builder_proxy_deps())

def build_snooze_keyboard(reminder_id: int):
    return build_snooze_keyboard_impl(reminder_id, deps=_build_keyboard_builder_proxy_deps())

def build_group_reminder_keyboard(reminder_id: int):
    return build_group_reminder_keyboard_impl(reminder_id, deps=_build_keyboard_builder_proxy_deps())

def build_self_remind_mode_keyboard(reminder_id: int):
    return build_self_remind_mode_keyboard_impl(reminder_id, deps=_build_keyboard_builder_proxy_deps())

def build_self_remind_choice_keyboard(reminder_id: int):
    return build_self_remind_choice_keyboard_impl(reminder_id, deps=_build_keyboard_builder_proxy_deps())

def build_self_remind_event_before_keyboard(reminder_id: int):
    return build_self_remind_event_before_keyboard_impl(reminder_id, deps=_build_keyboard_builder_proxy_deps())

def build_custom_date_keyboard(reminder_id: int, year: Optional[int]=None, month: Optional[int]=None, callback_prefix: str='snooze'):
    return build_custom_date_keyboard_impl(reminder_id, year, month, callback_prefix, deps=_build_keyboard_builder_proxy_deps())

def build_custom_time_keyboard(reminder_id: int, date_str: str, callback_prefix: str='snooze'):
    return build_custom_time_keyboard_impl(reminder_id, date_str, callback_prefix, deps=_build_keyboard_builder_proxy_deps())


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
    return parse_renamealias_args_impl(args)

def _rest_starts_like_datetime(s: str) -> bool:
    return _rest_starts_like_datetime_impl(s)

def _strip_leading_token_in_group(raw_args: str) -> Tuple[str, bool]:
    return _strip_leading_token_in_group_impl(raw_args)

def _format_bulk_result(*, created: int, failed: int, error_lines):
    return _format_bulk_result_impl(created=created, failed=failed, error_lines=error_lines)


async def renamealias_command(update: Update, context: CTX) -> None:
    await handle_renamealias_command(update, context, _build_alias_settings_command_deps())


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


def _build_created_action_callback_deps():
    return SimpleNamespace(
        MSG_INVALID_REMINDER_ID=MSG_INVALID_REMINDER_ID,
        MSG_REMINDER_NOT_FOUND=MSG_REMINDER_NOT_FOUND,
        MSG_RESCHEDULE_OPEN_FAILED_TEXT=MSG_RESCHEDULE_OPEN_FAILED_TEXT,
        build_created_reminder_actions_keyboard_for_reminder=build_created_reminder_actions_keyboard_for_reminder,
        build_created_reschedule_keyboard=build_created_reschedule_keyboard,
        build_custom_date_keyboard=build_custom_date_keyboard,
        get_reminder=get_reminder,
        logger=logger,
        answer_created_action_reminder_missing=_answer_created_action_reminder_missing,
        ensure_created_action_reminder_exists=_ensure_created_action_reminder_exists,
    )


async def _answer_created_action_reminder_missing(query) -> None:
    await answer_created_action_reminder_missing_impl(query, _build_created_action_callback_deps())


async def _ensure_created_action_reminder_exists(query, reminder_id: int) -> bool:
    return await ensure_created_action_reminder_exists_impl(query, reminder_id, _build_created_action_callback_deps())


async def created_reschedule_callback(update: Update, context: CTX) -> None:
    await handle_created_reschedule_callback(update, context, _build_created_action_callback_deps())


async def created_snooze_custom_callback(update: Update, context: CTX) -> None:
    await handle_created_snooze_custom_callback(update, context, _build_created_action_callback_deps())


async def created_snooze_cancel_callback(update: Update, context: CTX) -> None:
    await handle_created_snooze_cancel_callback(update, context, _build_created_action_callback_deps())


async def created_back_callback(update: Update, context: CTX) -> None:
    await handle_created_back_callback(update, context, _build_created_action_callback_deps())


def _build_created_snooze_callback_deps():
    return build_created_snooze_callback_deps(globals())

async def created_snooze_callback(update: Update, context: CTX) -> None:
    await handle_created_snooze_callback(update, context, _build_created_snooze_callback_deps())


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


def _build_app_lifecycle_deps():
    return SimpleNamespace(
        BACKGROUND_WORKER_TASK_KEYS=BACKGROUND_WORKER_TASK_KEYS,
        init_db=init_db,
        logger=logger,
        migrate_alias_tables_to_owner_scope=migrate_alias_tables_to_owner_scope,
        reminders_nudge_worker=reminders_nudge_worker,
        reminders_worker=reminders_worker,
    )

def _start_background_worker(application: Application, task_key: str, coro_factory) -> asyncio.Task:
    return _start_background_worker_impl(application, task_key, coro_factory, deps=_build_app_lifecycle_deps())

async def _cancel_background_worker(task: asyncio.Task) -> None:
    return await _cancel_background_worker_impl(task, deps=_build_app_lifecycle_deps())

async def post_init(application: Application) -> None:
    return await post_init_impl(application, deps=_build_app_lifecycle_deps())

async def post_shutdown(application: Application) -> None:
    return await post_shutdown_impl(application, deps=_build_app_lifecycle_deps())


def _build_storage_nudges_deps():
    return SimpleNamespace(
        DB_PATH=DB_PATH,
        sqlite3=sqlite3,
    )


def _nudge_threshold_minutes(nudge_count: int) -> Optional[int]:
    return _nudge_threshold_minutes_impl(nudge_count)

def get_due_nudges(now: datetime) -> List[Dict[str, Any]]:
    return get_due_nudges_impl(now, deps=_build_storage_nudges_deps())

def increment_nudge_count(reminder_id: int) -> None:
    return increment_nudge_count_impl(reminder_id, deps=_build_storage_nudges_deps())

def exhaust_nudges(reminder_id: int) -> None:
    return exhaust_nudges_impl(reminder_id, deps=_build_storage_nudges_deps())


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
