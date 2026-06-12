import asyncio
from types import SimpleNamespace

from zoneinfo import ZoneInfo


def _mk_update(text: str, chat_type: str, chat_id: int = 999, chat_title: str = "Test Chat"):
    msg = SimpleNamespace(
        text=text,
        replies=[],
        reply_text=lambda t, **k: msg.replies.append(t),
    )
    chat = SimpleNamespace(id=chat_id, type=chat_type, title=chat_title)
    user = SimpleNamespace(id=123, username="u", first_name="U", last_name="L")
    upd = SimpleNamespace(
        effective_chat=chat,
        effective_message=msg,
        effective_user=user,
    )

    # telegram.ext.CommandHandler обычно кладет args в context.args
    parts = (text or "").strip().split()
    args = parts[1:] if len(parts) > 1 else []

    ctx = SimpleNamespace(user_data={}, args=args)
    return upd, ctx, msg, chat, user


def test_help_command_sends_usage(main_module, monkeypatch, fixed_now):
    m = main_module

    # фиксируем now, чтобы не было случайных зависимостей
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)

    # чтобы не завалиться на Chat.PRIVATE
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    upd, ctx, msg, chat, user = _mk_update("/help", chat_type="private", chat_id=999)

    asyncio.run(m.help_command(upd, ctx))

    assert msg.replies, "help_command должен отвечать текстом"
    reply = "\n".join(msg.replies)
    assert "/remind" in reply
    assert "/list" in reply


def test_linkchat_private_rejects(main_module, monkeypatch, fixed_now):
    m = main_module
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    upd, ctx, msg, chat, user = _mk_update("/linkchat TeamA", chat_type="private", chat_id=999)

    # если вдруг попытается трогать алиасы из лички - это ошибка
    def _should_not_be_called(*a, **k):
        raise AssertionError("set_chat_alias must not be called in private chats")

    monkeypatch.setattr(m, "set_chat_alias", _should_not_be_called)

    asyncio.run(m.linkchat_command(upd, ctx))

    assert msg.replies, "linkchat_command в личке должен ответить инструкцией"
    reply = "\n".join(msg.replies).lower()
    assert "групп" in reply or "чат" in reply
    assert "/linkchat" in reply


def test_linkchat_group_without_args_shows_usage(main_module, monkeypatch, fixed_now):
    m = main_module
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    upd, ctx, msg, chat, user = _mk_update("/linkchat", chat_type="group", chat_id=777, chat_title="My Group")

    def _should_not_be_called(*a, **k):
        raise AssertionError("set_chat_alias must not be called when alias is missing")

    monkeypatch.setattr(m, "set_chat_alias", _should_not_be_called)

    asyncio.run(m.linkchat_command(upd, ctx))

    assert msg.replies
    reply = "\n".join(msg.replies)
    assert "Формат:" in reply
    assert "/linkchat" in reply


def test_linkchat_group_sets_alias(main_module, monkeypatch, fixed_now):
    m = main_module
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    upd, ctx, msg, chat, user = _mk_update("/linkchat TeamA", chat_type="group", chat_id=777, chat_title="My Group")

    called = {}

    def fake_set_chat_alias(alias, chat_id, title):
        called["chat_id"] = chat_id
        called["alias"] = alias
        called["title"] = title

    monkeypatch.setattr(m, "set_chat_alias", fake_set_chat_alias)

    asyncio.run(m.linkchat_command(upd, ctx))

    assert called == {"chat_id": 777, "alias": "TeamA", "title": "My Group"}
    assert msg.replies
    reply = "\n".join(msg.replies)
    assert "Ok" in reply or "Ок" in reply
    assert "TeamA" in reply

def test_linkchat_alias_with_spaces(main_module, monkeypatch):
    upd, ctx, msg, *_ = _mk_update("/linkchat Team A", chat_type="group")

    monkeypatch.setattr(main_module, "set_chat_alias", lambda *a, **k: None)

    asyncio.run(main_module.linkchat_command(upd, ctx))
    assert msg.replies


def test_linkchat_alias_symbols(main_module, monkeypatch):
    upd, ctx, msg, *_ = _mk_update("/linkchat @@@", chat_type="group")

    monkeypatch.setattr(main_module, "set_chat_alias", lambda *a, **k: None)

    asyncio.run(main_module.linkchat_command(upd, ctx))
    assert msg.replies

def test_linkchat_calls_set_chat_alias_with_kwargs(main_module, monkeypatch):
    upd, ctx, msg, chat, user = _mk_update("/linkchat TeamA", chat_type="group", chat_id=777, chat_title="My Group")

    called = {}

    def fake_set_chat_alias(*, chat_id, alias, title):
        called["chat_id"] = chat_id
        called["alias"] = alias
        called["title"] = title

    monkeypatch.setattr(main_module, "set_chat_alias", fake_set_chat_alias)

    asyncio.run(main_module.linkchat_command(upd, ctx))

    assert called == {"chat_id": 777, "alias": "TeamA", "title": "My Group"}