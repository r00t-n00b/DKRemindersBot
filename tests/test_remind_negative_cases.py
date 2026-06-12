import pytest
import asyncio
from types import SimpleNamespace


def _mk_private(text: str):
    msg = SimpleNamespace(
        text=text,
        replies=[],
        reply_text=lambda t, **k: msg.replies.append(t),
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123, username="u", first_name="U", last_name="L"),
    )
    ctx = SimpleNamespace(user_data={}, args=[])
    return msg, upd, ctx

@pytest.mark.parametrize("text", [
    "/remind foo",
    "/remind - hi",
    "/remind 99.99 - hi",
    "/remind 25.13 - hi",
    "/remind every - hi",
])
def test_remind_invalid_inputs(main_module, text):
    msg = SimpleNamespace(
        text=text,
        replies=[],
        reply_text=lambda t, **k: msg.replies.append(t),
    )

    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123),
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(main_module.remind_command(upd, ctx))

    assert msg.replies

def test_alias_without_date_private(main_module):
    msg, upd, ctx = _mk_private("/remind TeamA")
    asyncio.run(main_module.remind_command(upd, ctx))
    assert msg.replies


def test_username_without_date_private(main_module):
    msg, upd, ctx = _mk_private("/remind @someone")
    asyncio.run(main_module.remind_command(upd, ctx))
    assert msg.replies


def test_empty_bulk(main_module):
    msg, upd, ctx = _mk_private("/remind\n-\n-")
    asyncio.run(main_module.remind_command(upd, ctx))
    assert msg.replies


def test_bulk_only_garbage(main_module):
    msg, upd, ctx = _mk_private("/remind\n- foo\n- bar")
    asyncio.run(main_module.remind_command(upd, ctx))
    assert msg.replies