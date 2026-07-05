from datetime import datetime, timezone
from types import SimpleNamespace

import main
from dkreminders_bot.commands.bulk_single_reminder import create_single_reminder_from_line


class Logger:
    def __init__(self):
        self.calls = []

    def info(self, *args):
        self.calls.append(args)


def test_create_single_reminder_from_line_creates_oneoff_reminder():
    logger = Logger()
    add_calls = []

    def add_reminder(**kwargs):
        add_calls.append(kwargs)
        return 101

    def parse_with_optional_default_time(parser, raw, now, *, default_time):
        assert parser == "date-parser"
        assert raw == "tomorrow 10:00 - milk"
        assert default_time == (9, 30)
        return datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc), "milk"

    create_single_reminder_from_line(
        line="tomorrow 10:00 - milk",
        now="now",
        target_chat_id=555,
        user=SimpleNamespace(id=42),
        default_time=(9, 30),
        looks_like_recurring=lambda line: False,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_recurring="rec-parser",
        parse_date_time_smart="date-parser",
        create_recurring_template=None,
        add_reminder=add_reminder,
        logger=logger,
    )

    assert add_calls == [
        {
            "chat_id": 555,
            "text": "milk",
            "remind_at": datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
            "created_by": 42,
        }
    ]
    assert logger.calls


def test_create_single_reminder_from_line_creates_recurring_reminder():
    logger = Logger()
    template_calls = []
    add_calls = []

    def create_recurring_template(**kwargs):
        template_calls.append(kwargs)
        return 77

    def add_reminder(**kwargs):
        add_calls.append(kwargs)
        return 102

    def parse_with_optional_default_time(parser, raw, now, *, default_time):
        assert parser == "rec-parser"
        assert raw == "every day 10:00 - water"
        assert default_time == (8, 0)
        return (
            datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
            "water",
            "daily",
            {"interval": 1},
            10,
            0,
        )

    create_single_reminder_from_line(
        line="every day 10:00 - water",
        now="now",
        target_chat_id=555,
        user=SimpleNamespace(id=42),
        default_time=(8, 0),
        looks_like_recurring=lambda line: True,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_recurring="rec-parser",
        parse_date_time_smart="date-parser",
        create_recurring_template=create_recurring_template,
        add_reminder=add_reminder,
        logger=logger,
    )

    assert template_calls == [
        {
            "chat_id": 555,
            "text": "water",
            "pattern_type": "daily",
            "payload": {"interval": 1},
            "time_hour": 10,
            "time_minute": 0,
            "created_by": 42,
        }
    ]
    assert add_calls == [
        {
            "chat_id": 555,
            "text": "water",
            "remind_at": datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
            "created_by": 42,
            "template_id": 77,
        }
    ]
    assert logger.calls


def test_main_wrapper_delegates_to_bulk_single_creator(monkeypatch):
    calls = []

    def fake_create_single_reminder_from_line(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(main, "create_single_reminder_from_line", fake_create_single_reminder_from_line)

    main._create_single_reminder_from_line(
        line="tomorrow 10:00 - milk",
        now="now",
        target_chat_id=555,
        user=SimpleNamespace(id=42),
        default_time=(9, 30),
    )

    assert calls
    assert calls[0]["line"] == "tomorrow 10:00 - milk"
    assert calls[0]["target_chat_id"] == 555
    assert calls[0]["user"].id == 42
    assert calls[0]["default_time"] == (9, 30)
    assert calls[0]["add_reminder"] is main.add_reminder
    assert calls[0]["create_recurring_template"] is main.create_recurring_template


def test_bulk_creation_logic_is_no_longer_in_main_wrapper():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_create_single_reminder_from_line"
    ]
    assert len(nodes) == 1

    wrapper_source = ast.get_source_segment(source, nodes[0])
    assert "create_single_reminder_from_line(" in wrapper_source
    assert "Создан bulk recurring reminder" not in wrapper_source
    assert "Создан bulk reminder id=" not in wrapper_source
