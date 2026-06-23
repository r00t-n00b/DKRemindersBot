import asyncio

import main
from remind_group_routing import reject_group_remind_target_prefix_if_needed


class Message:
    def __init__(self):
        self.replies = []


async def fake_safe_reply(message, text):
    message.replies.append(text)


def run_guard(raw_args, *, is_private=False, alias_chat_id=None, alias_raises=False):
    message = Message()

    def get_chat_id_by_alias_for_user(alias, user_id):
        if alias_raises:
            raise RuntimeError("db down")
        return alias_chat_id

    async def run():
        return await reject_group_remind_target_prefix_if_needed(
            is_private=is_private,
            raw_args=raw_args,
            user_id=42,
            message=message,
            safe_reply=fake_safe_reply,
            get_chat_id_by_alias_for_user=get_chat_id_by_alias_for_user,
            msg_group_username_prefix_forbidden="username forbidden",
            msg_group_alias_prefix_forbidden="alias forbidden",
        )

    rejected, normalized_raw_args = asyncio.run(run())
    return rejected, normalized_raw_args, message.replies


def test_group_prefix_guard_rejects_username_prefix_in_group():
    rejected, raw_args, replies = run_guard("@user tomorrow 10:00 - hi")

    assert rejected is True
    assert raw_args == "@user tomorrow 10:00 - hi"
    assert replies == ["username forbidden"]


def test_group_prefix_guard_rejects_alias_prefix_in_group():
    rejected, raw_args, replies = run_guard(
        "home tomorrow 10:00 - hi",
        alias_chat_id=123,
    )

    assert rejected is True
    assert raw_args == "home tomorrow 10:00 - hi"
    assert replies == ["alias forbidden"]


def test_group_prefix_guard_allows_plain_single_line_without_alias():
    rejected, raw_args, replies = run_guard("tomorrow 10:00 - hi")

    assert rejected is False
    assert raw_args == "tomorrow 10:00 - hi"
    assert replies == []


def test_group_prefix_guard_allows_bulk_without_alias_lookup_rejection():
    rejected, raw_args, replies = run_guard(
        "home\n- tomorrow 10:00 - hi",
        alias_chat_id=123,
    )

    assert rejected is False
    assert raw_args == "home\n- tomorrow 10:00 - hi"
    assert replies == []


def test_group_prefix_guard_noops_in_private_chat():
    rejected, raw_args, replies = run_guard(
        "@user tomorrow 10:00 - hi",
        is_private=True,
        alias_chat_id=123,
    )

    assert rejected is False
    assert raw_args == "@user tomorrow 10:00 - hi"
    assert replies == []


def test_group_prefix_guard_treats_alias_lookup_errors_as_no_alias():
    rejected, raw_args, replies = run_guard(
        "home tomorrow 10:00 - hi",
        alias_raises=True,
    )

    assert rejected is False
    assert raw_args == "home tomorrow 10:00 - hi"
    assert replies == []


def test_main_reexports_group_prefix_guard_for_handler():
    assert main.reject_group_remind_target_prefix_if_needed is reject_group_remind_target_prefix_if_needed


def test_group_prefix_guard_body_is_no_longer_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "from remind_group_routing import reject_group_remind_target_prefix_if_needed" in source
    assert "reject_group_remind_target_prefix_if_needed(" in source
    assert "# В group-чате запрещаем" not in source
