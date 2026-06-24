import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from single_recurring_reminder import try_handle_single_recurring_reminder


class Logger:
    def __init__(self):
        self.calls = []

    def info(self, *args):
        self.calls.append(args)


class Message:
    def __init__(self):
        self.replies = []


async def safe_reply(message, text, **kwargs):
    message.replies.append((text, kwargs))


def run_handler(**overrides):
    message = overrides.pop("message", Message())
    logger = overrides.pop("logger", Logger())

    async def run():
        result = await try_handle_single_recurring_reminder(
            raw_single=overrides.pop("raw_single", "every day 10:00 - water"),
            now=overrides.pop("now", "now"),
            target_chat_id=overrides.pop("target_chat_id", 555),
            used_alias=overrides.pop("used_alias", None),
            chat=overrides.pop("chat", SimpleNamespace(id=100)),
            user=overrides.pop("user", SimpleNamespace(id=42)),
            message=message,
            is_private=overrides.pop("is_private", True),
            default_time=overrides.pop("default_time", (9, 30)),
            looks_like_recurring=overrides.pop("looks_like_recurring", lambda raw: True),
            parse_with_optional_default_time=overrides.pop("parse_with_optional_default_time"),
            parse_recurring=overrides.pop("parse_recurring", "parse-recurring"),
            create_recurring_template=overrides.pop("create_recurring_template"),
            add_reminder=overrides.pop("add_reminder"),
            build_created_reminder_actions_keyboard=overrides.pop("build_created_reminder_actions_keyboard", lambda reminder_id, is_recurring=False: f"kb:{reminder_id}:{is_recurring}"),
            format_recurring_human=overrides.pop("format_recurring_human", lambda pattern_type, payload: "каждый день"),
            format_created_recurring_reminder_text=overrides.pop("format_created_recurring_reminder_text", lambda when, text, human, chat_alias=None: f"created {when} {text} {human} {chat_alias}"),
            msg_recurring_parse_failed=overrides.pop("msg_recurring_parse_failed", lambda is_private: f"parse failed private={is_private}"),
            safe_reply=safe_reply,
            logger=logger,
        )
        assert not overrides, f"unused overrides: {overrides}"
        return result

    return asyncio.run(run()), message, logger


def test_single_recurring_handler_noops_for_non_recurring_line():
    result, message, logger = run_handler(
        raw_single="tomorrow 10:00 - water",
        looks_like_recurring=lambda raw: False,
        parse_with_optional_default_time=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not parse")),
        create_recurring_template=lambda **kw: None,
        add_reminder=lambda **kw: None,
    )

    assert result is False
    assert message.replies == []
    assert logger.calls == []


def test_single_recurring_handler_replies_on_parse_error():
    def parse_with_optional_default_time(*args, **kwargs):
        raise ValueError("bad recurring")

    result, message, logger = run_handler(
        parse_with_optional_default_time=parse_with_optional_default_time,
        create_recurring_template=lambda **kw: None,
        add_reminder=lambda **kw: None,
    )

    assert result is True
    assert message.replies == [("parse failed private=True", {})]
    assert logger.calls


def test_single_recurring_handler_creates_template_and_reminder_and_replies():
    template_calls = []
    reminder_calls = []

    first_dt = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    def parse_with_optional_default_time(parser, raw, now, *, default_time):
        assert parser == "parse-recurring"
        assert raw == "every day 10:00 - water"
        assert default_time == (9, 30)
        return first_dt, "water", "daily", {"interval": 1}, 10, 0

    def create_recurring_template(**kwargs):
        template_calls.append(kwargs)
        return 77

    def add_reminder(**kwargs):
        reminder_calls.append(kwargs)
        return 101

    result, message, logger = run_handler(
        used_alias="home",
        parse_with_optional_default_time=parse_with_optional_default_time,
        create_recurring_template=create_recurring_template,
        add_reminder=add_reminder,
    )

    assert result is True
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
    assert reminder_calls == [
        {
            "chat_id": 555,
            "text": "water",
            "remind_at": first_dt,
            "created_by": 42,
            "template_id": 77,
        }
    ]
    assert message.replies == [
        ("created 02.01 10:00 water каждый день home", {"reply_markup": "kb:101:True"})
    ]
    assert logger.calls


def test_main_uses_single_recurring_handler_in_remind_command():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    remind_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remind_command"
    ]
    assert len(remind_nodes) == 1

    remind_source = ast.get_source_segment(source, remind_nodes[0])
    dispatch_source = Path("remind_dispatch.py").read_text()

    assert "dispatch_remind_creation(" in remind_source
    assert "try_handle_single_recurring_reminder(" in dispatch_source
    assert "if looks_like_recurring(raw_single):" not in remind_source
    assert "Создан recurring reminder id=" not in remind_source


def test_main_reexports_single_recurring_handler():
    assert main.try_handle_single_recurring_reminder is try_handle_single_recurring_reminder
