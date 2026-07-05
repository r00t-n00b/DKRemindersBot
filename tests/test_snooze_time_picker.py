import asyncio

import main
from dkreminders_bot.callbacks.snooze_time_picker import enter_custom_snooze_time_picker


class Query:
    def __init__(self):
        self.markups = []
        self.answers = []

    async def edit_message_reply_markup(self, reply_markup=None):
        self.markups.append(reply_markup)

    async def answer(self, text=None):
        self.answers.append(text)


def test_enter_custom_snooze_time_picker_marks_acked_and_opens_time_picker():
    calls = []
    query = Query()

    asyncio.run(
        enter_custom_snooze_time_picker(
            reminder_id=123,
            date_str="2026-07-15",
            query=query,
            mark_reminder_acked=lambda rid: calls.append(("acked", rid)),
            build_custom_time_keyboard=lambda rid, date_str: f"time-kb:{rid}:{date_str}",
        )
    )

    assert calls == [("acked", 123)]
    assert query.markups == ["time-kb:123:2026-07-15"]
    assert query.answers == ["Выбери время"]


def test_snooze_callback_uses_time_picker_helper():
    import ast
    from pathlib import Path

    source = Path("dkreminders_bot/callbacks/reminder_callback_router.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_reminder_callback"
    ]
    assert len(nodes) == 1

    snooze_source = ast.get_source_segment(source, nodes[0])
    assert "enter_custom_snooze_time_picker(" in snooze_source
    assert "kb = build_custom_time_keyboard(rid, date_str)" not in snooze_source


def test_main_reexports_time_picker_helper():
    assert main.enter_custom_snooze_time_picker is enter_custom_snooze_time_picker
