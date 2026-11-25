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
            uid, int(data.get("unfinished_page", 0)), target=data.get("unfinished_target"),
        )
    except ValueError:
        data["unfinished_ids"] = []
        return T["target_changed"], keyboard(session, [[(T["back"], "home")]])
    except sqlite3.Error:
        data["unfinished_ids"] = []
        logger.exception("Reading unfinished reminders failed")
        return T["error"], keyboard(session, [
            [(T["refresh"], "unfinished_page:" + str(data.get("unfinished_page", 0)))], [(T["back"], "home")],
        ])
    data["unfinished_page"] = number
    data["unfinished_ids"] = [row["id"] for row in reminders]
    lines = [
        T["title"],
        T["summary"].format(total=total),
        T["target_scope"].format(name=_truncate_list_reminder_text(data["unfinished_target"]["alias"], limit=60)) if data.get("unfinished_target") else T["scope"],
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
    completion_buttons = [
        (T["complete"].format(number=number*PAGE_SIZE+i+1), f"u_done:{row['id']}")
        for i, row in enumerate(reminders)
    ]
    rows = [completion_buttons[i:i+4] for i in range(0, len(completion_buttons), 4)]
    if navigation:
        rows.append(navigation)
    rows += [[(T["refresh"], f"unfinished_page:{number}")], [(T["back"], "home")]]
    return "\n\n".join(lines), keyboard(session, rows)


async def start_unfinished(update, context, deps):
    from dkreminders_bot.settings.settings_menu import _identity, _personal, start_settings
    from dkreminders_bot.ui.messages import SETTINGS_NOTICES

    user, chat, message = _identity(update)
    if not _personal(user, chat):
        if message is not None:
            await message.reply_text(SETTINGS_NOTICES["private"])
        return
    name = " ".join(context.args or []).strip()
    target = None
    if name:
        try:
            target = deps.unfinished_store.resolve_alias(user.id, name)
        except ValueError as exc:
            await message.reply_text(str(exc), parse_mode=None)
            return
        except sqlite3.Error:
            logger.exception("Resolving unfinished recipient failed")
            await message.reply_text(T["error"])
            return
    await start_settings(
        update, context, deps, page="unfinished", initial_data={"unfinished_target": target},
    )
