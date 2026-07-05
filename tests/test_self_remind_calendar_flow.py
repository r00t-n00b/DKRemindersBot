import asyncio
from types import SimpleNamespace

import main
from dkreminders_bot.callbacks.self_remind_calendar_flow import (
    get_self_remind_callback_prefix,
    handle_self_remind_calendar_month,
    handle_self_remind_calendar_today,
    handle_self_remind_pickdate,
)


class Query:
    def __init__(self, *, fail_markup=False):
        self.fail_markup = fail_markup
        self.markups = []
        self.answers = []

    async def edit_message_reply_markup(self, reply_markup=None):
        if self.fail_markup:
            raise RuntimeError("edit failed")
        self.markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def test_get_self_remind_callback_prefix_detects_regular_and_event_prefix():
    assert get_self_remind_callback_prefix("selfremind_caltoday:123") == "selfremind"
    assert get_self_remind_callback_prefix("selfremind_event_caltoday:123") == "selfremind_event"


def test_self_remind_calendar_today_opens_regular_calendar():
    query = Query()

    asyncio.run(
        handle_self_remind_calendar_today(
            data="selfremind_caltoday:123",
            query=query,
            get_today=lambda: SimpleNamespace(year=2026, month=7),
            parse_required_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            build_custom_date_keyboard=lambda rid, *, year, month, callback_prefix: f"date-kb:{rid}:{year}:{month}:{callback_prefix}",
        )
    )

    assert query.markups == ["date-kb:123:2026:7:selfremind"]
    assert query.answers == [(None, None)]


def test_self_remind_calendar_today_opens_event_calendar_and_ignores_edit_error():
    query = Query(fail_markup=True)

    asyncio.run(
        handle_self_remind_calendar_today(
            data="selfremind_event_caltoday:123",
            query=query,
            get_today=lambda: SimpleNamespace(year=2026, month=7),
            parse_required_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            build_custom_date_keyboard=lambda rid, *, year, month, callback_prefix: f"date-kb:{rid}:{year}:{month}:{callback_prefix}",
        )
    )

    assert query.markups == []
    assert query.answers == [(None, None)]


def test_self_remind_pickdate_opens_regular_time_picker():
    query = Query()

    asyncio.run(
        handle_self_remind_pickdate(
            data="selfremind_pickdate:123:2026-07-15",
            query=query,
            parse_required_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            build_custom_time_keyboard=lambda rid, date_str, *, callback_prefix: f"time-kb:{rid}:{date_str}:{callback_prefix}",
        )
    )

    assert query.markups == ["time-kb:123:2026-07-15:selfremind"]
    assert query.answers == [("Выбери время", None)]


def test_self_remind_pickdate_opens_event_time_picker():
    query = Query()

    asyncio.run(
        handle_self_remind_pickdate(
            data="selfremind_event_pickdate:123:2026-07-15",
            query=query,
            parse_required_int_callback_id=lambda data, *, prefix: int(data[len(prefix):]),
            build_custom_time_keyboard=lambda rid, date_str, *, callback_prefix: f"time-kb:{rid}:{date_str}:{callback_prefix}",
        )
    )

    assert query.markups == ["time-kb:123:2026-07-15:selfremind_event"]
    assert query.answers == [("Выбери время", None)]


def test_snooze_callback_uses_self_remind_calendar_helpers():
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

    today_start = snooze_source.index('if data.startswith("selfremind_caltoday:") or data.startswith("selfremind_event_caltoday:"):')
    picktime_start = snooze_source.index('if data.startswith("selfremind_picktime:") or data.startswith("selfremind_event_picktime:"):', today_start)
    calendar_source = snooze_source[today_start:picktime_start]

    assert "handle_self_remind_calendar_today(" in calendar_source
    assert "handle_self_remind_pickdate(" in calendar_source
    assert "build_custom_date_keyboard(" not in calendar_source
    assert "build_custom_time_keyboard(rid, date_str" not in calendar_source
    assert 'await query.answer("Выбери время")' not in calendar_source


def test_main_reexports_self_remind_calendar_helpers():
    assert main.handle_self_remind_calendar_today is handle_self_remind_calendar_today
    assert main.handle_self_remind_pickdate is handle_self_remind_pickdate


def test_self_remind_calendar_month_opens_regular_month():
    query = Query()

    asyncio.run(
        handle_self_remind_calendar_month(
            data="selfremind_cal:123:2026-07",
            query=query,
            build_custom_date_keyboard=lambda rid, *, year, month, callback_prefix: f"date-kb:{rid}:{year}:{month}:{callback_prefix}",
        )
    )

    assert query.markups == ["date-kb:123:2026:7:selfremind"]
    assert query.answers == [(None, None)]


def test_self_remind_calendar_month_opens_event_month():
    query = Query()

    asyncio.run(
        handle_self_remind_calendar_month(
            data="selfremind_event_cal:123:2026-07",
            query=query,
            build_custom_date_keyboard=lambda rid, *, year, month, callback_prefix: f"date-kb:{rid}:{year}:{month}:{callback_prefix}",
        )
    )

    assert query.markups == ["date-kb:123:2026:7:selfremind_event"]
    assert query.answers == [(None, None)]


def test_self_remind_calendar_month_rejects_bad_id_or_month():
    query = Query()

    try:
        asyncio.run(
            handle_self_remind_calendar_month(
                data="selfremind_cal:bad:2026-07",
                query=query,
                build_custom_date_keyboard=lambda rid, *, year, month, callback_prefix: None,
            )
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for bad id")

    try:
        asyncio.run(
            handle_self_remind_calendar_month(
                data="selfremind_cal:123:2026-bad",
                query=query,
                build_custom_date_keyboard=lambda rid, *, year, month, callback_prefix: None,
            )
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for bad month")


def test_snooze_callback_uses_self_remind_calendar_month_helper():
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

    assert "handle_self_remind_calendar_month" in source

    cal_start = snooze_source.index('if data.startswith("selfremind_cal:") or data.startswith("selfremind_event_cal:"):')
    today_start = snooze_source.index('if data.startswith("selfremind_caltoday:") or data.startswith("selfremind_event_caltoday:"):', cal_start)
    cal_source = snooze_source[cal_start:today_start]

    assert "handle_self_remind_calendar_month(" in cal_source
    assert '_, rid_str, ym = data.split(":", 2)' not in cal_source
    assert "year_str, month_str = ym.split" not in cal_source
    assert "callback_prefix =" not in cal_source
