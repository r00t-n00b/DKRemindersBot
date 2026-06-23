import asyncio
from types import SimpleNamespace

import main
from self_remind_cancel_flow import handle_self_remind_cancel


class Query:
    def __init__(self):
        self.edited_texts = []
        self.edited_markups = []
        self.answers = []

    async def edit_message_text(self, text):
        self.edited_texts.append(text)

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edited_markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def test_self_remind_cancel_replies_not_found_when_source_missing():
    query = Query()

    asyncio.run(
        handle_self_remind_cancel(
            reminder_id=123,
            query=query,
            context=SimpleNamespace(bot="bot"),
            get_reminder=lambda rid: None,
            get_source_chat_title_for_self_remind=None,
            build_self_remind_choice_keyboard=lambda rid: f"kb:{rid}",
            msg_source_reminder_not_found="source not found",
        )
    )

    assert query.edited_texts == []
    assert query.edited_markups == []
    assert query.answers == [("source not found", True)]


def test_self_remind_cancel_restores_choice_keyboard_for_existing_source():
    query = Query()
    reminder = SimpleNamespace(text="проверить документы")

    async def get_source_chat_title_for_self_remind(context, src, query):
        assert context.bot == "bot"
        assert src is reminder
        return "Рабочий чат"

    asyncio.run(
        handle_self_remind_cancel(
            reminder_id=123,
            query=query,
            context=SimpleNamespace(bot="bot"),
            get_reminder=lambda rid: reminder,
            get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
            build_self_remind_choice_keyboard=lambda rid: f"choice-kb:{rid}",
            msg_source_reminder_not_found="source not found",
        )
    )

    assert query.edited_texts == [
        'Когда напомнить тебе о "проверить документы" из чата "Рабочий чат"?'
    ]
    assert query.edited_markups == ["choice-kb:123"]
    assert query.answers == [("Вернул варианты", None)]


def test_snooze_callback_uses_self_remind_cancel_flow_helper():
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

    assert "from self_remind_cancel_flow import handle_self_remind_cancel" in source

    cancel_start = snooze_source.index('if data.startswith("selfremind_cancel:"):')
    done_start = snooze_source.index('if data.startswith("done:"):', cancel_start)
    cancel_source = snooze_source[cancel_start:done_start]

    assert "handle_self_remind_cancel_callback(" in cancel_source
    assert "handle_self_remind_cancel=handle_self_remind_cancel" in cancel_source
    assert "src = get_reminder(rid)" not in cancel_source
    assert "source_chat_title = await get_source_chat_title_for_self_remind" not in cancel_source
    assert "reply_markup=build_self_remind_choice_keyboard(rid)" not in cancel_source


def test_main_reexports_self_remind_cancel_flow_helper():
    assert main.handle_self_remind_cancel is handle_self_remind_cancel
