"""Alias screens and creation wizard inside the existing private settings session."""

import logging
import secrets
import sqlite3
from datetime import datetime

from dkreminders_bot.domain.alias_names import alias_key, validate_alias_name
from dkreminders_bot.ui.presentation import build_active_reminders_list_response
from dkreminders_bot.ui.messages import (
    ALIAS_MENU_TEXT as TEXT, ALIAS_MENU_LABELS as L, ALIAS_MENU_NOTICES as N,
    SETTINGS_NOTICES as SN,
)

try:
    from telegram import KeyboardButton, KeyboardButtonRequestChat, ReplyKeyboardMarkup, ReplyKeyboardRemove
except ImportError:
    class KeyboardButtonRequestChat:
        def __init__(self, request_id, chat_is_channel, **kwargs):
            self.request_id, self.chat_is_channel = request_id, chat_is_channel
            self.bot_is_member = kwargs.get("bot_is_member")

    class KeyboardButton:
        def __init__(self, text, **kwargs):
            self.text, self.request_chat = text, kwargs.get("request_chat")

    class ReplyKeyboardMarkup:
        def __init__(self, keyboard, **kwargs):
            self.keyboard = keyboard

    class ReplyKeyboardRemove:
        def __init__(self, **kwargs):
            self.remove_keyboard = True


logger = logging.getLogger(__name__)

PAGE_SIZE = 8


def _clip(value, limit=140):
    value = str(value or "")
    return value if len(value) <= limit else value[:limit-1] + "…"


def target_label(row):
    if row.get("kind") == "user" or "user_id" in row:
        return "@" + row["username"] if row.get("username") else str(row["chat_id"])
    return _clip(row.get("title") or row["chat_id"])


def alias_view(session, deps, keyboard):
    data, uid = session["data"], session["user_id"]
    page = data["page"]
    if page == "aliases":
        entries = deps.alias_menu_store.aliases(uid)
        pages = max(1, (len(entries) + PAGE_SIZE-1)//PAGE_SIZE)
        number = max(0, min(int(data.get("alias_page", 0)), pages-1))
        data["alias_page"] = number
        data["alias_items"] = entries[number*PAGE_SIZE:(number+1)*PAGE_SIZE]
        rows = []
        previous_kind = None
        for i, r in enumerate(data["alias_items"]):
            if r["kind"] != previous_kind:
                rows.append([(L["section_" + r["kind"]], "a_section:" + r["kind"])])
                previous_kind = r["kind"]
            rows.append([(("👤 " if r["kind"] == "user" else "💬 ") + _clip(r["alias"], 48), f"a_open:{i}")])
        navigation = []
        if number:
            navigation.append((L["previous"], f"a_page:{number-1}"))
        if number+1 < pages:
            navigation.append((L["next"], f"a_page:{number+1}"))
        if navigation:
            rows.append(navigation)
        rows += [[(L["add"], "a_add")], [(L["back"], "home")]]
        text = TEXT["list"].format(page=number+1, pages=pages, empty=SN["none_aliases"] if not entries else "")
    elif page == "alias_detail":
        r = data["alias_selected"]
        text = TEXT["detail"].format(kind=L[r["kind"]], name=_clip(r["alias"], 100), target=target_label(r))
        rows = [[(L["reminders"], "a_reminders")], [(L["rename"], "a_rename")], [(L["delete"], "a_delete")], [(L["aliases"], "a_list")]]
    elif page == "alias_reminders":
        selected = data["alias_selected"]
        reminders, number, pages, total = deps.alias_menu_store.reminder_page(
            uid, selected, int(data.get("alias_reminder_page", 0)),
        )
        data["alias_reminder_page"] = number
        header = TEXT["reminders"].format(name=_clip(selected["alias"], 100), page=number+1, pages=pages, count=total)
        if reminders:
            text, _, _ = build_active_reminders_list_response(
                reminders, header=header, now_local=deps.get_now(),
                list_delete_keyboard_builder=lambda count: None,
            )
        else:
            text = header + "\n\n" + TEXT["reminders_empty"]
        navigation = []
        if number:
            navigation.append((L["previous"], f"a_reminder_page:{number-1}"))
        if number+1 < pages:
            navigation.append((L["next"], f"a_reminder_page:{number+1}"))
        rows = [navigation] if navigation else []
        rows += [[(L["refresh"], "a_reminder_page:" + str(number))], [(L["alias_back"], "a_detail")]]
    elif page == "alias_type":
        text = TEXT["type"]
        rows = [[(L["user"], "a_new:user")], [(L["chat"], "a_new:chat")], [(L["aliases"], "a_list")]]
    elif page == "alias_group":
        text = TEXT["group"]
        rows = [[(L["choose_group"], "a_group")], [(L["cancel"], "a_cancel")]]
    elif page == "alias_confirm":
        draft = data["alias_wizard"]
        operation = draft["op"]
        source = draft.get("selected") or draft.get("target")
        text = TEXT[operation].format(name=_clip(draft.get("name") or source["alias"], 100), old=_clip(source.get("alias"), 100), target=target_label(source))
        label = L["save"] if operation == "create" else L[operation+"_confirm"]
        rows = [[(label, "a_commit")], [(L["cancel"], "a_cancel")]]
    else:
        raise ValueError(SN["stale"])
    return text, keyboard(session, rows)


async def _remove_picker(message, text=SN["cancelled"]):
    await message.reply_text(text, reply_markup=ReplyKeyboardRemove())


def _same_session(deps, session, *, request_id=None):
    current = deps.settings_store.session(session["user_id"], deps.get_now())
    if current is None or current["token"] != session["token"] or current["data"].get("revision") != session["data"].get("revision") or current["_snapshot"] != session["_snapshot"]:
        return False
    return request_id is None or current["data"].get("alias_request") == request_id


async def _group_target(bot, chat_id):
    if type(chat_id) is not int or chat_id >= 0:
        raise ValueError(N["group_unavailable"])
    try:
        chat = await bot.get_chat(chat_id)
        chat_type = getattr(chat.type, "value", chat.type)
        if chat.id != chat_id or chat_type not in {"group", "supergroup"}:
            raise ValueError()
        member = await bot.get_chat_member(chat_id, bot.id)
        status = getattr(member.status, "value", member.status)
        if status not in {"member", "administrator", "creator"} and not (status == "restricted" and getattr(member, "is_member", False)):
            raise ValueError()
    except Exception as exc:
        raise ValueError(N["group_unavailable"]) from exc
    return {"chat_id": chat_id, "title": getattr(chat, "title", None)}


async def _request_group(update, context, deps, session):
    from dkreminders_bot.settings.settings_menu import _page, _render, _identity
    request_id = secrets.randbelow(2**31-1) + 1
    session["data"]["alias_request"] = request_id
    _page(session, "alias_group")
    query = getattr(update, "callback_query", None)
    if not await _render(update, context, deps, session, query=query):
        return
    _, _, message = _identity(update)
    keyboard = ReplyKeyboardMarkup([[KeyboardButton(L["choose_group"], request_chat=KeyboardButtonRequestChat(
        request_id=request_id, chat_is_channel=False, bot_is_member=True,
    ))]], resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text(TEXT["group"], reply_markup=keyboard)


async def alias_action(action, args, update, context, deps, session):
    from dkreminders_bot.settings.settings_menu import _page, _render, _ask
    data, uid = session["data"], session["user_id"]
    query = update.callback_query
    notice = None
    try:
        if action == "a_section" and data["page"] == "aliases" and args[0] in {"chat", "user"}:
            await query.answer(L["section_" + args[0]])
            return
        elif action == "a_list":
            data.pop("alias_wizard", None)
            _page(session, "aliases")
        elif action == "a_page":
            number = int(args[0])
            if number < 0:
                raise ValueError(SN["stale"])
            data["alias_page"] = number
            _page(session, "aliases")
        elif action == "a_open":
            index = int(args[0])
            if not 0 <= index < len(data.get("alias_items", [])):
                raise ValueError(SN["stale"])
            data["alias_selected"] = deps.alias_menu_store.current(uid, data["alias_items"][index])
            _page(session, "alias_detail")
        elif action in {"a_reminders", "a_reminder_page", "a_detail"}:
            if data["page"] not in {"alias_detail", "alias_reminders"}:
                raise ValueError(SN["stale"])
            deps.alias_menu_store.current(uid, data["alias_selected"])
            if action == "a_detail":
                _page(session, "alias_detail")
            else:
                number = 0 if action == "a_reminders" else int(args[0])
                if number < 0 or (action == "a_reminder_page" and data["page"] != "alias_reminders"):
                    raise ValueError(SN["stale"])
                data["alias_reminder_page"] = number
                _page(session, "alias_reminders")
            await _render(update, context, deps, session, query=query)
            await query.answer()
            return
        elif action == "a_add":
            data.pop("alias_wizard", None)
            _page(session, "alias_type")
        elif action == "a_new":
            kind = args[0]
            if kind not in {"user", "chat"}:
                raise ValueError(SN["stale"])
            data["alias_wizard"] = {"op": "create", "kind": kind}
            _page(session, "alias_type")
            await query.answer()
            await _ask(update, context, deps, session, "alias_name", query=query)
            return
        elif action in {"a_rename", "a_delete"}:
            selected = deps.alias_menu_store.current(uid, data["alias_selected"])
            data["alias_wizard"] = {"op": "rename" if action == "a_rename" else "delete", "selected": selected}
            if action == "a_rename":
                _page(session, "alias_detail")
                await query.answer()
                await _ask(update, context, deps, session, "alias_name", query=query)
                return
            _page(session, "alias_confirm")
        elif action == "a_group":
            if data.get("alias_wizard", {}).get("kind") != "chat" or not data["alias_wizard"].get("name"):
                raise ValueError(SN["stale"])
            await query.answer()
            await _request_group(update, context, deps, session)
            return
        elif action == "a_cancel":
            data.pop("alias_wizard", None)
            if data.pop("alias_request", None) is not None:
                deps.settings_store.save(session)
                await _remove_picker(query.message)
                if not _same_session(deps, session):
                    return
            _page(session, "aliases")
            notice = SN["cancelled"]
        elif action == "a_commit":
            if data.get("page") != "alias_confirm":
                raise ValueError(SN["stale"])
            draft = data["alias_wizard"]
            if draft["op"] == "create":
                if draft["kind"] == "chat":
                    target = await _group_target(context.bot, draft["target"]["chat_id"])
                    if not _same_session(deps, session):
                        await query.answer(SN["stale"], show_alert=True)
                        return
                else:
                    target = draft["target"]
                deps.alias_menu_store.create(uid, draft["name"], draft["kind"], target, deps.get_now())
                notice = N["created"]
            elif draft["op"] == "rename":
                deps.alias_menu_store.rename(uid, draft["selected"], draft["name"])
                notice = N["renamed"]
            elif draft["op"] == "delete":
                deps.alias_menu_store.delete(uid, draft["selected"])
                notice = N["deleted"]
            else:
                raise ValueError(SN["stale"])
            data.pop("alias_wizard", None)
            data.pop("alias_selected", None)
            _page(session, "aliases")
        else:
            raise ValueError(SN["stale"])
    except sqlite3.Error:
        logger.exception("Alias menu storage change failed")
        await query.answer(N["storage_error"], show_alert=True)
        return
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        text = str(exc) if isinstance(exc, ValueError) and str(exc) else SN["stale"]
        if text not in {N["conflict"], N["group_unavailable"], N["target_changed"]}:
            _page(session, "aliases")
            data.pop("alias_wizard", None)
        await query.answer(text, show_alert=True)
        await _render(update, context, deps, session, query=query)
        return
    deps.settings_store.save(session)
    await query.answer(notice)
    await _render(update, context, deps, session, query=query)


async def alias_text(kind, text, update, context, deps, session):
    """Values remain a draft until the confirmation button is pressed."""
    from dkreminders_bot.settings.settings_menu import _page, _render, _ask
    data, uid = session["data"], session["user_id"]
    draft = data["alias_wizard"]
    if kind == "alias_name":
        name = validate_alias_name(text)
        if draft["op"] == "rename":
            deps.alias_menu_store.current(uid, draft["selected"])
            # Full conflict checking repeats atomically at commit time.
            for row in deps.alias_menu_store.aliases(uid):
                if alias_key(row["alias"]) == alias_key(name) and row != draft["selected"]:
                    raise ValueError(N["conflict"])
            draft["name"] = name
            _page(session, "alias_confirm")
        else:
            draft["name"] = deps.alias_menu_store.available(uid, name)
            if draft["kind"] == "user":
                _page(session, "alias_type")
                await _ask(update, context, deps, session, "alias_username")
                return
            await _request_group(update, context, deps, session)
            return
    elif kind == "alias_username" and draft["op"] == "create" and draft["kind"] == "user":
        draft["target"] = deps.alias_menu_store.user_target(text.strip())
        _page(session, "alias_confirm")
    else:
        raise ValueError(SN["stale"])
    await _render(update, context, deps, session)


async def cancel_group_input(update, context, deps, session):
    from dkreminders_bot.settings.settings_menu import _page, _render, _identity
    session["data"].pop("alias_request", None)
    session["data"].pop("alias_wizard", None)
    _page(session, "aliases")
    deps.settings_store.save(session)
    _, _, message = _identity(update)
    await _remove_picker(message)
    await _render(update, context, deps, session)


async def alias_chat_shared(update, context, deps):
    from dkreminders_bot.settings.settings_menu import _identity, _personal, _page, _render
    user, chat, message = _identity(update)
    shared = getattr(message, "chat_shared", None)
    if not _personal(user, chat) or shared is None:
        return
    session = deps.settings_store.session(user.id, deps.get_now(), include_expired=True)
    request_id = getattr(shared, "request_id", None)
    if session is None or datetime.fromisoformat(session["expires_at"]).timestamp() <= deps.get_now().timestamp() or session["data"].get("alias_request") != request_id or session["data"].get("page") != "alias_group":
        if session and session["data"].get("alias_request") == request_id:
            session["data"].pop("alias_request", None)
            deps.settings_store.save(session)
            await _remove_picker(message, N["group_closed"])
        else:
            await message.reply_text(N["group_closed"])
        return
    try:
        target = await _group_target(context.bot, getattr(shared, "chat_id", None))
    except ValueError:
        await message.reply_text(N["group_unavailable"])
        return
    if not _same_session(deps, session, request_id=request_id):
        await message.reply_text(N["group_closed"])
        return
    draft = session["data"]["alias_wizard"]
    draft["target"] = target
    session["data"].pop("alias_request", None)
    _page(session, "alias_confirm")
    deps.settings_store.save(session)
    await _remove_picker(message, N["group_selected"])
    if not _same_session(deps, session):
        return
    await _render(update, context, deps, session)
