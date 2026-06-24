import asyncio
from types import SimpleNamespace

import main
from remind_target_resolution import resolve_remind_target_and_args


class Logger:
    def __init__(self):
        self.infos = []

    def info(self, *args):
        self.infos.append(args)


async def safe_reply(message, text):
    message.replies.append(text)


def strip_first_token_from_first_line(raw_args, first_token):
    lines = raw_args.splitlines()
    first = lines[0].lstrip()
    rest = first.split(maxsplit=1)
    new_first = rest[1] if len(rest) == 2 else ""
    result = "\n".join([new_first] + lines[1:]).strip()
    return result


def make_base(**overrides):
    message = SimpleNamespace(replies=[])
    chat = SimpleNamespace(id=100, type="private")
    user = SimpleNamespace(id=42, username="u", first_name="F", last_name="L")
    logger = Logger()
    upserts = []

    kwargs = dict(
        is_private=True,
        raw_args="tomorrow 10:00 - text",
        had_newline=False,
        chat=chat,
        user=user,
        message=message,
        now=object(),
        default_time=(9, 0),
        safe_reply=safe_reply,
        logger=logger,
        strip_first_token_from_first_line=strip_first_token_from_first_line,
        first_token_looks_like_reminder_start=lambda token: token in {"tomorrow", "28.11", "at"},
        get_user_chat_id_by_username=lambda username: None,
        get_user_alias_chat_id_for_user=lambda alias, user_id: None,
        get_chat_id_by_alias_for_user=lambda alias, user_id: None,
        parse_with_optional_default_time=lambda parser, text, now, default_time: (_ for _ in ()).throw(ValueError("bad")),
        parse_date_time_smart=object(),
        upsert_user_chat=lambda **kw: upserts.append(kw),
        msg_after_me_requires_date_and_text=lambda example: f"need after me: {example}",
        msg_user_has_not_started_bot=lambda username: f"{username} has not started",
        msg_after_target_requires_date_and_text=lambda target, example: f"need after {target}: {example}",
    )
    kwargs.update(overrides)
    return kwargs, message, logger, upserts


def run_resolver(**overrides):
    kwargs, message, logger, upserts = make_base(**overrides)
    result = asyncio.run(resolve_remind_target_and_args(**kwargs))
    return result, message, logger, upserts


def test_resolver_keeps_regular_private_reminder_for_self():
    result, message, logger, upserts = run_resolver()

    assert result.aborted is False
    assert result.raw_args == "tomorrow 10:00 - text"
    assert result.had_newline is False
    assert result.target_chat_id == 100
    assert result.used_alias is None
    assert message.replies == []
    assert upserts == [
        {
            "user_id": 42,
            "chat_id": 100,
            "username": "u",
            "first_name": "F",
            "last_name": "L",
        }
    ]


def test_resolver_strips_me_and_keeps_target_self():
    result, message, logger, upserts = run_resolver(raw_args="me tomorrow 10:00 - text")

    assert result.aborted is False
    assert result.raw_args == "tomorrow 10:00 - text"
    assert result.target_chat_id == 100
    assert message.replies == []


def test_resolver_replies_when_me_has_no_body():
    result, message, logger, upserts = run_resolver(raw_args="me")

    assert result.aborted is True
    assert message.replies == ["need after me: Пример: /remind me on Tuesday - алкоголь под КС"]


def test_resolver_routes_username_target():
    result, message, logger, upserts = run_resolver(
        raw_args="@bob tomorrow 10:00 - text",
        get_user_chat_id_by_username=lambda username: 555,
    )

    assert result.aborted is False
    assert result.raw_args == "tomorrow 10:00 - text"
    assert result.target_chat_id == 555
    assert result.used_alias == "@bob"


def test_resolver_replies_when_username_unknown():
    result, message, logger, upserts = run_resolver(raw_args="@bob tomorrow")

    assert result.aborted is True
    assert message.replies == ["@bob has not started"]


def test_resolver_strips_nested_remind_prefix_before_alias_lookup():
    result, message, logger, upserts = run_resolver(raw_args="напомни tomorrow 10:00 - text")

    assert result.aborted is False
    assert result.raw_args == "tomorrow 10:00 - text"


def test_resolver_routes_user_alias_without_used_alias():
    result, message, logger, upserts = run_resolver(
        raw_args="natasha tomorrow 10:00 - text",
        get_user_alias_chat_id_for_user=lambda alias, user_id: 777,
    )

    assert result.aborted is False
    assert result.raw_args == "tomorrow 10:00 - text"
    assert result.target_chat_id == 777
    assert result.used_alias is None


def test_resolver_routes_chat_alias_with_used_alias():
    result, message, logger, upserts = run_resolver(
        raw_args="team tomorrow 10:00 - text",
        get_chat_id_by_alias_for_user=lambda alias, user_id: -100,
    )

    assert result.aborted is False
    assert result.raw_args == "tomorrow 10:00 - text"
    assert result.target_chat_id == -100
    assert result.used_alias == "team"


def test_resolver_replies_when_unknown_alias_precedes_valid_reminder_text():
    result, message, logger, upserts = run_resolver(
        raw_args="unknown tomorrow 10:00 - text",
        parse_with_optional_default_time=lambda parser, text, now, default_time: object(),
    )

    assert result.aborted is True
    assert message.replies == [
        'Алиаса "unknown" не существует. '
        "Используй команду без него, если хочешь поставить ремайндер себе, "
        'или присвой "unknown" тому, кому нужно, с помощью команд /linkuser или /linkchat. '
        "Подробнее о них можешь прочитать в /help."
    ]


def test_resolver_does_not_touch_group_target_or_upsert():
    result, message, logger, upserts = run_resolver(
        is_private=False,
        chat=SimpleNamespace(id=-100, type="group"),
        raw_args="team tomorrow 10:00 - text",
    )

    assert result.aborted is False
    assert result.target_chat_id == -100
    assert result.raw_args == "team tomorrow 10:00 - text"
    assert upserts == []


def test_remind_command_uses_target_resolution_helper():
    import ast
    from pathlib import Path

    source = Path("remind_command_router.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_remind_command"
    ]
    assert len(nodes) == 1

    remind_source = ast.get_source_segment(source, nodes[0])

    assert "resolve_remind_target_and_args(" in remind_source

    forbidden_fragments = [
        'first_token.startswith("@")',
        "get_user_alias_chat_id_for_user(",
        "get_chat_id_by_alias_for_user(first_token",
        "upsert_user_chat(",
        "REMIND normalized chat_id",
        'nested_first in {"напомни", "напомнить", "remind"}',
    ]

    for fragment in forbidden_fragments:
        assert fragment not in remind_source


def test_main_reexports_target_resolution_helper():
    assert main.resolve_remind_target_and_args is resolve_remind_target_and_args
