import asyncio
from types import SimpleNamespace

from remind_dispatch import dispatch_remind_creation


async def safe_reply(message, text):
    message.replies.append(text)


def test_dispatch_bulk_creates_each_normalized_line_and_replies_summary():
    message = SimpleNamespace(replies=[])
    user = SimpleNamespace(id=42)
    calls = []

    def create_single_reminder_from_line(**kwargs):
        calls.append(kwargs)

    def format_bulk_result(**kwargs):
        return f"created={kwargs['created']} failed={kwargs['failed']}"

    asyncio.run(dispatch_remind_creation(
        had_newline=True,
        raw_args="Header\n- tomorrow 10:00 - one\n28.11 12:00 - two",
        now="NOW",
        target_chat_id=100,
        used_alias=None,
        chat=SimpleNamespace(id=100, type="private"),
        user=user,
        message=message,
        is_private=True,
        default_time=(9, 0),
        private_chat_type="private",
        looks_like_recurring=lambda text: False,
        drop_optional_bulk_header=lambda lines, looks_like_recurring: lines[1:],
        create_single_reminder_from_line=create_single_reminder_from_line,
        format_bulk_result=format_bulk_result,
        try_handle_single_recurring_reminder=None,
        handle_single_oneoff_reminder=None,
        parse_with_optional_default_time=None,
        parse_recurring=None,
        create_recurring_template=None,
        add_reminder=None,
        build_created_reminder_actions_keyboard=None,
        format_recurring_human=None,
        format_created_recurring_reminder_text=None,
        msg_recurring_parse_failed=None,
        parse_date_time_smart=None,
        normalize_plain_text_reminder_with_gemini=None,
        normalize_gemini_reminder_command_text=None,
        normalize_reminder_text_fallback=None,
        format_created_reminder_text=None,
        msg_parse_date_text_failed=None,
        safe_reply=safe_reply,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    ))

    assert [call["line"] for call in calls] == [
        "tomorrow 10:00 - one",
        "28.11 12:00 - two",
    ]
    assert all(call["now"] == "NOW" for call in calls)
    assert all(call["target_chat_id"] == 100 for call in calls)
    assert message.replies == ["created=2 failed=0"]


def test_dispatch_bulk_reports_failed_lines():
    message = SimpleNamespace(replies=[])
    user = SimpleNamespace(id=42)

    def create_single_reminder_from_line(**kwargs):
        if "bad" in kwargs["line"]:
            raise ValueError("bad line")

    seen = {}

    def format_bulk_result(**kwargs):
        seen.update(kwargs)
        return "summary"

    asyncio.run(dispatch_remind_creation(
        had_newline=True,
        raw_args="- good\n- bad",
        now="NOW",
        target_chat_id=100,
        used_alias=None,
        chat=SimpleNamespace(id=100, type="private"),
        user=user,
        message=message,
        is_private=True,
        default_time=(9, 0),
        private_chat_type="private",
        looks_like_recurring=lambda text: False,
        drop_optional_bulk_header=lambda lines, looks_like_recurring: lines,
        create_single_reminder_from_line=create_single_reminder_from_line,
        format_bulk_result=format_bulk_result,
        try_handle_single_recurring_reminder=None,
        handle_single_oneoff_reminder=None,
        parse_with_optional_default_time=None,
        parse_recurring=None,
        create_recurring_template=None,
        add_reminder=None,
        build_created_reminder_actions_keyboard=None,
        format_recurring_human=None,
        format_created_recurring_reminder_text=None,
        msg_recurring_parse_failed=None,
        parse_date_time_smart=None,
        normalize_plain_text_reminder_with_gemini=None,
        normalize_gemini_reminder_command_text=None,
        normalize_reminder_text_fallback=None,
        format_created_reminder_text=None,
        msg_parse_date_text_failed=None,
        safe_reply=safe_reply,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    ))

    assert seen["created"] == 1
    assert seen["failed"] == 1
    assert seen["error_lines"] == [(2, "bad", "bad line")]
    assert message.replies == ["summary"]


def test_dispatch_single_recurring_short_circuits_oneoff():
    message = SimpleNamespace(replies=[])
    calls = []

    async def recurring(**kwargs):
        calls.append(("recurring", kwargs))
        return True

    async def oneoff(**kwargs):
        calls.append(("oneoff", kwargs))

    asyncio.run(dispatch_remind_creation(
        had_newline=False,
        raw_args="every day - standup",
        now="NOW",
        target_chat_id=100,
        used_alias="team",
        chat=SimpleNamespace(id=100, type="private"),
        user=SimpleNamespace(id=42),
        message=message,
        is_private=True,
        default_time=(9, 0),
        private_chat_type="private",
        looks_like_recurring=lambda text: True,
        drop_optional_bulk_header=None,
        create_single_reminder_from_line=None,
        format_bulk_result=None,
        try_handle_single_recurring_reminder=recurring,
        handle_single_oneoff_reminder=oneoff,
        parse_with_optional_default_time="parse_with_default",
        parse_recurring="parse_recurring",
        create_recurring_template="template",
        add_reminder="add",
        build_created_reminder_actions_keyboard="keyboard",
        format_recurring_human="human",
        format_created_recurring_reminder_text="format_recurring",
        msg_recurring_parse_failed="recurring_failed",
        parse_date_time_smart="date_time",
        normalize_plain_text_reminder_with_gemini="gemini",
        normalize_gemini_reminder_command_text="gemini_text",
        normalize_reminder_text_fallback="fallback",
        format_created_reminder_text="format_oneoff",
        msg_parse_date_text_failed="parse_failed",
        safe_reply=safe_reply,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    ))

    assert [name for name, _ in calls] == ["recurring"]
    assert calls[0][1]["raw_single"] == "every day - standup"
    assert calls[0][1]["target_chat_id"] == 100
    assert calls[0][1]["used_alias"] == "team"


def test_dispatch_single_falls_through_to_oneoff():
    message = SimpleNamespace(replies=[])
    calls = []

    async def recurring(**kwargs):
        calls.append(("recurring", kwargs))
        return False

    async def oneoff(**kwargs):
        calls.append(("oneoff", kwargs))

    asyncio.run(dispatch_remind_creation(
        had_newline=False,
        raw_args="tomorrow 10:00 - milk",
        now="NOW",
        target_chat_id=100,
        used_alias=None,
        chat=SimpleNamespace(id=100, type="private"),
        user=SimpleNamespace(id=42),
        message=message,
        is_private=True,
        default_time=(9, 0),
        private_chat_type="private",
        looks_like_recurring=lambda text: False,
        drop_optional_bulk_header=None,
        create_single_reminder_from_line=None,
        format_bulk_result=None,
        try_handle_single_recurring_reminder=recurring,
        handle_single_oneoff_reminder=oneoff,
        parse_with_optional_default_time="parse_with_default",
        parse_recurring="parse_recurring",
        create_recurring_template="template",
        add_reminder="add",
        build_created_reminder_actions_keyboard="keyboard",
        format_recurring_human="human",
        format_created_recurring_reminder_text="format_recurring",
        msg_recurring_parse_failed="recurring_failed",
        parse_date_time_smart="date_time",
        normalize_plain_text_reminder_with_gemini="gemini",
        normalize_gemini_reminder_command_text="gemini_text",
        normalize_reminder_text_fallback="fallback",
        format_created_reminder_text="format_oneoff",
        msg_parse_date_text_failed="parse_failed",
        safe_reply=safe_reply,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    ))

    assert [name for name, _ in calls] == ["recurring", "oneoff"]
    assert calls[1][1]["raw_single"] == "tomorrow 10:00 - milk"
    assert calls[1][1]["private_chat_type"] == "private"


def test_remind_command_uses_dispatch_helper():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    node = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remind_command"
    ][0]
    remind_source = ast.get_source_segment(source, node)

    assert "dispatch_remind_creation(" in remind_source

    forbidden_fragments = [
        "raw_lines = [ln.strip() for ln in raw_args.splitlines() if ln.strip()]",
        "created = 0",
        "failed = 0",
        "error_lines:",
        "try_handle_single_recurring_reminder(",
        "handle_single_oneoff_reminder(",
    ]

    for fragment in forbidden_fragments:
        assert fragment not in remind_source
