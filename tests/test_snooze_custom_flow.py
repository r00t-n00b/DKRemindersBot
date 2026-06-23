import asyncio

import main
from snooze_custom_flow import enter_custom_snooze_flow


class Query:
    def __init__(self):
        self.markups = []
        self.answers = []

    async def edit_message_reply_markup(self, reply_markup=None):
        self.markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def test_enter_custom_snooze_flow_marks_acked_and_opens_date_picker():
    calls = []
    query = Query()

    asyncio.run(
        enter_custom_snooze_flow(
            reminder_id=123,
            query=query,
            mark_reminder_acked=lambda rid: calls.append(("acked", rid)),
            build_custom_date_keyboard=lambda rid: f"date-kb:{rid}",
        )
    )

    assert calls == [("acked", 123)]
    assert query.markups == ["date-kb:123"]
    assert query.answers == [("Выбери дату", False)]


def test_snooze_callback_uses_custom_snooze_flow():
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

    direct_source = Path("snooze_direct_flow.py").read_text()

    assert "from snooze_custom_flow import enter_custom_snooze_flow" in source
    assert "enter_custom_snooze_flow=enter_custom_snooze_flow" in snooze_source
    assert "enter_custom_snooze_flow(" in direct_source
    assert "kb = build_custom_date_keyboard(rid)" not in snooze_source
    assert 'await query.answer("Выбери дату", show_alert=False)' not in snooze_source


def test_main_reexports_custom_snooze_flow():
    assert main.enter_custom_snooze_flow is enter_custom_snooze_flow
