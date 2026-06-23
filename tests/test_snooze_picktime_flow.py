import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from snooze_picktime_flow import handle_custom_snooze_picktime


class Query:
    def __init__(self):
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

    async def clear_reminder_message_keyboards(bot, rid):
        calls.append(("clear", bot, rid))

    async def apply_snooze_to_reminder(**kwargs):
        calls.append(("apply", kwargs))

    async def run():
        await handle_custom_snooze_picktime(
            reminder_id=overrides.pop("reminder_id", 123),
            date_str=overrides.pop("date_str", "2026-07-15"),
            time_str=overrides.pop("time_str", "10:30"),
            query=query,
            context=overrides.pop("context", SimpleNamespace(bot="bot")),
            tz=overrides.pop("tz", timezone.utc),
            get_now=overrides.pop("get_now", lambda: datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)),
            get_reminder=overrides.pop("get_reminder", lambda rid: reminder),
            mark_reminder_acked=overrides.pop("mark_reminder_acked", lambda rid: calls.append(("acked", rid))),
            clear_reminder_message_keyboards=clear_reminder_message_keyboards,
            add_reminder=overrides.pop("add_reminder", lambda **kwargs: calls.append(("add", kwargs))),
            apply_snooze_to_reminder=apply_snooze_to_reminder,
            format_snoozed_reminder_text=overrides.pop("format_snoozed_reminder_text", lambda text, when: f"snoozed {when}: {text}"),
            format_snoozed_answer_text=overrides.pop("format_snoozed_answer_text", lambda when: f"answer {when}"),
            msg_reminder_not_found=overrides.pop("msg_reminder_not_found", "not found"),
            msg_reschedule_bad_datetime=overrides.pop("msg_reschedule_bad_datetime", "bad datetime"),
            msg_reschedule_past_time=overrides.pop("msg_reschedule_past_time", "past time"),
        )
        assert not overrides, f"unused overrides: {overrides}"

    asyncio.run(run())
    return calls, query


def test_picktime_replies_not_found_when_reminder_missing():
    calls, query = run_handler(get_reminder=lambda rid: None)

    assert calls == []
    assert query.answers == [("not found", True)]


def test_picktime_replies_bad_datetime_for_invalid_date_or_time():
    calls, query = run_handler(date_str="bad-date")

    assert calls == []
    assert query.answers == [("bad datetime", True)]


def test_picktime_replies_past_time_for_non_future_datetime():
    calls, query = run_handler(
        get_now=lambda: datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc),
    )

    assert calls == []
    assert query.answers == [("past time", True)]


def test_picktime_applies_snooze_for_valid_future_datetime():
    reminder = SimpleNamespace(id=123, chat_id=555, text="milk", created_by=42)

    calls, query = run_handler(reminder=reminder)

    assert query.answers == []
    assert len(calls) == 1
    name, kwargs = calls[0]
    assert name == "apply"
    assert kwargs["reminder"] is reminder
    assert kwargs["new_dt"] == datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)
    assert kwargs["mark_reminder_acked"] is not None
    assert kwargs["clear_reminder_message_keyboards"] is not None


def test_snooze_callback_uses_picktime_flow_helper():
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
    assert "handle_custom_snooze_picktime(" in snooze_source

    picktime_start = snooze_source.index('if data.startswith("snooze_picktime:"):')
    cancel_start = snooze_source.index('if data.startswith("snooze_cancel:"):', picktime_start)
    picktime_source = snooze_source[picktime_start:cancel_start]

    assert "year, month, day = map(int, date_str.split" not in picktime_source
    assert "hour, minute = map(int, time_str.split" not in picktime_source
    assert "new_dt = datetime(year, month, day, hour, minute" not in picktime_source


def test_main_reexports_picktime_flow_helper():
    assert main.handle_custom_snooze_picktime is handle_custom_snooze_picktime
