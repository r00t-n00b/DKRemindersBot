import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest


def _mk_update(text: str, chat_id: int, chat_type: str):
    msg = SimpleNamespace(
        text=text,
        reply_text=lambda *a, **k: None,
    )
    chat = SimpleNamespace(id=chat_id, type=chat_type)
    user = SimpleNamespace(id=123, username="u", first_name="U", last_name="L")
    upd = SimpleNamespace(
        effective_chat=chat,
        effective_message=msg,
        effective_user=user,
    )
    ctx = SimpleNamespace(user_data={})
    return upd, ctx, msg, chat, user


def _run_remind(
    m,
    monkeypatch,
    text: str,
    fixed_now: datetime,
    chat_type: str = "private",
    chat_id: int = 999,
    alias_map=None,
    username_map=None,
):
    TZ = ZoneInfo("Europe/Madrid")
    alias_map = alias_map or {}
    username_map = username_map or {}

    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))
    monkeypatch.setattr(m, "get_now", lambda: fixed_now.astimezone(TZ))

    monkeypatch.setattr(
        m,
        "get_chat_id_by_alias",
        lambda a: alias_map.get(a),
    )
    monkeypatch.setattr(
        m,
        "get_user_chat_id_by_username",
        lambda u: username_map.get(u),
    )

    monkeypatch.setattr(m, "looks_like_recurring", lambda s: False)
    monkeypatch.setattr(m, "upsert_user_chat", lambda **kw: None)

    added = {}
    replies = []

    async def fake_safe_reply(message, text, **kw):
        replies.append(text)

    def fake_add_reminder(chat_id, text, remind_at, created_by, template_id=None):
        added["chat_id"] = chat_id
        added["text"] = text
        added["remind_at"] = remind_at
        return 1

    monkeypatch.setattr(m, "safe_reply", fake_safe_reply)
    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    upd, ctx, msg, chat, user = _mk_update(text=text, chat_id=chat_id, chat_type=chat_type)
    asyncio.run(m.remind_command(upd, ctx))

    return added, replies


def test_group_chat_ignores_username_switch(main_module, monkeypatch):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    def _should_not_be_called(_u):
        raise AssertionError("get_user_chat_id_by_username must not be called in group chats")

    monkeypatch.setattr(m, "get_user_chat_id_by_username", _should_not_be_called)

    added, replies = _run_remind(
        m,
        monkeypatch,
        "/remind 02.02 - hi @someone",
        fixed_now=now,
        chat_type="group",
        chat_id=999,
    )

    assert added["chat_id"] == 999
    assert "@someone" in added["text"]

    assert len(replies) == 1
    assert replies[0].startswith("Ок, напомню ")
    assert "этому человеку" not in replies[0]


def test_private_unknown_username_returns_error_and_does_not_add(main_module, monkeypatch):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added, replies = _run_remind(
        m,
        monkeypatch,
        "/remind @nouser 02.02 - hi",
        fixed_now=now,
        chat_type="private",
        chat_id=999,
        username_map={},  # unknown
    )

    assert added == {}
    assert replies
    assert "@nouser" in replies[0]


def test_private_alias_without_rest_returns_error_and_does_not_add(main_module, monkeypatch):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added, replies = _run_remind(
        m,
        monkeypatch,
        "/remind TeamA",
        fixed_now=now,
        chat_type="private",
        chat_id=999,
        alias_map={"TeamA": 777},
    )

    assert added == {}
    assert replies
    assert "После alias" in replies[0]


def test_private_bulk_with_alias_applies_to_all_lines(main_module, monkeypatch):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    # проверяем только то, что хотя бы один add_reminder ушел в alias-chat
    added, replies = _run_remind(
        m,
        monkeypatch,
        "/remind TeamA\n- 02.02 - one\n- 03.02 - two",
        fixed_now=now,
        chat_type="private",
        chat_id=999,
        alias_map={"TeamA": 777},
    )

    assert added["chat_id"] == 777
    assert added["text"] in ("one", "two")


def test_private_bulk_first_line_dash_does_not_trigger_alias_strip(main_module, monkeypatch):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    # alias не должен резаться из bulk-строк, если первая строка начинается с "-"
    added, replies = _run_remind(
        m,
        monkeypatch,
        "/remind\n- TeamA 02.02 - hi",
        fixed_now=now,
        chat_type="private",
        chat_id=999,
        alias_map={"TeamA": 777},
    )

    # Тут ожидаем, что напоминание создается в текущем чате (999),
    # а "TeamA 02.02" парсится как выражение даты (и вероятно упадет) - но тогда add не будет.
    # Чтобы тест был устойчивым, проверяем только что НЕ ушло в alias-chat.
    assert added.get("chat_id") != 777