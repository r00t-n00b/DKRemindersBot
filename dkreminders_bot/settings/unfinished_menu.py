"""The unfinished list inside the persistent personal settings session."""

from datetime import datetime
import logging
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dkreminders_bot.storage.unfinished_reminders import PAGE_SIZE
from dkreminders_bot.ui.messages import UNFINISHED_TEXT as T
from dkreminders_bot.ui.presentation import _truncate_list_reminder_text

logger = logging.getLogger(__name__)


def _when(row, default_zone):
    zone = row["timezone_name"] or default_zone
    try:
        value = datetime.fromisoformat(row["remind_at"])
        if value.tzinfo is not None:
            value = value.astimezone(ZoneInfo(zone))
        return value.strftime("%d.%m.%Y %H:%M") + " " + zone[:32]
    except (ValueError, ZoneInfoNotFoundError):
        return row["remind_at"][:40]


def unfinished_view(session, deps, keyboard):
    data, uid = session["data"], session["user_id"]
    try:
        reminders, number, pages, total = deps.unfinished_store.page(
            uid, int(data.get("unfinished_page", 0)),
        )
    except sqlite3.Error:
        logger.exception("Reading unfinished reminders failed")
        return T["error"], keyboard(session, [
            [(T["refresh"], "unfinished")], [(T["back"], "home")],
        ])
    data["unfinished_page"] = number
    lines = [
        T["title"],
        T["summary"].format(total=total),
        T["scope"],
        T["page"].format(page=number+1, pages=pages),
    ]
    zone = deps.get_user_timezone_name_raw(uid) or "Europe/Madrid"
    for index, row in enumerate(reminders, start=number*PAGE_SIZE+1):
        if row["chat_id"] == uid:
            target = T["me"]
        elif row["target_alias"]:
            target = _truncate_list_reminder_text(row["target_alias"], limit=40)
        else:
            target = T["person" if row["chat_id"] > 0 else "chat"].format(chat_id=row["chat_id"])
        lines.append(T["row"].format(
            number=index,
            text=_truncate_list_reminder_text(row["text"], limit=100),
            recurring=" 🔁" if row["template_id"] is not None else "",
            status=T["delivered"],
            when=_when(row, zone),
            target=target,
        ))
    if not reminders:
        lines.append(T["empty"])
    navigation = []
    if number:
        navigation.append((T["previous"], f"unfinished_page:{number-1}"))
    if number+1 < pages:
        navigation.append((T["next"], f"unfinished_page:{number+1}"))
    rows = [navigation] if navigation else []
    rows += [[(T["refresh"], f"unfinished_page:{number}")], [(T["back"], "home")]]
    return "\n\n".join(lines), keyboard(session, rows)
