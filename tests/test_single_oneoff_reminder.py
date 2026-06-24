import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from single_oneoff_reminder import handle_single_oneoff_reminder


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
        await handle_single_oneoff_reminder(
            raw_single=overrides.pop("raw_single", "tomorrow 10:00 - milk"),
            now=overrides.pop("now", "now"),
            target_chat_id=overrides.pop("target_chat_id", 555),
            used_alias=overrides.pop("used_alias", None),
            chat=overrides.pop("chat", SimpleNamespace(id=555, type="private")),
            user=overrides.pop("user", SimpleNamespace(id=42)),
            message=message,
            default_time=overrides.pop("default_time", (9, 30)),
            private_chat_type=overrides.pop("private_chat_type", "private"),
            parse_with_optional_default_time=overrides.pop("parse_with_optional_default_time"),
            parse_date_time_smart=overrides.pop("parse_date_time_smart", "date-parser"),
            normalize_plain_text_reminder_with_gemini=overrides.pop("normalize_plain_text_reminder_with_gemini", None),
            normalize_gemini_reminder_command_text=overrides.pop("normalize_gemini_reminder_command_text", lambda text: text),
            normalize_reminder_text_fallback=overrides.pop("normalize_reminder_text_fallback", lambda text: text),
            add_reminder=overrides.pop("add_reminder"),
            build_created_reminder_actions_keyboard=overrides.pop("build_created_reminder_actions_keyboard", lambda reminder_id: f"kb:{reminder_id}"),
            format_created_reminder_text=overrides.pop("format_created_reminder_text", lambda when, text: f"created {when}: {text}"),
            msg_parse_date_text_failed=overrides.pop("msg_parse_date_text_failed", "parse failed"),
            safe_reply=safe_reply,
            logger=logger,
        )
        assert not overrides, f"unused overrides: {overrides}"

    asyncio.run(run())
    return message, logger


def test_single_oneoff_handler_creates_reminder_and_replies_in_same_chat():
    add_calls = []
    remind_at = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    def parse_with_optional_default_time(parser, raw, now, *, default_time):
        assert parser == "date-parser"
        assert raw == "tomorrow 10:00 - milk"
        assert default_time == (9, 30)
        return remind_at, "milk"

    def add_reminder(**kwargs):
        add_calls.append(kwargs)
        return 101

    message, logger = run_handler(
        parse_with_optional_default_time=parse_with_optional_default_time,
        add_reminder=add_reminder,
    )

    assert add_calls == [
        {
            "chat_id": 555,
            "text": "milk",
            "remind_at": remind_at,
            "created_by": 42,
        }
    ]
    assert message.replies == [("created 02.01 10:00: milk", {"reply_markup": "kb:101"})]
    assert logger.calls


def test_single_oneoff_handler_replies_with_alias_text():
    remind_at = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    def parse_with_optional_default_time(parser, raw, now, *, default_time):
        return remind_at, "milk"

    message, _ = run_handler(
        used_alias="home",
        parse_with_optional_default_time=parse_with_optional_default_time,
        add_reminder=lambda **kwargs: 101,
    )

    assert message.replies == [
        ("Ок, напомню в чате 'home' 02.01 10:00: milk", {"reply_markup": "kb:101"})
    ]


def test_single_oneoff_handler_replies_with_other_person_text_in_private_chat():
    remind_at = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    def parse_with_optional_default_time(parser, raw, now, *, default_time):
        return remind_at, "milk"

    message, _ = run_handler(
        target_chat_id=777,
        chat=SimpleNamespace(id=555, type="private"),
        parse_with_optional_default_time=parse_with_optional_default_time,
        add_reminder=lambda **kwargs: 101,
    )

    assert message.replies == [
        ("Ок, напомню этому человеку 02.01 10:00: milk", {"reply_markup": "kb:101"})
    ]


def test_single_oneoff_handler_uses_gemini_fallback_after_parse_error():
    calls = []
    remind_at = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)

    def parse_with_optional_default_time(parser, raw, now, *, default_time):
        calls.append(raw)
        if raw == "bad raw":
            raise ValueError("bad")
        assert raw == "tomorrow 10:00 - milk"
        return remind_at, "milk"

    async def normalize_plain_text_reminder_with_gemini(raw, created_by):
        assert raw == "bad raw"
        assert created_by == 42
        return "/remind tomorrow 10:00 - milk"

    message, _ = run_handler(
        raw_single="bad raw",
        parse_with_optional_default_time=parse_with_optional_default_time,
        normalize_plain_text_reminder_with_gemini=normalize_plain_text_reminder_with_gemini,
        normalize_gemini_reminder_command_text=lambda text: text,
        normalize_reminder_text_fallback=lambda text: text,
        add_reminder=lambda **kwargs: 101,
    )

    assert calls == ["bad raw", "tomorrow 10:00 - milk"]
    assert message.replies == [("created 02.01 10:00: milk", {"reply_markup": "kb:101"})]


def test_single_oneoff_handler_replies_parse_failed_when_gemini_says_no_reminder():
    def parse_with_optional_default_time(parser, raw, now, *, default_time):
        raise ValueError("bad")

    async def normalize_plain_text_reminder_with_gemini(raw, created_by):
        return "NO_REMINDER"

    message, _ = run_handler(
        raw_single="bad raw",
        parse_with_optional_default_time=parse_with_optional_default_time,
        normalize_plain_text_reminder_with_gemini=normalize_plain_text_reminder_with_gemini,
        add_reminder=lambda **kwargs: 101,
    )

    assert message.replies == [("parse failed", {})]


def test_main_uses_single_oneoff_handler_in_remind_command():
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
    assert "handle_single_oneoff_reminder(" in dispatch_source
    assert "normalize_plain_text_reminder_with_gemini(raw_single, created_by)" not in remind_source
    assert "format_created_reminder_text(when_str, text)" not in remind_source


def test_main_reexports_single_oneoff_handler():
    assert main.handle_single_oneoff_reminder is handle_single_oneoff_reminder
