import asyncio

import main
from snooze_cancel_flow import handle_custom_snooze_cancel


class Query:
    def __init__(self):
        self.markups = []
        self.answers = []

    async def edit_message_reply_markup(self, reply_markup=None):
        self.markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def test_custom_snooze_cancel_marks_acked_and_restores_keyboard():
    calls = []
    query = Query()

    asyncio.run(
        handle_custom_snooze_cancel(
            reminder_id=123,
            query=query,
            mark_reminder_acked=lambda rid: calls.append(("acked", rid)),
            build_snooze_keyboard=lambda rid: f"snooze-kb:{rid}",
            msg_invalid_reminder_id="invalid id",
        )
    )

    assert calls == [("acked", 123)]
    assert query.markups == ["snooze-kb:123"]
    assert query.answers == [("Вернул варианты", None)]


def test_custom_snooze_cancel_replies_invalid_id_when_id_is_none():
    calls = []
    query = Query()

    asyncio.run(
        handle_custom_snooze_cancel(
            reminder_id=None,
            query=query,
            mark_reminder_acked=lambda rid: calls.append(("acked", rid)),
            build_snooze_keyboard=lambda rid: f"snooze-kb:{rid}",
            msg_invalid_reminder_id="invalid id",
        )
    )

    assert calls == []
    assert query.markups == []
    assert query.answers == [("invalid id", True)]


def test_snooze_callback_uses_cancel_flow_helper():
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

    assert "from snooze_cancel_flow import handle_custom_snooze_cancel" in source
    assert "handle_custom_snooze_cancel(" in snooze_source

    cancel_start = snooze_source.index('if data.startswith("snooze_cancel:"):')
    noop_start = snooze_source.index('if data == "noop":', cancel_start)
    cancel_source = snooze_source[cancel_start:noop_start]

    assert "reply_markup=build_snooze_keyboard(rid)" not in cancel_source
    assert 'await query.answer("Вернул варианты")' not in cancel_source
    assert "await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)" not in cancel_source


def test_main_reexports_cancel_flow_helper():
    assert main.handle_custom_snooze_cancel is handle_custom_snooze_cancel
