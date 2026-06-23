import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from self_remind_create_flow import (
    handle_self_remind_event_custom,
    handle_self_remind_event_before,
    handle_self_remind_set,
)


class Query:
    def __init__(self, user_id=42):
        self.from_user = SimpleNamespace(id=user_id) if user_id is not None else SimpleNamespace()
        self.markups = []
        self.edited_texts = []
        self.edited_markups = []
        self.answers = []

    async def edit_message_reply_markup(self, reply_markup=None):
        self.markups.append(reply_markup)

    async def edit_message_text(self, text, reply_markup=None):
        self.edited_texts.append(text)
        self.edited_markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def test_event_custom_opens_event_calendar():
    query = Query()
    source = SimpleNamespace(text="футбол завтра")

    asyncio.run(
        handle_self_remind_event_custom(
            data="selfremind:event_custom:123",
            query=query,
            get_reminder=lambda rid: source,
            build_custom_date_keyboard=lambda rid, callback_prefix: f"date-kb:{rid}:{callback_prefix}",
            msg_invalid_reminder_id="invalid id",
            msg_source_reminder_not_found="source missing",
        )
    )

    assert query.markups == ["date-kb:123:selfremind_event"]
    assert query.answers == [("Выбери дату", None)]


def test_event_custom_replies_invalid_id_or_source_missing():
    query = Query()

    asyncio.run(
        handle_self_remind_event_custom(
            data="selfremind:event_custom:bad",
            query=query,
            get_reminder=lambda rid: None,
            build_custom_date_keyboard=lambda rid, callback_prefix: None,
            msg_invalid_reminder_id="invalid id",
            msg_source_reminder_not_found="source missing",
        )
    )

    assert query.answers == [("invalid id", True)]

    query = Query()
    asyncio.run(
        handle_self_remind_event_custom(
            data="selfremind:event_custom:123",
            query=query,
            get_reminder=lambda rid: None,
            build_custom_date_keyboard=lambda rid, callback_prefix: None,
            msg_invalid_reminder_id="invalid id",
            msg_source_reminder_not_found="source missing",
        )
    )

    assert query.answers == [("source missing", True)]


def run_event_before(**overrides):
    calls = []
    query = overrides.pop("query", Query())
    source = overrides.pop("source", SimpleNamespace(text="футбол завтра"))
    event_at = overrides.pop("event_at", datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc))
    remind_at = overrides.pop("remind_at", datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc))

    async def get_source_chat_title_for_self_remind(context, src, query):
        calls.append(("title", context.bot, src.text))
        return "Исходный чат"

    def add_reminder(**kwargs):
        calls.append(("add", kwargs))
        return 777

    asyncio.run(
        handle_self_remind_event_before(
            data=overrides.pop("data", "selfremind:event_before:123:3h"),
            query=query,
            context=overrides.pop("context", SimpleNamespace(bot="bot")),
            get_now=overrides.pop("get_now", lambda: datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)),
            get_user_chat_id_by_user_id=overrides.pop("get_user_chat_id_by_user_id", lambda user_id: 999),
            get_reminder=overrides.pop("get_reminder", lambda rid: source),
            get_self_remind_event_base=overrides.pop("get_self_remind_event_base", lambda src: object()),
            extract_event_datetime_from_text=overrides.pop("extract_event_datetime_from_text", lambda text, base: event_at),
            compute_event_before_time=overrides.pop("compute_event_before_time", lambda option, event_at: remind_at),
            get_source_chat_title_for_self_remind=overrides.pop("get_source_chat_title_for_self_remind", get_source_chat_title_for_self_remind),
            normalize_relative_event_date_in_text=overrides.pop("normalize_relative_event_date_in_text", lambda text, event_at: f"normalized {text}"),
            format_self_remind_text=overrides.pop("format_self_remind_text", lambda title, text: f"from {title}: {text}"),
            add_reminder=overrides.pop("add_reminder", add_reminder),
            format_created_reminder_text=overrides.pop("format_created_reminder_text", lambda when, text: f"created {when}: {text}"),
            build_created_reminder_actions_keyboard_for_reminder=overrides.pop("build_created_reminder_actions_keyboard_for_reminder", lambda rid: f"actions:{rid}"),
            msg_invalid_reminder_id=overrides.pop("msg_invalid_reminder_id", "invalid id"),
            msg_user_context_missing=overrides.pop("msg_user_context_missing", "user missing"),
            msg_source_reminder_not_found=overrides.pop("msg_source_reminder_not_found", "source missing"),
            msg_event_date_not_found=overrides.pop("msg_event_date_not_found", "event missing"),
            msg_unknown_time_option=overrides.pop("msg_unknown_time_option", "unknown option"),
            msg_reschedule_past_time=overrides.pop("msg_reschedule_past_time", "past time"),
        )
    )
    assert not overrides, f"unused overrides: {overrides}"
    return calls, query


def test_event_before_creates_personal_reminder():
    calls, query = run_event_before()

    assert calls[0] == ("title", "bot", "футбол завтра")
    name, kwargs = calls[1]
    assert name == "add"
    assert kwargs["chat_id"] == 999
    assert kwargs["text"] == "from Исходный чат: normalized футбол завтра"
    assert kwargs["created_by"] == 42
    assert query.edited_texts == ["created 15.07 10:00: from Исходный чат: normalized футбол завтра"]
    assert query.edited_markups == ["actions:777"]
    assert query.answers == [("Личное напоминание создано", None)]


def test_event_before_negative_paths():
    assert run_event_before(data="selfremind:event_before:bad:3h")[1].answers == [("invalid id", True)]
    assert run_event_before(query=Query(user_id=None))[1].answers == [("user missing", True)]
    assert run_event_before(get_user_chat_id_by_user_id=lambda user_id: None)[1].answers[0][1] is True
    assert run_event_before(get_reminder=lambda rid: None)[1].answers == [("source missing", True)]
    assert run_event_before(extract_event_datetime_from_text=lambda text, base: None)[1].answers == [("event missing", True)]
    assert run_event_before(compute_event_before_time=lambda option, event_at: None)[1].answers == [("unknown option", True)]
    assert run_event_before(get_now=lambda: datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc))[1].answers == [("past time", True)]


def run_set(**overrides):
    calls = []
    query = overrides.pop("query", Query())
    source = overrides.pop("source", SimpleNamespace(text="купить молоко"))
    remind_at = overrides.pop("remind_at", datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc))

    async def get_source_chat_title_for_self_remind(context, src, query):
        calls.append(("title", context.bot, src.text))
        return "Исходный чат"

    def add_reminder(**kwargs):
        calls.append(("add", kwargs))
        return 777

    asyncio.run(
        handle_self_remind_set(
            data=overrides.pop("data", "selfremind:set:123:1h"),
            query=query,
            context=overrides.pop("context", SimpleNamespace(bot="bot")),
            get_now=overrides.pop("get_now", lambda: datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)),
            get_user_chat_id_by_user_id=overrides.pop("get_user_chat_id_by_user_id", lambda user_id: 999),
            get_reminder=overrides.pop("get_reminder", lambda rid: source),
            compute_self_remind_time=overrides.pop("compute_self_remind_time", lambda option, now: remind_at),
            get_source_chat_title_for_self_remind=overrides.pop("get_source_chat_title_for_self_remind", get_source_chat_title_for_self_remind),
            format_self_remind_text=overrides.pop("format_self_remind_text", lambda title, text: f"from {title}: {text}"),
            add_reminder=overrides.pop("add_reminder", add_reminder),
            build_custom_date_keyboard=overrides.pop("build_custom_date_keyboard", lambda rid, callback_prefix: f"date-kb:{rid}:{callback_prefix}"),
            format_created_reminder_text=overrides.pop("format_created_reminder_text", lambda when, text: f"created {when}: {text}"),
            build_created_reminder_actions_keyboard_for_reminder=overrides.pop("build_created_reminder_actions_keyboard_for_reminder", lambda rid: f"actions:{rid}"),
            msg_invalid_reminder_id=overrides.pop("msg_invalid_reminder_id", "invalid id"),
            msg_user_context_missing=overrides.pop("msg_user_context_missing", "user missing"),
            msg_source_reminder_not_found=overrides.pop("msg_source_reminder_not_found", "source missing"),
        )
    )
    assert not overrides, f"unused overrides: {overrides}"
    return calls, query


def test_self_remind_set_custom_opens_regular_calendar():
    calls, query = run_set(data="selfremind:set:123:custom")

    assert calls == []
    assert query.markups == ["date-kb:123:selfremind"]
    assert query.answers == [("Выбери дату", None)]


def test_self_remind_set_creates_personal_reminder():
    calls, query = run_set()

    assert calls[0] == ("title", "bot", "купить молоко")
    name, kwargs = calls[1]
    assert name == "add"
    assert kwargs["chat_id"] == 999
    assert kwargs["text"] == "from Исходный чат: купить молоко"
    assert kwargs["template_id"] is None
    assert query.edited_texts == ["created 15.07 10:00: from Исходный чат: купить молоко"]
    assert query.edited_markups == ["actions:777"]
    assert query.answers == [("Личное напоминание создано", None)]


def test_self_remind_set_negative_paths():
    assert run_set(data="selfremind:set:bad:1h")[1].answers == [("invalid id", True)]
    assert run_set(query=Query(user_id=None))[1].answers == [("user missing", True)]
    assert run_set(get_user_chat_id_by_user_id=lambda user_id: None)[1].answers[0][1] is True
    assert run_set(get_reminder=lambda rid: None)[1].answers == [("source missing", True)]


def test_snooze_callback_uses_self_remind_create_flow_helpers():
    import ast
    from pathlib import Path

    source = Path("reminder_callback_router.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_reminder_callback"
    ]
    assert len(nodes) == 1

    snooze_source = ast.get_source_segment(source, nodes[0])

    start = snooze_source.index('if data.startswith("selfremind:event_custom:"):')
    end = snooze_source.index('if data.startswith("selfremind_cal:") or data.startswith("selfremind_event_cal:"):', start)
    create_source = snooze_source[start:end]

    assert "handle_self_remind_event_custom(" in create_source
    assert "handle_self_remind_event_before(" in create_source
    assert "handle_self_remind_set(" in create_source
    assert "target_chat_id = get_user_chat_id_by_user_id" not in create_source
    assert "new_reminder_id = add_reminder" not in create_source


def test_main_reexports_self_remind_create_flow_helpers():
    assert main.handle_self_remind_event_custom is handle_self_remind_event_custom
    assert main.handle_self_remind_event_before is handle_self_remind_event_before
    assert main.handle_self_remind_set is handle_self_remind_set
