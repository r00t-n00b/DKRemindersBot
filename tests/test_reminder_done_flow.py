import asyncio
from types import SimpleNamespace

import main
from dkreminders_bot.callbacks.reminder_done_flow import handle_done_callback


class Query:
    def __init__(self, *, text="original text", fail_text=False, fail_markup=False, no_edit_text=False, no_edit_markup=False):
        self.message = SimpleNamespace(text=text) if text is not None else None
        self.fail_text = fail_text
        self.fail_markup = fail_markup
        self.edited_texts = []
        self.edited_markups = []
        self.answers = []
        if no_edit_text:
            self.edit_message_text = None
        if no_edit_markup:
            self.edit_message_reply_markup = None

    async def edit_message_text(self, text):
        if self.fail_text:
            raise RuntimeError("edit text failed")
        self.edited_texts.append(text)

    async def edit_message_reply_markup(self, reply_markup=None):
        if self.fail_markup:
            raise RuntimeError("edit markup failed")
        self.edited_markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def run_handler(**overrides):
    calls = []
    query = overrides.pop("query", Query())
    reminder = overrides.pop("reminder", SimpleNamespace(id=123, chat_id=555, text="db text", created_by=42))

    async def clear_reminder_message_keyboards(bot, rid, replacement_text=None):
        calls.append(("clear", bot, rid, replacement_text))

    async def delete_other_reminder_messages(bot, *, reminder_id, keep_chat_id, keep_message_id):
        calls.append(("delete_other", bot, reminder_id, keep_chat_id, keep_message_id))

    async def run():
        await handle_done_callback(
            reminder_id=overrides.pop("reminder_id", 123),
            query=query,
            context=overrides.pop("context", SimpleNamespace(bot="bot")),
            mark_reminder_acked=overrides.pop("mark_reminder_acked", lambda rid: calls.append(("acked", rid))),
            clear_reminder_message_keyboards=clear_reminder_message_keyboards,
            get_reminder=overrides.pop("get_reminder", lambda rid: reminder),
            format_completed_reminder_text=overrides.pop("format_completed_reminder_text", lambda text: f"done: {text}"),
            delete_old_snoozed_reminder_messages=overrides.pop("delete_old_snoozed_reminder_messages", None),
            delete_other_reminder_messages=overrides.pop("delete_other_reminder_messages", delete_other_reminder_messages),
        )
        assert not overrides, f"unused overrides: {overrides}"

    asyncio.run(run())
    return calls, query


def test_done_callback_marks_acked_updates_related_messages_and_uses_db_text():
    calls, query = run_handler()

    assert calls == [("acked", 123), ("clear", "bot", 123, "done: db text")]
    assert query.edited_texts == ["done: db text"]
    assert query.edited_markups == [None]
    assert query.answers == [("Отмечено как завершенное", None)]


def test_done_callback_uses_original_message_text_when_reminder_id_invalid():
    calls, query = run_handler(reminder_id=None, query=Query(text="message text"))

    assert calls == []
    assert query.edited_texts == ["done: message text"]
    assert query.edited_markups == [None]
    assert query.answers == [("Отмечено как завершенное", None)]


def test_done_callback_uses_default_text_when_no_db_and_no_message_text():
    calls, query = run_handler(
        reminder=None,
        get_reminder=lambda rid: None,
        query=Query(text=None),
    )

    assert calls == [("acked", 123), ("clear", "bot", 123, "done: Напоминание")]
    assert query.edited_texts == ["done: Напоминание"]
    assert query.edited_markups == [None]
    assert query.answers == [("Отмечено как завершенное", None)]


def test_done_callback_ignores_edit_failures():
    calls, query = run_handler(query=Query(fail_text=True, fail_markup=True))

    assert calls == [("acked", 123), ("clear", "bot", 123, "done: db text")]
    assert query.edited_texts == []
    assert query.edited_markups == []
    assert query.answers == [("Отмечено как завершенное", None)]


def test_snooze_callback_uses_done_flow_helper():
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
    assert "handle_done_callback_data(" in snooze_source
    assert "handle_done_callback=handle_done_callback" in snooze_source

    done_start = snooze_source.index('if data.startswith("done:"):')
    snooze_start = snooze_source.index('if data.startswith("snooze:"):', done_start)
    done_source = snooze_source[done_start:snooze_start]

    assert "original_text = query.message.text" not in done_source
    assert "format_completed_reminder_text(base_text)" not in done_source
    assert "await clear_reminder_message_keyboards(context.bot, rid)" not in done_source


def test_main_reexports_done_flow_helper():
    assert main.handle_done_callback is handle_done_callback



def test_done_callback_deletes_sibling_messages_when_clicked_message_is_known():
    query = Query()
    query.message.chat_id = 555
    query.message.message_id = 1002

    calls, query = run_handler(
        query=query,
    )

    assert ("delete_other", "bot", 123, 555, 1002) in calls
    assert not any(call[0] == "clear" for call in calls)
    assert ("acked", 123) in calls
    assert query.edited_texts == ["done: db text"]
    assert query.edited_markups == [None]


def test_done_router_threads_delete_other_messages():
    from pathlib import Path

    source = Path("dkreminders_bot/callbacks/reminder_callback_router.py").read_text()

    done_start = source.index('if data.startswith("done:"):')
    snooze_start = source.index('if data.startswith("snooze:"):', done_start)
    done_source = source[done_start:snooze_start]

    assert "delete_other_reminder_messages=delete_other_reminder_messages" in done_source
