import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from dkreminders_bot.callbacks.snooze_direct_flow import handle_direct_snooze_action


class Query:
    def __init__(self, user_id=42):
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def run_handler(**overrides):
    calls = []
    query = overrides.pop("query", Query())
    reminder = overrides.pop(
        "reminder",
        SimpleNamespace(id=123, chat_id=555, text="milk", created_by=42),
    )
    new_dt = overrides.pop("new_dt", datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc))

    async def enter_custom_snooze_flow(**kwargs):
        calls.append(("custom", kwargs))

    async def apply_snooze_to_reminder(**kwargs):
        calls.append(("apply", kwargs))

    async def clear_reminder_message_keyboards(bot, rid):
        calls.append(("clear", bot, rid))

    async def run():
        await handle_direct_snooze_action(
            reminder_id=overrides.pop("reminder_id", 123),
            action=overrides.pop("action", "1h"),
            query=query,
            context=overrides.pop("context", SimpleNamespace(bot="bot")),
            get_now=overrides.pop("get_now", lambda: datetime(2026, 7, 15, 9, 30, tzinfo=timezone.utc)),
            get_user_default_time=overrides.pop("get_user_default_time", lambda user_id: ("default", user_id)),
            get_reminder=overrides.pop("get_reminder", lambda rid: reminder),
            compute_snooze_target_time=overrides.pop("compute_snooze_target_time", lambda action, now, *, default_time: new_dt),
            enter_custom_snooze_flow=enter_custom_snooze_flow,
            apply_snooze_to_reminder=apply_snooze_to_reminder,
            mark_reminder_acked=overrides.pop("mark_reminder_acked", lambda rid: calls.append(("acked", rid))),
            clear_reminder_message_keyboards=clear_reminder_message_keyboards,
            add_reminder=overrides.pop("add_reminder", lambda **kwargs: calls.append(("add", kwargs))),
            build_custom_date_keyboard=overrides.pop("build_custom_date_keyboard", lambda rid: f"date-kb:{rid}"),
            format_snoozed_reminder_text=overrides.pop("format_snoozed_reminder_text", lambda text, when: f"snoozed {when}: {text}"),
            format_snoozed_answer_text=overrides.pop("format_snoozed_answer_text", lambda when: f"answer {when}"),
            delete_old_snoozed_reminder_messages=overrides.pop("delete_old_snoozed_reminder_messages", None),
            delete_other_reminder_messages=overrides.pop("delete_other_reminder_messages", None),
            msg_reminder_not_found=overrides.pop("msg_reminder_not_found", "not found"),
            msg_reschedule_unknown_action=overrides.pop("msg_reschedule_unknown_action", "unknown action"),
        )
        assert not overrides, f"unused overrides: {overrides}"

    asyncio.run(run())
    return calls, query


def test_direct_snooze_replies_not_found_when_reminder_missing():
    calls, query = run_handler(get_reminder=lambda rid: None)

    assert calls == []
    assert query.answers == [("not found", True)]


def test_direct_snooze_enters_custom_flow_for_custom_action():
    calls, query = run_handler(action="custom")

    assert query.answers == []
    assert len(calls) == 1
    name, kwargs = calls[0]
    assert name == "custom"
    assert kwargs["reminder_id"] == 123
    assert kwargs["mark_reminder_acked"] is not None
    assert kwargs["build_custom_date_keyboard"] is not None


def test_direct_snooze_replies_unknown_action_when_target_time_fails():
    def compute_snooze_target_time(action, now, *, default_time):
        assert default_time == ("default", 42)
        raise ValueError("bad action")

    calls, query = run_handler(compute_snooze_target_time=compute_snooze_target_time)

    assert calls == []
    assert query.answers == [("unknown action", True)]


def test_direct_snooze_applies_snooze_for_valid_action():
    reminder = SimpleNamespace(id=123, chat_id=555, text="milk", created_by=42)
    new_dt = datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)

    calls, query = run_handler(reminder=reminder, new_dt=new_dt)

    assert query.answers == []
    assert len(calls) == 1
    name, kwargs = calls[0]
    assert name == "apply"
    assert kwargs["reminder"] is reminder
    assert kwargs["new_dt"] == new_dt
    assert kwargs["mark_reminder_acked"] is not None
    assert kwargs["clear_reminder_message_keyboards"] is not None


def test_snooze_callback_uses_direct_snooze_flow_helper():
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
    assert "handle_direct_snooze_action(" in snooze_source

    direct_start = snooze_source.index('if data.startswith("snooze:"):')
    cal_start = snooze_source.index('if data.startswith("snooze_cal:"):', direct_start)
    direct_source = snooze_source[direct_start:cal_start]

    assert "r = get_reminder(rid)" not in direct_source
    assert 'if action == "custom":' not in direct_source
    assert "compute_snooze_target_time(" not in direct_source
    assert "await apply_snooze_to_reminder(" not in direct_source


def test_main_reexports_direct_snooze_flow_helper():
    assert main.handle_direct_snooze_action is handle_direct_snooze_action



def test_direct_snooze_passes_delete_other_messages_to_apply():
    async def delete_other_reminder_messages(*args, **kwargs):
        pass

    calls, query = run_handler(delete_other_reminder_messages=delete_other_reminder_messages)

    assert query.answers == []
    assert len(calls) == 1
    name, kwargs = calls[0]
    assert name == "apply"
    assert kwargs["delete_other_reminder_messages"] is delete_other_reminder_messages


def test_snooze_router_threads_delete_other_messages_into_direct_flow():
    from pathlib import Path

    source = Path("dkreminders_bot/callbacks/reminder_callback_router.py").read_text()
    assert "delete_other_reminder_messages = deps.delete_other_reminder_messages" in source

    direct_start = source.index('if data.startswith("snooze:"):')
    cal_start = source.index('if data.startswith("snooze_cal:"):', direct_start)
    direct_source = source[direct_start:cal_start]

    assert "delete_other_reminder_messages=delete_other_reminder_messages" in direct_source
