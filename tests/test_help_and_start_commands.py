import asyncio
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo


def _mk_update(text, chat_type="private", chat_id=1):
    msg = SimpleNamespace(
        text=text,
        replies=[],
        reply_text=lambda s, **k: msg.replies.append(s),
    )
    chat = SimpleNamespace(id=chat_id, type=chat_type)
    user = SimpleNamespace(id=123, username="u", first_name="U", last_name="L")
    upd = SimpleNamespace(
        effective_chat=chat,
        effective_message=msg,
        effective_user=user,
    )
    ctx = SimpleNamespace(user_data={}, args=text.split()[1:])
    return upd, ctx, msg


def test_help_private_chat(main_module):
    m = main_module
    upd, ctx, msg = _mk_update("/help", chat_type="private")

    asyncio.run(m.help_command(upd, ctx))

    assert msg.replies
    assert any("remind" in r.lower() for r in msg.replies)


def test_help_group_chat(main_module):
    m = main_module
    upd, ctx, msg = _mk_update("/help", chat_type="group")

    asyncio.run(m.help_command(upd, ctx))

    assert msg.replies

def test_help_in_group(main_module):
    msg = SimpleNamespace(
        text="/help",
        replies=[],
        reply_text=lambda t, **k: msg.replies.append(t),
    )

    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=999, type="group"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=1),
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(main_module.help_command(upd, ctx))


def test_help_without_message(main_module):
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=None,
        effective_user=SimpleNamespace(id=1),
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(main_module.help_command(upd, ctx))