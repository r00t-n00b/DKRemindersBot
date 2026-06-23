import asyncio
import main
from callback_simple_flows import (
    handle_done_callback_data,
    handle_noop_callback,
    handle_pastdate_callback,
    handle_self_remind_cancel_callback,
    handle_self_remind_event_cancel_callback,
    handle_snooze_cancel_callback_data,
    handle_snooze_current_month_callback,
)


class Query:
    def __init__(self):
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def test_pastdate_and_noop_callbacks_answer():
    past = Query()
    asyncio.run(handle_pastdate_callback(query=past))
    assert past.answers == [("Эта дата уже прошла. Выбери другую.", True)]

    noop = Query()
    asyncio.run(handle_noop_callback(query=noop))
    assert noop.answers == [(None, None)]


def test_self_remind_event_cancel_callback_parses_id_and_delegates():
    query = Query()
    calls = []

    async def helper(**kwargs):
        calls.append(kwargs)

    asyncio.run(
        handle_self_remind_event_cancel_callback(
            data="selfremind_event_cancel:123",
            query=query,
            parse_required_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            handle_self_remind_event_cancel=helper,
            get_reminder="get_reminder",
            get_self_remind_event_base="base",
            extract_event_datetime_from_text="extract",
            build_self_remind_choice_keyboard="choice",
            build_self_remind_event_before_keyboard="event",
            msg_invalid_reminder_id="invalid",
            msg_source_reminder_not_found="missing",
        )
    )

    assert calls[0]["reminder_id"] == 123
    assert calls[0]["msg_source_reminder_not_found"] == "missing"
    assert query.answers == []


def test_self_remind_event_cancel_callback_replies_invalid_id():
    query = Query()

    asyncio.run(
        handle_self_remind_event_cancel_callback(
            data="selfremind_event_cancel:bad",
            query=query,
            parse_required_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            handle_self_remind_event_cancel=None,
            get_reminder=None,
            get_self_remind_event_base=None,
            extract_event_datetime_from_text=None,
            build_self_remind_choice_keyboard=None,
            build_self_remind_event_before_keyboard=None,
            msg_invalid_reminder_id="invalid",
            msg_source_reminder_not_found="missing",
        )
    )

    assert query.answers == [("invalid", True)]


def test_self_remind_cancel_callback_parses_id_and_delegates():
    query = Query()
    calls = []

    async def helper(**kwargs):
        calls.append(kwargs)

    asyncio.run(
        handle_self_remind_cancel_callback(
            data="selfremind_cancel:123",
            query=query,
            context="context",
            parse_required_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            handle_self_remind_cancel=helper,
            get_reminder="get_reminder",
            get_source_chat_title_for_self_remind="title",
            build_self_remind_choice_keyboard="choice",
            msg_invalid_reminder_id="invalid",
            msg_source_reminder_not_found="missing",
        )
    )

    assert calls[0]["reminder_id"] == 123
    assert calls[0]["context"] == "context"
    assert query.answers == []


def test_done_callback_data_parses_optional_id_and_delegates():
    query = Query()
    calls = []

    async def helper(**kwargs):
        calls.append(kwargs)

    asyncio.run(
        handle_done_callback_data(
            data="done:123",
            query=query,
            context="context",
            parse_optional_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            handle_done_callback=helper,
            mark_reminder_acked="ack",
            clear_reminder_message_keyboards="clear",
            get_reminder="get",
            format_completed_reminder_text="fmt",
        )
    )

    assert calls[0]["reminder_id"] == 123
    assert calls[0]["mark_reminder_acked"] == "ack"


def test_snooze_current_month_callback_parses_id_and_delegates():
    query = Query()
    calls = []

    async def show_calendar(**kwargs):
        calls.append(kwargs)

    asyncio.run(
        handle_snooze_current_month_callback(
            data="snooze_caltoday:123",
            query=query,
            get_today=lambda: type("Day", (), {"year": 2026, "month": 4})(),
            parse_required_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            show_custom_snooze_calendar=show_calendar,
            build_custom_date_keyboard="date-kb",
        )
    )

    assert calls[0]["reminder_id"] == 123
    assert calls[0]["year"] == 2026
    assert calls[0]["build_custom_date_keyboard"] == "date-kb"
    assert calls[0]["ignore_edit_errors"] is True


def test_snooze_cancel_callback_data_parses_optional_id_and_delegates():
    query = Query()
    calls = []

    async def helper(**kwargs):
        calls.append(kwargs)

    asyncio.run(
        handle_snooze_cancel_callback_data(
            data="snooze_cancel:123",
            query=query,
            parse_optional_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            handle_custom_snooze_cancel=helper,
            mark_reminder_acked="ack",
            build_snooze_keyboard="kb",
            msg_invalid_reminder_id="invalid",
        )
    )

    assert calls[0]["reminder_id"] == 123
    assert calls[0]["build_snooze_keyboard"] == "kb"


def test_snooze_callback_uses_simple_flow_helpers():
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

    for required in [
        "handle_pastdate_callback(",
        "handle_self_remind_event_cancel_callback(",
        "handle_self_remind_cancel_callback(",
        "handle_done_callback_data(",
        "handle_snooze_current_month_callback(",
        "handle_snooze_cancel_callback_data(",
        "handle_noop_callback(",
    ]:
        assert required in snooze_source

    for forbidden in [
        'await query.answer("Эта дата уже прошла. Выбери другую.", show_alert=True)',
        'rid = parse_required_int_callback_id(data, prefix="selfremind_event_cancel:")',
        'rid = parse_required_int_callback_id(data, prefix="selfremind_cancel:")',
        'rid = parse_required_int_callback_id(data, prefix="snooze_caltoday:")',
        'rid = parse_optional_int_callback_id(data, prefix="done:")',
        'rid = parse_optional_int_callback_id(data, prefix="snooze_cancel:")',
        "today = datetime.now(TZ).date()",
    ]:
        assert forbidden not in snooze_source


def test_main_reexports_simple_flow_helpers():
    assert main.handle_pastdate_callback is handle_pastdate_callback
    assert main.handle_noop_callback is handle_noop_callback
    assert main.handle_done_callback_data is handle_done_callback_data
