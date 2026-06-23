import asyncio

import main
from snooze_calendar_nav import show_custom_snooze_calendar


class Query:
    def __init__(self, *, fail_edit=False):
        self.fail_edit = fail_edit
        self.markups = []
        self.answers = 0

    async def edit_message_reply_markup(self, reply_markup=None):
        if self.fail_edit:
            raise RuntimeError("edit failed")
        self.markups.append(reply_markup)

    async def answer(self):
        self.answers += 1


def test_show_custom_snooze_calendar_updates_markup_and_answers():
    query = Query()

    asyncio.run(
        show_custom_snooze_calendar(
            reminder_id=123,
            query=query,
            year=2026,
            month=7,
            build_custom_date_keyboard=lambda rid, year, month: f"kb:{rid}:{year}:{month}",
        )
    )

    assert query.markups == ["kb:123:2026:7"]
    assert query.answers == 1


def test_show_custom_snooze_calendar_can_ignore_edit_errors():
    query = Query(fail_edit=True)

    asyncio.run(
        show_custom_snooze_calendar(
            reminder_id=123,
            query=query,
            year=2026,
            month=7,
            build_custom_date_keyboard=lambda rid, year, month: f"kb:{rid}:{year}:{month}",
            ignore_edit_errors=True,
        )
    )

    assert query.markups == []
    assert query.answers == 1


def test_show_custom_snooze_calendar_raises_edit_errors_by_default():
    query = Query(fail_edit=True)

    try:
        asyncio.run(
            show_custom_snooze_calendar(
                reminder_id=123,
                query=query,
                year=2026,
                month=7,
                build_custom_date_keyboard=lambda rid, year, month: f"kb:{rid}:{year}:{month}",
            )
        )
    except RuntimeError as e:
        assert str(e) == "edit failed"
    else:
        raise AssertionError("expected edit failure")


def test_snooze_callback_uses_calendar_nav_helper():
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
    assert snooze_source.count("show_custom_snooze_calendar(") == 1
    assert "kb = build_custom_date_keyboard(rid, year=year, month=month)" not in snooze_source
    assert "kb = build_custom_date_keyboard(rid, year=today.year, month=today.month)" not in snooze_source


def test_main_reexports_calendar_nav_helper():
    assert main.show_custom_snooze_calendar is show_custom_snooze_calendar
