import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from self_remind_picktime_flow import handle_self_remind_picktime


class Query:
    def __init__(self, user_id=42):
        self.from_user = SimpleNamespace(id=user_id) if user_id is not None else SimpleNamespace()
        self.edited_texts = []
        self.edited_markups = []
        self.answers = []

    async def edit_message_text(self, text, reply_markup=None):
        self.edited_texts.append(text)
        self.edited_markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def run_handler(**overrides):
    calls = []
    query = overrides.pop("query", Query())
    source = overrides.pop("source", SimpleNamespace(text="исходный текст"))
    new_id = overrides.pop("new_id", 777)

    async def get_source_chat_title_for_self_remind(context, src, query):
        calls.append(("title", context.bot, src.text))
        return "Исходный чат"

    def add_reminder(**kwargs):
        calls.append(("add", kwargs))
        return new_id

    async def run():
        await handle_self_remind_picktime(
            data=overrides.pop("data", "selfremind_picktime:123:2026-07-15:10:30"),
            query=query,
            context=overrides.pop("context", SimpleNamespace(bot="bot")),
            tz=overrides.pop("tz", timezone.utc),
            get_now=overrides.pop("get_now", lambda: datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)),
            get_user_chat_id_by_user_id=overrides.pop("get_user_chat_id_by_user_id", lambda user_id: 999),
            get_reminder=overrides.pop("get_reminder", lambda rid: source),
            get_source_chat_title_for_self_remind=overrides.pop("get_source_chat_title_for_self_remind", get_source_chat_title_for_self_remind),
            add_reminder=overrides.pop("add_reminder", add_reminder),
            build_created_reminder_actions_keyboard_for_reminder=overrides.pop("build_created_reminder_actions_keyboard_for_reminder", lambda rid: f"actions:{rid}"),
            format_self_remind_text=overrides.pop("format_self_remind_text", lambda title, text: f"from {title}: {text}"),
            format_created_reminder_text=overrides.pop("format_created_reminder_text", lambda when, text: f"created {when}: {text}"),
            msg_user_context_missing=overrides.pop("msg_user_context_missing", "user missing"),
            msg_source_reminder_not_found=overrides.pop("msg_source_reminder_not_found", "source missing"),
            msg_reschedule_bad_datetime=overrides.pop("msg_reschedule_bad_datetime", "bad datetime"),
            msg_reschedule_past_time=overrides.pop("msg_reschedule_past_time", "past time"),
        )
        assert not overrides, f"unused overrides: {overrides}"

    asyncio.run(run())
    return calls, query


def test_picktime_replies_user_missing_when_query_has_no_user_id():
    calls, query = run_handler(query=Query(user_id=None))

    assert calls == []
    assert query.answers == [("user missing", True)]


def test_picktime_replies_unknown_private_chat_when_user_not_known():
    calls, query = run_handler(get_user_chat_id_by_user_id=lambda user_id: None)

    assert calls == []
    assert query.answers == [
        (
            "Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате",
            True,
        )
    ]


def test_picktime_replies_source_missing_when_source_reminder_not_found():
    calls, query = run_handler(get_reminder=lambda rid: None)

    assert calls == []
    assert query.answers == [("source missing", True)]


def test_picktime_replies_bad_datetime_for_invalid_datetime():
    calls, query = run_handler(data="selfremind_picktime:123:bad-date:10:30")

    assert calls == []
    assert query.answers == [("bad datetime", True)]


def test_picktime_replies_past_time_for_non_future_datetime():
    calls, query = run_handler(
        get_now=lambda: datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc),
    )

    assert calls == []
    assert query.answers == [("past time", True)]


def test_picktime_creates_regular_personal_reminder():
    calls, query = run_handler()

    assert calls[0] == ("title", "bot", "исходный текст")

    name, kwargs = calls[1]
    assert name == "add"
    assert kwargs["chat_id"] == 999
    assert kwargs["text"] == "from Исходный чат: исходный текст"
    assert kwargs["remind_at"] == datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)
    assert kwargs["created_by"] == 42
    assert kwargs["template_id"] is None

    assert query.edited_texts == ["created 15.07 10:30: from Исходный чат: исходный текст"]
    assert query.edited_markups == ["actions:777"]
    assert query.answers == [("Личное напоминание создано", None)]


def test_picktime_creates_event_personal_reminder():
    calls, query = run_handler(
        data="selfremind_event_picktime:123:2026-07-15:10:30",
    )

    name, kwargs = calls[1]
    assert name == "add"
    assert kwargs["text"] == "from Исходный чат: исходный текст"
    assert query.answers == [("Личное напоминание создано", None)]


def test_snooze_callback_uses_self_remind_picktime_flow_helper():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "snooze_callback"
    ]
    assert len(nodes) == 1

    snooze_source = ast.get_source_segment(source, nodes[0])

    assert "from self_remind_picktime_flow import handle_self_remind_picktime" in source

    picktime_start = snooze_source.index('if data.startswith("selfremind_picktime:") or data.startswith("selfremind_event_picktime:"):')
    event_cancel_start = snooze_source.index('if data.startswith("selfremind_event_cancel:"):', picktime_start)
    picktime_source = snooze_source[picktime_start:event_cancel_start]

    assert "handle_self_remind_picktime(" in picktime_source
    assert "target_chat_id = get_user_chat_id_by_user_id" not in picktime_source
    assert "src = get_reminder(rid)" not in picktime_source
    assert "new_reminder_id = add_reminder" not in picktime_source


def test_main_reexports_self_remind_picktime_flow_helper():
    assert main.handle_self_remind_picktime is handle_self_remind_picktime
