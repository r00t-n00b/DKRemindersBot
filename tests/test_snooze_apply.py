import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from snooze_apply import apply_snooze_to_reminder


class Query:
    def __init__(self, *, fail_edit_text=False, fail_edit_markup=False):
        self.fail_edit_text = fail_edit_text
        self.fail_edit_markup = fail_edit_markup
        self.edited_texts = []
        self.edited_markups = []
        self.answers = []

    async def edit_message_text(self, text):
        if self.fail_edit_text:
            raise RuntimeError("edit text failed")
        self.edited_texts.append(text)

    async def edit_message_reply_markup(self, reply_markup=None):
        if self.fail_edit_markup:
            raise RuntimeError("edit markup failed")
        self.edited_markups.append(reply_markup)

    async def answer(self, text):
        self.answers.append(text)


def run_apply(*, fail_edit_text=False, fail_edit_markup=False):
    calls = []
    query = Query(fail_edit_text=fail_edit_text, fail_edit_markup=fail_edit_markup)
    context = SimpleNamespace(bot="bot")
    reminder = SimpleNamespace(
        id=123,
        chat_id=555,
        text="milk",
        created_by=42,
    )
    new_dt = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    async def clear_reminder_message_keyboards(bot, rid, replacement_text=None):
        calls.append(("clear", bot, rid, replacement_text))

    async def run():
        await apply_snooze_to_reminder(
            reminder=reminder,
            new_dt=new_dt,
            query=query,
            context=context,
            mark_reminder_acked=lambda rid: calls.append(("acked", rid)),
            clear_reminder_message_keyboards=clear_reminder_message_keyboards,
            add_reminder=lambda **kwargs: calls.append(("add", kwargs)),
            format_snoozed_reminder_text=lambda text, when: f"snoozed {when}: {text}",
            format_snoozed_answer_text=lambda when: f"answer {when}",
        )

    asyncio.run(run())
    return calls, query


def test_apply_snooze_to_reminder_creates_new_reminder_and_updates_related_messages():
    calls, query = run_apply()

    assert calls == [
        ("acked", 123),
        ("clear", "bot", 123, "snoozed 02.01 10:00: milk"),
        (
            "add",
            {
                "chat_id": 555,
                "text": "milk",
                "remind_at": datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
                "created_by": 42,
                "template_id": None,
            },
        ),
    ]
    assert query.edited_texts == ["snoozed 02.01 10:00: milk"]
    assert query.edited_markups == []
    assert query.answers == ["answer 02.01 10:00"]


def test_apply_snooze_to_reminder_clears_keyboard_when_text_edit_fails():
    calls, query = run_apply(fail_edit_text=True)

    assert calls[0] == ("acked", 123)
    assert calls[1] == ("clear", "bot", 123, "snoozed 02.01 10:00: milk")
    assert query.edited_texts == []
    assert query.edited_markups == [None]
    assert query.answers == ["answer 02.01 10:00"]


def test_apply_snooze_to_reminder_ignores_keyboard_clear_failure_after_text_edit_failure():
    calls, query = run_apply(fail_edit_text=True, fail_edit_markup=True)

    assert calls[0] == ("acked", 123)
    assert calls[1] == ("clear", "bot", 123, "snoozed 02.01 10:00: milk")
    assert query.edited_texts == []
    assert query.edited_markups == []
    assert query.answers == ["answer 02.01 10:00"]


def test_snooze_callback_uses_extracted_apply_helper():
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
    assert snooze_source.count("apply_snooze_to_reminder(") == 0
    assert "apply_snooze_to_reminder(" in Path("snooze_direct_flow.py").read_text()
    assert "apply_snooze_to_reminder(" in Path("snooze_picktime_flow.py").read_text()
    assert "format_snoozed_reminder_text(r.text, when_str)" not in snooze_source
    assert "format_snoozed_answer_text(when_str)" not in snooze_source


def test_main_reexports_snooze_apply_helper():
    assert main.apply_snooze_to_reminder is apply_snooze_to_reminder



def test_apply_snooze_to_reminder_deletes_old_snoozed_messages_before_current_update():
    calls = []
    query = Query()
    context = SimpleNamespace(bot="bot")
    reminder = SimpleNamespace(
        id=123,
        chat_id=555,
        text="milk",
        created_by=42,
    )
    new_dt = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    async def delete_old(bot, **kwargs):
        calls.append(("delete_old", bot, kwargs))

    async def clear_reminder_message_keyboards(bot, rid, replacement_text=None):
        calls.append(("clear", bot, rid, replacement_text))

    async def run():
        await apply_snooze_to_reminder(
            reminder=reminder,
            new_dt=new_dt,
            query=query,
            context=context,
            mark_reminder_acked=lambda rid: calls.append(("acked", rid)),
            clear_reminder_message_keyboards=clear_reminder_message_keyboards,
            add_reminder=lambda **kwargs: calls.append(("add", kwargs)),
            format_snoozed_reminder_text=lambda text, when: f"snoozed {when}: {text}",
            format_snoozed_answer_text=lambda when: f"answer {when}",
            delete_old_snoozed_reminder_messages=delete_old,
        )

    asyncio.run(run())

    assert calls[0] == (
        "delete_old",
        "bot",
        {
            "current_reminder_id": 123,
            "chat_id": 555,
            "text": "milk",
            "created_by": 42,
        },
    )
    assert calls[1] == ("acked", 123)
    assert calls[2] == ("clear", "bot", 123, "snoozed 02.01 10:00: milk")


def test_done_callback_deletes_old_snoozed_messages_before_completion():
    import asyncio
    from reminder_done_flow import handle_done_callback

    calls = []
    reminder = SimpleNamespace(
        id=123,
        chat_id=555,
        text="milk",
        created_by=42,
    )

    class DoneQuery(Query):
        def __init__(self):
            super().__init__()
            self.message = SimpleNamespace(text="milk")

    query = DoneQuery()
    context = SimpleNamespace(bot="bot")

    async def delete_old(bot, **kwargs):
        calls.append(("delete_old", bot, kwargs))

    async def clear_reminder_message_keyboards(bot, rid, replacement_text=None):
        calls.append(("clear", bot, rid, replacement_text))

    asyncio.run(
        handle_done_callback(
            reminder_id=123,
            query=query,
            context=context,
            mark_reminder_acked=lambda rid: calls.append(("acked", rid)),
            clear_reminder_message_keyboards=clear_reminder_message_keyboards,
            get_reminder=lambda rid: reminder,
            format_completed_reminder_text=lambda text: f"{text} done",
            delete_old_snoozed_reminder_messages=delete_old,
        )
    )

    assert calls[0] == (
        "delete_old",
        "bot",
        {
            "current_reminder_id": 123,
            "chat_id": 555,
            "text": "milk",
            "created_by": 42,
        },
    )
    assert calls[1] == ("acked", 123)
    assert calls[2] == ("clear", "bot", 123, "milk done")
    assert query.edited_texts == ["milk done"]


def test_done_callback_data_passes_delete_old_snoozed_messages():
    import asyncio
    from callback_simple_flows import handle_done_callback_data

    seen = {}

    async def fake_handle_done_callback(**kwargs):
        seen.update(kwargs)

    async def fake_delete_old(*args, **kwargs):
        pass

    query = SimpleNamespace()
    context = SimpleNamespace(bot="bot")

    asyncio.run(
        handle_done_callback_data(
            data="done:123",
            query=query,
            context=context,
            parse_optional_int_callback_id=lambda data, prefix: 123,
            handle_done_callback=fake_handle_done_callback,
            mark_reminder_acked=lambda rid: None,
            clear_reminder_message_keyboards=lambda *a, **k: None,
            get_reminder=lambda rid: None,
            format_completed_reminder_text=lambda text: text,
            delete_old_snoozed_reminder_messages=fake_delete_old,
        )
    )

    assert seen["reminder_id"] == 123
    assert seen["delete_old_snoozed_reminder_messages"] is fake_delete_old


def test_apply_snooze_deletes_other_messages_from_same_reminder():
    import asyncio
    from types import SimpleNamespace

    from snooze_apply import apply_snooze_to_reminder

    calls = []

    class Query:
        def __init__(self):
            self.message = SimpleNamespace(chat_id=555, message_id=1002)
            self.edits = []
            self.answers = []

        async def edit_message_text(self, text):
            self.edits.append(text)

        async def edit_message_reply_markup(self, reply_markup=None):
            calls.append(("fallback_clear_clicked", reply_markup))

        async def answer(self, text):
            self.answers.append(text)

    reminder = SimpleNamespace(
        id=77,
        chat_id=555,
        text="meltan",
        created_by=42,
    )
    query = Query()
    context = SimpleNamespace(bot=SimpleNamespace())

    async def delete_other_reminder_messages(bot, *, reminder_id, keep_chat_id, keep_message_id):
        calls.append(("delete_other", reminder_id, keep_chat_id, keep_message_id))

    async def async_delete_old_snoozed_reminder_messages(bot, **kwargs):
        calls.append(("delete_old", kwargs))

    asyncio.run(
        apply_snooze_to_reminder(
            reminder=reminder,
            new_dt=SimpleNamespace(strftime=lambda fmt: "03.07 14:56"),
            query=query,
            context=context,
            mark_reminder_acked=lambda reminder_id: calls.append(("acked", reminder_id)),
            clear_reminder_message_keyboards=lambda bot, reminder_id, replacement_text=None: calls.append(
                ("clear_all", reminder_id, replacement_text)
            ),
            add_reminder=lambda **kwargs: calls.append(("add", kwargs)),
            format_snoozed_reminder_text=lambda text, when: f"{text}\n\n(Отложено до {when})",
            format_snoozed_answer_text=lambda when: f"Отложено до {when}",
            delete_old_snoozed_reminder_messages=async_delete_old_snoozed_reminder_messages,
            delete_other_reminder_messages=delete_other_reminder_messages,
        )
    )

    assert ("delete_other", 77, 555, 1002) in calls
    assert not any(call[0] == "clear_all" for call in calls)
    assert query.edits == ["meltan\n\n(Отложено до 03.07 14:56)"]
