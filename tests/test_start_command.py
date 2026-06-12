import asyncio
from types import SimpleNamespace

def test_start_private_chat(main_module):
    m = main_module

    msg = SimpleNamespace(
        text="/start",
        replies=[],
        reply_text=lambda text, **k: msg.replies.append(text),
    )

    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123),
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(m.start_command(upd, ctx))

    assert msg.replies
    assert any("напомин" in r.lower() for r in msg.replies)


def test_start_group_chat_is_silent(main_module):
    m = main_module

    msg = SimpleNamespace(
        text="/start",
        replies=[],
        reply_text=lambda text, **k: msg.replies.append(text),
    )

    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=999, type="group"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123),
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(m.start_command(upd, ctx))

    assert msg.replies == []

def test_start_without_message(main_module):
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=None,
        effective_user=SimpleNamespace(id=123),
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(main_module.start_command(upd, ctx))


def test_start_without_user(main_module):
    msg = SimpleNamespace(reply_text=lambda *a, **k: None)

    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=msg,
        effective_user=None,
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(main_module.start_command(upd, ctx))