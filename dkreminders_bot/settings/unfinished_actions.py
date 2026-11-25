"""Finish a delivered reminder selected from a personal unfinished list."""

import logging
import sqlite3

from dkreminders_bot.ui.messages import UNFINISHED_TEXT as T, SETTINGS_NOTICES as N

logger = logging.getLogger(__name__)


async def complete_unfinished(update, context, deps, session, args):
    from dkreminders_bot.settings.settings_menu import _render

    query = update.callback_query
    try:
        reminder_id = int(args[0])
        if session["data"].get("page") != "unfinished" or reminder_id not in session["data"].get("unfinished_ids", []):
            raise ValueError()
    except (ValueError, TypeError, IndexError):
        await query.answer(N["stale"], show_alert=True)
        return
    try:
        result = deps.finish_unfinished(reminder_id, session["user_id"], target=session["data"].get("unfinished_target"))
    except (sqlite3.Error, ValueError):
        logger.exception("Finishing an unfinished reminder failed")
        await query.answer(T["complete_error"], show_alert=True)
        return
    if result["status"] == "forbidden":
        await query.answer(N["stale"], show_alert=True)
        return
    notice = T["completed"] if result["status"] == "applied" else T["processed"]
    await query.answer(notice)
    if result["status"] == "applied":
        try:
            await deps.finish_unfinished_messages(reminder_id, context, result)
        except Exception:
            # Completion is committed. A Telegram cleanup error must not undo it.
            logger.exception("Updating completed reminder messages failed")
    await _render(update, context, deps, session, query=query)
