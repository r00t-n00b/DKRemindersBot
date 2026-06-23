import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from self_remind_event_cancel_flow import handle_self_remind_event_cancel


class Query:
    def __init__(self):
        self.edited_texts = []
        self.edited_markups = []
        self.answers = []

    async def edit_message_text(self, text, reply_markup=None):
        self.edited_texts.append(text)
        self.edited_markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def test_event_cancel_replies_not_found_when_source_missing():
    query = Query()

    asyncio.run(
        handle_self_remind_event_cancel(
            reminder_id=123,
            query=query,
            get_reminder=lambda rid: None,
            get_self_remind_event_base=lambda src: None,
            extract_event_datetime_from_text=lambda text, base: None,
            build_self_remind_choice_keyboard=lambda rid: f"choice-kb:{rid}",
            build_self_remind_event_before_keyboard=lambda rid: f"event-kb:{rid}",
            msg_source_reminder_not_found="source not found",
        )
    )

    assert query.edited_texts == []
    assert query.edited_markups == []
    assert query.answers == [("source not found", True)]


def test_event_cancel_returns_regular_choice_keyboard_when_event_is_not_parsed():
    query = Query()
    reminder = SimpleNamespace(text="какой-то текст")
    base_now = object()

    asyncio.run(
        handle_self_remind_event_cancel(
            reminder_id=123,
            query=query,
            get_reminder=lambda rid: reminder,
            get_self_remind_event_base=lambda src: base_now,
            extract_event_datetime_from_text=lambda text, base: None,
            build_self_remind_choice_keyboard=lambda rid: f"choice-kb:{rid}",
            build_self_remind_event_before_keyboard=lambda rid: f"event-kb:{rid}",
            msg_source_reminder_not_found="source not found",
        )
    )

    assert query.edited_texts == [
        "Я не смог понять дату события из текста.\n"
        "Ты можешь поставить себе обычный ремайндер:"
    ]
    assert query.edited_markups == ["choice-kb:123"]
    assert query.answers == [("Вернул варианты", None)]


def test_event_cancel_returns_event_before_keyboard_when_event_is_parsed():
    query = Query()
    reminder = SimpleNamespace(text="футбол завтра")
    event_at = datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)

    asyncio.run(
        handle_self_remind_event_cancel(
            reminder_id=123,
            query=query,
            get_reminder=lambda rid: reminder,
            get_self_remind_event_base=lambda src: object(),
            extract_event_datetime_from_text=lambda text, base: event_at,
            build_self_remind_choice_keyboard=lambda rid: f"choice-kb:{rid}",
            build_self_remind_event_before_keyboard=lambda rid: f"event-kb:{rid}",
            msg_source_reminder_not_found="source not found",
        )
    )

    assert query.edited_texts == [
        "Я понял, что событие из напоминания состоится 15.07 10:30.\n"
        "За сколько до этого времени напомнить?"
    ]
    assert query.edited_markups == ["event-kb:123"]
    assert query.answers == [("Вернул варианты до события", None)]


def test_snooze_callback_uses_self_remind_event_cancel_flow_helper():
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

    assert "from self_remind_event_cancel_flow import handle_self_remind_event_cancel" in source

    event_cancel_start = snooze_source.index('if data.startswith("selfremind_event_cancel:"):')
    cancel_start = snooze_source.index('if data.startswith("selfremind_cancel:"):', event_cancel_start)
    event_cancel_source = snooze_source[event_cancel_start:cancel_start]

    assert "handle_self_remind_event_cancel(" in event_cancel_source
    assert "src = get_reminder(rid)" not in event_cancel_source
    assert "event_at = extract_event_datetime_from_text(src.text, base_now)" not in event_cancel_source
    assert "build_self_remind_event_before_keyboard(rid)" not in event_cancel_source


def test_main_reexports_self_remind_event_cancel_flow_helper():
    assert main.handle_self_remind_event_cancel is handle_self_remind_event_cancel
