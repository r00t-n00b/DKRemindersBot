"""Persistent interval-mode chooser and transactional completion callbacks."""

from datetime import datetime
from zoneinfo import ZoneInfo

from dkreminders_bot.callbacks.callback_contracts import cb_recurrence_mode
from dkreminders_bot.settings.timezone_features import timezone_label
from dkreminders_bot.ui import messages
from dkreminders_bot.ui.presentation import format_interval_duration
from dkreminders_bot.ui.keyboards import InlineKeyboardButton, InlineKeyboardMarkup


def mode_keyboard(token):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕒 По расписанию", callback_data=cb_recurrence_mode(token, "schedule"))],
        [InlineKeyboardButton("✅ После выполнения", callback_data=cb_recurrence_mode(token, "completion"))],
        [InlineKeyboardButton("Отмена", callback_data=cb_recurrence_mode(token, "cancel"))],
    ])


async def request_interval_choice(*, store, spec, now, message, safe_reply):
    token = store.save_choice(spec, now)
    await safe_reply(message, messages.MSG_RECURRENCE_MODE_PROMPT.format(
        text=spec["text"], interval=format_interval_duration(spec["payload"]),
    ), reply_markup=mode_keyboard(token))


async def handle_mode_choice(update, context, *, store, deps):
    query = update.callback_query
    if query is None:
        return
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        await query.answer(messages.MSG_RECURRENCE_EXPIRED, show_alert=True)
        return
    chat_id = getattr(getattr(query.message, "chat", None), "id", None)
    actor = getattr(getattr(query, "from_user", None), "id", None)
    try:
        result = store.choose(parts[1], parts[2], actor, chat_id, deps.get_now())
    except Exception:
        deps.logger.exception("Failed to choose interval recurrence mode")
        await query.answer(messages.MSG_RECURRENCE_CHOICE_FAILED, show_alert=True)
        return
    status = result["status"]
    if status != "created":
        text = {
            "forbidden": messages.MSG_RECURRENCE_FORBIDDEN,
            "processed": messages.MSG_RECURRENCE_PROCESSED,
            "cancelled": messages.MSG_RECURRENCE_CANCELLED,
        }.get(status, messages.MSG_RECURRENCE_EXPIRED)
        await query.answer(text, show_alert=status != "cancelled")
        if status == "cancelled":
            await query.edit_message_text(text)
        return
    spec, rid = result["spec"], result["reminder_id"]
    when = result["first_dt"].astimezone(ZoneInfo(spec["timezone_name"]))
    text = deps.format_created_recurring_reminder_text(
        f"{when:%d.%m %H:%M} {timezone_label(spec['timezone_name'])}",
        spec["text"], deps.format_recurring_human("interval", result["payload"]),
        chat_alias=spec.get("used_alias"),
    )
    # Persist tracking before a best-effort UI edit: a Telegram error must not
    # make an already committed creation look unselected or create it twice.
    message_id = getattr(query.message, "message_id", None)
    if message_id is not None:
        deps.register_reminder_message(reminder_id=rid, chat_id=chat_id, message_id=message_id, kind="created")
    await query.answer(messages.MSG_RECURRENCE_SELECTED)
    try:
        await query.edit_message_text(text, reply_markup=deps.build_created_reminder_actions_keyboard_for_reminder(rid))
    except Exception:
        deps.logger.exception("Failed to update selected recurrence prompt")
        await deps.safe_reply(query.message, text, reply_markup=deps.build_created_reminder_actions_keyboard_for_reminder(rid))


async def handle_completion_callback(update, context, *, store, deps):
    """Return False for legacy series; keep their existing callback paths intact."""
    query = getattr(update, "callback_query", None)
    data = (getattr(query, "data", None) or "").split(":")
    if len(data) < 2 or data[0] not in {"done", "snooze", "snooze_picktime"}:
        return False
    try:
        rid = int(data[1])
    except ValueError:
        return False
    row = store.completion_reminder(rid)
    if row is None:
        return False
    actor = getattr(getattr(query, "from_user", None), "id", None)
    chat_id = getattr(getattr(query.message, "chat", None), "id", None)
    owner = row["chat_id"] if row["chat_id"] > 0 else row["created_by"]
    if actor != owner or chat_id != row["chat_id"]:
        await query.answer(messages.MSG_RECURRENCE_FORBIDDEN, show_alert=True)
        return True
    if row["acked"] or not row["active"] or not row["delivered"]:
        await query.answer(messages.MSG_RECURRENCE_PROCESSED, show_alert=True)
        return True
    if data[0] == "snooze" and len(data) == 3 and data[2] == "custom":
        return False  # Existing picker is navigation only; no acknowledgement.
    now = deps.get_now()
    new_dt = None
    try:
        if data[0] == "snooze":
            if len(data) != 3:
                raise ValueError("Invalid snooze callback")
            new_dt = deps.compute_snooze_target_time(data[2], now, default_time=deps.get_user_default_time(actor))
        elif data[0] == "snooze_picktime":
            if len(data) != 5:
                raise ValueError("Invalid snooze time")
            zone = ZoneInfo(row["series_timezone"]) if row["series_timezone"] else now.tzinfo
            new_dt = datetime.fromisoformat(f"{data[2]}T{data[3]}:{data[4]}").replace(tzinfo=zone)
            if new_dt.timestamp() <= now.timestamp():
                await query.answer(deps.MSG_RESCHEDULE_PAST_TIME, show_alert=True)
                return True
    except ValueError:
        await query.answer(deps.MSG_RESCHEDULE_BAD_DATETIME, show_alert=True)
        return True
    reminder = deps.get_reminder(rid)
    result = store.transition(rid, actor_id=actor, chat_id=chat_id, now=now, snooze_until=new_dt)
    if result["status"] != "applied":
        await query.answer(messages.MSG_RECURRENCE_PROCESSED, show_alert=True)
        return True
    common = dict(
        query=query, context=context, mark_reminder_acked=lambda rid: None,
        clear_reminder_message_keyboards=deps.clear_reminder_message_keyboards,
        delete_old_snoozed_reminder_messages=deps.delete_old_snoozed_reminder_messages,
        delete_other_reminder_messages=deps.delete_other_reminder_messages,
    )
    if new_dt is not None:
        await deps.apply_snooze_to_reminder(
            reminder=reminder, new_dt=new_dt, add_reminder=lambda **kwargs: None,
            format_snoozed_reminder_text=deps.format_snoozed_reminder_text,
            format_snoozed_answer_text=deps.format_snoozed_answer_text, **common,
        )
    else:
        next_at = result["next_at"]
        await deps.handle_done_callback(
            reminder_id=rid, get_reminder=deps.get_reminder,
            format_completed_reminder_text=lambda text: deps.format_completed_reminder_text(text) + "\n\n" + messages.MSG_RECURRENCE_NEXT.format(when=f"{next_at:%d.%m %H:%M} {next_at:%Z}"),
            **common,
        )
    return True
