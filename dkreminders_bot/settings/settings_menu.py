"""Native Telegram settings: inline menus, reply-scoped custom input, drafts."""

from datetime import datetime
from types import SimpleNamespace

from dkreminders_bot.domain.nudge_policy import DEFAULT_GAPS, MAX_GAPS, parse_interval, validate_gaps
from dkreminders_bot.settings.default_time import parse_default_time_value, format_default_time_value
from dkreminders_bot.settings.timezone_features import InlineKeyboardButton, InlineKeyboardMarkup, _edit_or_reply, _load_settings_alias_lines
from dkreminders_bot.settings.timezone_search import search_timezones
from dkreminders_bot.ui.messages import SETTINGS_MENU_TEXT as TEXT, SETTINGS_MENU_LABELS as L, SETTINGS_INPUT_PROMPTS as PROMPTS, SETTINGS_NOTICES as N, settings_schedule_text
from dkreminders_bot.ui.presentation import format_interval_duration

try:
    from telegram import ForceReply
except ImportError:
    class ForceReply:
        def __init__(self, **kwargs):
            self.force_reply = True


PREFIX = "settings:v2:"


def _identity(update):
    query = getattr(update, "callback_query", None)
    message = getattr(query, "message", None) if query else getattr(update, "effective_message", None)
    user = getattr(update, "effective_user", None) or getattr(query, "from_user", None)
    chat = getattr(message, "chat", None) or getattr(update, "effective_chat", None)
    return user, chat, message


def _personal(user, chat):
    return bool(user and chat and getattr(chat, "type", None) == "private" and chat.id == user.id)


def _duration(minutes):
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    return " ".join(format_interval_duration({"value": n, "unit": u}) for n, u in ((days, "days"), (hours, "hours"), (mins, "minutes")) if n)


def _keyboard(session, rows):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=PREFIX + session["token"] + ":" + str(session["data"].get("revision", 0)) + ":" + action) for label, action in row]
        for row in rows
    ])


def _page(session, page):
    session["data"]["page"] = page
    session["data"].pop("input", None)
    session["prompt_message_id"] = None


def _view(session, deps):
    uid = session["user_id"]
    data = session["data"]
    page = data.get("page", "home")
    config = deps.settings_store.nudges(uid)
    gaps = config["gaps"]
    time = deps.get_user_default_time(uid) or (10, 0)
    values = {"time": format_default_time_value(*time), "zone": deps.get_user_timezone_name_raw(uid) or N["zone_missing"]}
    status = N["active"].format(count=len(gaps)) if config["enabled"] else N["inactive"]
    values.update(nudges=status, status=status, schedule=settings_schedule_text(gaps, lambda p: _duration(p["value"])))
    back = [(L["back"], "home")]
    rows = []
    if page == "home":
        rows = [[(L[key], key)] for key in ("time", "zone", "nudges", "aliases", "list")]
    elif page == "nudges":
        rows = [[(L["sequence"], "sequence")], [(L["off"] if config["enabled"] else L["on"], "off" if config["enabled"] else "on")], back]
    elif page == "sequence":
        draft = validate_gaps(data["draft"])
        values["count"] = len(draft)
        rows = [[(L["count"].format(count=len(draft)), "count")]]
        rows += [[(f"{i+1}. {_duration(n)}", f"gap:{i}")] for i, n in enumerate(draft)]
        rows += [[(L["save"], "save")], [(L["cancel"], "discard")]]
    elif page == "count":
        values["count"] = len(data["draft"])
        rows = [[(("✓ " if n == values["count"] else "") + str(n), f"countset:{n}") for n in range(start, start+3)] for start in (1, 4, 7)]
        rows += [[(L["custom_count"], "input:count")], [(L["back"], "sequenceback")]]
    elif page == "gap":
        idx = int(data["editing"])
        values.update(number=idx+1, duration=_duration(data["draft"][idx]), baseline=L["baseline_first"] if idx == 0 else L["baseline_next"])
        rows = [[(("✓ " if n == data["draft"][idx] else "") + _duration(n), f"gapset:{n}") for n in group] for group in ((10, 20, 30), (60, 120, 240), (720, 1440))]
        rows += [[(L["custom_gap"], "input:gap")], [(L["back"], "sequenceback")]]
    elif page == "time":
        rows = [[(("✓ " if (h, m) == time else "") + f"{h:02d}:{m:02d}", f"timeset:{h}:{m}") for h, m in group] for group in (((9, 0), (10, 0)), ((12, 0), (18, 0)))]
        rows += [[(L["custom_time"], "input:time")], [(L["reset_time"], "timereset")], back]
    elif page == "zone":
        rows = [[(zone, f"zoneset:{i}")] for i, zone in enumerate(("Europe/Madrid", "Europe/Moscow", "Asia/Tokyo"))]
        rows += [[(L["custom_zone"], "input:zone")], [(L["geo"], "geo")], back]
    elif page == "zones":
        rows = [[(zone, f"zonepick:{i}")] for i, zone in enumerate(data.get("zones", []))]
        rows += [[(L["custom_zone"], "input:zone")], [(L["back"], "zone")]]
    elif page == "migration":
        values["zone"] = data["migration"]["new_tz"]
        rows = [[(L[mode], "migrate:"+mode)] for mode in ("all", "oneoff", "recurring", "none")]
    elif page == "aliases":
        users, chats = _load_settings_alias_lines(uid, deps)
        values["aliases"] = "\n".join(users + chats) or N["none_aliases"]
        rows = [back]
    elif page == "input":
        kind = data["input"]
        text = PROMPTS[kind]
        return text, _keyboard(session, [[(L["cancel"], "cancelinput")]])
    else:
        raise ValueError("Unknown settings screen")
    return TEXT[page].format(**values), _keyboard(session, rows)


async def _render(update, context, deps, session, *, query=None):
    session["data"]["revision"] = session["data"].get("revision", 0) + 1
    if not deps.settings_store.save(session):
        return False
    text, keyboard = _view(session, deps)
    _, _, message = _identity(update)
    if query is not None:
        await _edit_or_reply(query, text, reply_markup=keyboard)
    elif session.get("message_id") is not None:
        try:
            await context.bot.edit_message_text(chat_id=session["chat_id"], message_id=session["message_id"], text=text, reply_markup=keyboard)
        except Exception as exc:
            if "not modified" not in str(exc).lower():
                sent = await message.reply_text(text, reply_markup=keyboard)
                session["message_id"] = getattr(sent, "message_id", None)
    else:
        sent = await message.reply_text(text, reply_markup=keyboard)
        session["message_id"] = getattr(sent, "message_id", None)
    deps.settings_store.save(session)
    return True


async def start_settings(update, context, deps):
    user, chat, message = _identity(update)
    if not _personal(user, chat):
        if message is not None:
            await message.reply_text(N["private"])
        return
    session = deps.settings_store.open(user.id, chat.id, deps.get_now())
    await _render(update, context, deps, session)


async def _ask(update, context, deps, session, kind, *, query=None):
    data = session["data"]
    data["input_return"] = data.get("page", "home")
    data["page"], data["input"] = "input", kind
    session["prompt_message_id"] = None
    if not await _render(update, context, deps, session, query=query):
        return
    _, _, message = _identity(update)
    prompt = await message.reply_text(PROMPTS[kind], reply_markup=ForceReply(selective=False))
    pid = getattr(prompt, "message_id", None)
    if pid is None:
        return
    session["prompt_message_id"] = pid
    data["prompts"] = (data.get("prompts", []) + [pid])[-20:]
    deps.settings_store.save(session)


async def _set_zone(update, context, deps, session, zone, *, query):
    uid = session["user_id"]
    old = deps.get_user_timezone_name_raw(uid)
    deps.set_user_timezone_name(uid, zone)
    context.user_data.pop("pending_timezone_migration", None)
    context.user_data.pop("timezone_started_from_settings", None)
    _page(session, "zone")
    if old and old != zone and deps.count_active_reminders_for_user(uid) > 0:
        session["data"]["migration"] = {"old_tz": old, "new_tz": zone}
        session["data"]["page"] = "migration"
    await _render(update, context, deps, session, query=query)
    if old is None:
        from dkreminders_bot.settings.timezone_features import _resume_pending_plain_text_reminder
        await _resume_pending_plain_text_reminder(update, context, deps)


async def settings_menu_callback(update, context, deps):
    query = getattr(update, "callback_query", None)
    if query is None:
        return
    user, chat, _ = _identity(update)
    if not _personal(user, chat):
        await query.answer(N["private"], show_alert=True)
        return
    parts = (query.data or "").split(":")
    session = deps.settings_store.session(user.id, deps.get_now())
    if len(parts) < 5 or session is None or parts[2] != session["token"] or parts[3] != str(session["data"].get("revision", 0)) or chat.id != session["chat_id"] or query.message.message_id != session["message_id"]:
        await query.answer(N["stale"], show_alert=True)
        return
    action, args = parts[4], parts[5:]
    data, now = session["data"], deps.get_now()
    notice = None
    try:
        if action in {"home", "time", "zone", "nudges", "aliases"}:
            _page(session, action)
        elif action == "list":
            _page(session, "home")
            deps.settings_store.save(session)
            await query.answer()
            proxy = SimpleNamespace(effective_user=user, effective_chat=chat, effective_message=query.message, message=query.message)
            await deps.list_command(proxy, SimpleNamespace(args=[], user_data=context.user_data, bot=context.bot))
            return
        elif action in {"on", "off"}:
            deps.settings_store.set_enabled(user.id, action == "on", now)
            _page(session, "nudges")
            notice = N[action]
        elif action == "sequence":
            data["draft"] = deps.settings_store.nudges(user.id)["gaps"]
            _page(session, "sequence")
        elif action in {"sequenceback", "count"}:
            validate_gaps(data["draft"])
            _page(session, "sequence" if action == "sequenceback" else "count")
        elif action == "countset":
            _resize(data, int(args[0]))
            _page(session, "sequence")
        elif action == "gap":
            idx = int(args[0])
            if not 0 <= idx < len(validate_gaps(data["draft"])):
                raise ValueError()
            data["editing"] = idx
            _page(session, "gap")
        elif action == "gapset":
            draft = validate_gaps(data["draft"])
            idx = int(data["editing"])
            draft[idx] = int(args[0])
            data["draft"] = validate_gaps(draft)
            _page(session, "sequence")
        elif action == "save":
            deps.settings_store.set_gaps(user.id, validate_gaps(data["draft"]), now)
            data.pop("draft", None)
            _page(session, "nudges")
            notice = N["saved"]
        elif action == "discard":
            data.pop("draft", None)
            _page(session, "nudges")
            notice = N["cancelled"]
        elif action == "input":
            kind = args[0]
            if kind not in PROMPTS or kind in {"gap", "count"} and "draft" not in data:
                raise ValueError()
            await query.answer()
            await _ask(update, context, deps, session, kind, query=query)
            return
        elif action == "cancelinput":
            _page(session, data.get("input_return", "home"))
            notice = N["cancelled"]
        elif action == "timeset":
            hour, minute = parse_default_time_value(":".join(args))
            deps.set_user_default_time(user.id, hour, minute)
            _page(session, "time")
            notice = N["time_saved"]
        elif action == "timereset":
            deps.clear_user_default_time(user.id)
            _page(session, "time")
            notice = N["time_saved"]
        elif action in {"zoneset", "zonepick"}:
            zones = ["Europe/Madrid", "Europe/Moscow", "Asia/Tokyo"] if action == "zoneset" else data.get("zones", [])
            index = int(args[0])
            if not 0 <= index < len(zones):
                raise ValueError()
            await query.answer()
            await _set_zone(update, context, deps, session, zones[index], query=query)
            return
        elif action == "migrate":
            mode = args[0]
            pending = data.pop("migration")
            if mode not in {"all", "oneoff", "recurring", "none"} or deps.get_user_timezone_name(user.id) != pending["new_tz"]:
                raise ValueError()
            if mode != "none":
                result = deps.move_active_reminders_timezone_for_user(user_id=user.id, mode=mode, **pending)
                notice = N["migration_done"].format(**result)
            else:
                notice = N["migration_none"]
            _page(session, "home")
        elif action == "geo":
            context.user_data["timezone_started_from_settings"] = True
            deps.settings_store.save(session)
            from dkreminders_bot.settings.timezone_features import handle_timezone_callback
            proxy_query = _QueryProxy(query, "tz:geo")
            proxy_update = SimpleNamespace(callback_query=proxy_query, effective_user=user, effective_chat=chat)
            await handle_timezone_callback(proxy_update, context, deps)
            return
        else:
            raise ValueError()
    except (ValueError, KeyError, IndexError, TypeError):
        await query.answer(N["stale"], show_alert=True)
        return
    deps.settings_store.save(session)
    await query.answer(notice)
    await _render(update, context, deps, session, query=query)


class _QueryProxy:
    def __init__(self, query, data):
        self._query, self.data = query, data

    def __getattr__(self, name):
        return getattr(self._query, name)


def _resize(data, count):
    if not 1 <= count <= MAX_GAPS:
        raise ValueError(N["count_bad"])
    draft = validate_gaps(data["draft"])
    while len(draft) < count:
        draft.append(DEFAULT_GAPS[len(draft)] if len(draft) < len(DEFAULT_GAPS) else 720)
    data["draft"] = draft[:count]


async def settings_text_input(update, context, deps):
    user, chat, message = _identity(update)
    if not _personal(user, chat) or message is None:
        return False
    session = deps.settings_store.session(user.id, deps.get_now(), include_expired=True)
    if session is None:
        return False
    text = (getattr(message, "text", None) or "").strip()
    reply_id = getattr(getattr(message, "reply_to_message", None), "message_id", None)
    cancel = text.split("@", 1)[0] == "/cancel"
    known_prompt = reply_id is not None and reply_id in session["data"].get("prompts", [])
    if not known_prompt and not (cancel and session["data"].get("input")):
        return False
    kind = session["data"].get("input")
    expired = datetime.fromisoformat(session["expires_at"]).timestamp() <= deps.get_now().timestamp()
    if expired or not kind or not cancel and reply_id != session["prompt_message_id"]:
        await message.reply_text(N["closed"])
        return True
    if cancel:
        _page(session, session["data"].get("input_return", "home"))
        await _render(update, context, deps, session)
        await message.reply_text(N["cancelled"])
        return True
    data = session["data"]
    try:
        if kind == "time":
            hour, minute = parse_default_time_value(text)
            deps.set_user_default_time(user.id, hour, minute)
            _page(session, "time")
        elif kind == "zone":
            zones = search_timezones(text)
            if not zones:
                raise ValueError(N["zone_bad"])
            data["zones"] = zones
            _page(session, "zones")
        elif kind == "gap":
            idx = int(data["editing"])
            draft = validate_gaps(data["draft"])
            draft[idx] = parse_interval(text)
            data["draft"] = validate_gaps(draft)
            _page(session, "sequence")
        elif kind == "count":
            if not text.isdecimal():
                raise ValueError(N["count_bad"])
            _resize(data, int(text))
            _page(session, "sequence")
        else:
            raise ValueError(N["closed"])
    except ValueError as exc:
        error = N["time_bad"] if kind == "time" else str(exc)
        sent = await message.reply_text(error + "\n\n" + PROMPTS[kind], reply_markup=ForceReply(selective=False))
        pid = getattr(sent, "message_id", None)
        if pid is not None:
            session["prompt_message_id"] = pid
            data["prompts"] = (data.get("prompts", []) + [pid])[-20:]
            deps.settings_store.save(session)
        return True
    await _render(update, context, deps, session)
    return True


async def render_settings_home(update, query, context, deps):
    user, chat, _ = _identity(update)
    if not _personal(user, chat):
        await query.answer(N["private"], show_alert=True)
        return
    session = deps.settings_store.open(user.id, chat.id, deps.get_now())
    session["message_id"] = query.message.message_id
    await _render(update, context, deps, session, query=query)
