"""Created-reminder delete callback flow."""

from dkreminders_bot.ui.messages import MSG_CREATED_DELETE_ANSWER, MSG_UNDO_BUTTON_REMINDER, msg_created_deleted

from typing import Any, Dict, List, Optional, Tuple


_DEP_NAMES = [
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "MSG_DELETE_FAILED_SHORT",
    "MSG_DELETE_FAILED_TEXT",
    "MSG_REMINDER_ALREADY_DELETED_ALERT",
    "MSG_REMINDER_ALREADY_DELETED_TEXT",
    "build_recurring_delete_choice_keyboard",
    "cb_undo",
    "delete_single_reminder_with_snapshot",
    "dict",
    "format_deleted_human",
    "get_reminder_row",
    "make_undo_token",
]


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


async def handle_created_delete_callback(update, context, deps) -> None:
    _apply_deps(deps)
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

    if int(row.get("delivered", 0) or 0) or int(row.get("acked", 0) or 0):
        await query.answer("Это напоминание уже обработано", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
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
        [[InlineKeyboardButton(MSG_UNDO_BUTTON_REMINDER, callback_data=cb_undo(token))]]
    )

    await query.answer(MSG_CREATED_DELETE_ANSWER)
    await query.edit_message_text(msg_created_deleted(deleted_text), reply_markup=undo_kb)
