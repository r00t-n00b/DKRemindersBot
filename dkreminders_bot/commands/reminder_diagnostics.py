"""Private read-only diagnostics with independent, short-lived pagination."""

import secrets
import sqlite3

from dkreminders_bot.settings.timezone_features import InlineKeyboardButton, InlineKeyboardMarkup, _edit_or_reply
from dkreminders_bot.ui.messages import DIAGNOSTICS_NOTICES as N, DIAGNOSTICS_TEXT as T
from dkreminders_bot.ui.reminder_diagnostics import diagnostic_page

SESSION_KEY = "reminder_diagnostics"
SESSION_TTL = 30 * 60


def _identity(update):
    query = getattr(update, "callback_query", None)
    message = getattr(query, "message", None) if query else getattr(update, "effective_message", None)
    user = getattr(query, "from_user", None) if query else getattr(update, "effective_user", None)
    chat = getattr(message, "chat", None) or getattr(update, "effective_chat", None)
    return user, chat, message


def _private(user, chat):
    return bool(user and chat and chat.type == "private" and chat.id == user.id)


async def _render(update, context, deps, target, page=0, *, query=None):
    user, chat, message = _identity(update)
    rows = deps.store.recent(user.id, target)
    text, page, pages = diagnostic_page(rows, page, target=target, secrets=deps.sensitive_values)
    token = secrets.token_hex(8)
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(T["previous"], callback_data=f"diag:{token}:{page-1}"))
    if page+1 < pages:
        navigation.append(InlineKeyboardButton(T["next"], callback_data=f"diag:{token}:{page+1}"))
    keyboard_rows = [navigation] if navigation else []
    keyboard_rows.append([InlineKeyboardButton(T["refresh"], callback_data=f"diag:{token}:refresh")])
    markup = InlineKeyboardMarkup(keyboard_rows)
    if query:
        await query.answer()
        sent = await _edit_or_reply(query, text, reply_markup=markup, parse_mode=None)
    else:
        sent = await deps.safe_reply(message, text, reply_markup=markup, parse_mode=None)
    message_id = getattr(sent, "message_id", None) or (message.message_id if query else None)
    if message_id is not None:
        context.user_data[SESSION_KEY] = {
            "token": token, "owner": user.id, "chat_id": chat.id, "message_id": message_id,
            "target": target, "page": page, "expires_at": deps.get_now().timestamp() + SESSION_TTL,
        }


async def handle_diagnostics_command(update, context, deps):
    user, chat, message = _identity(update)
    if message is None:
        return
    if not _private(user, chat):
        await deps.safe_reply(message, N["private"])
        return
    target = " ".join(context.args or []).strip() or None
    try:
        await _render(update, context, deps, target)
    except ValueError as exc:
        await deps.safe_reply(message, str(exc), parse_mode=None)
    except sqlite3.Error:
        deps.logger.exception("Reading reminder diagnostics failed")
        await deps.safe_reply(message, N["storage_error"])


async def handle_diagnostics_callback(update, context, deps):
    query = getattr(update, "callback_query", None)
    if query is None:
        return
    user, chat, message = _identity(update)
    if not _private(user, chat):
        await query.answer(N["private"], show_alert=True)
        return
    parts = (query.data or "").split(":")
    session = context.user_data.get(SESSION_KEY)
    if (len(parts) != 3 or parts[0] != "diag" or not session
        or session["token"] != parts[1] or session["owner"] != user.id
        or session["chat_id"] != chat.id or session["message_id"] != message.message_id
        or session["expires_at"] <= deps.get_now().timestamp()):
        await query.answer(N["stale"], show_alert=True)
        return
    try:
        page = session["page"] if parts[2] == "refresh" else int(parts[2])
        if page < 0:
            raise ValueError()
    except (TypeError, ValueError):
        await query.answer(N["stale"], show_alert=True)
        return
    try:
        await _render(update, context, deps, session["target"], page, query=query)
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
    except sqlite3.Error:
        deps.logger.exception("Reading reminder diagnostics failed")
        await query.answer(N["storage_error"], show_alert=True)
