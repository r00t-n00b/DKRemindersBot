import asyncio
from datetime import datetime
from types import SimpleNamespace

from tests.conftest import TZ


def _make_group_update(text: str):
    msg = SimpleNamespace(
        text=text,
        reply_text=None,  # safe_reply мы замокаем
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=777, type="group"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123, username="u", first_name="U", last_name="L"),
    )
    ctx = SimpleNamespace(user_data={})
    return upd, ctx


def test_group_remind_forbids_username_switch(main_module, monkeypatch):
    m = main_module

    now = datetime(2026, 2, 1, 0, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)

    replies = []

    async def fake_safe_reply(message, text, **kwargs):
        replies.append(text)

    monkeypatch.setattr(m, "safe_reply", fake_safe_reply)

    created = {"count": 0}

    def fake_add_reminder(*args, **kwargs):
        created["count"] += 1
        return 1

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    upd, ctx = _make_group_update("/remind @R00t_n00b 02.02 - test")

    asyncio.run(m.remind_command(upd, ctx))

    assert created["count"] == 0
    assert replies
    assert "В групповом чате нельзя" in replies[-1]


def test_group_remind_forbids_alias_switch(main_module, monkeypatch):
    m = main_module

    now = datetime(2026, 2, 1, 0, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)

    replies = []

    async def fake_safe_reply(message, text, **kwargs):
        replies.append(text)

    monkeypatch.setattr(m, "safe_reply", fake_safe_reply)

    created = {"count": 0}

    def fake_add_reminder(*args, **kwargs):
        created["count"] += 1
        return 1

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    # Делаем так, чтобы "Гарсия" считался alias (то есть get_chat_id_by_alias возвращает chat_id)
    monkeypatch.setattr(
        m,
        "get_chat_id_by_alias",
        lambda token: 999 if token == "Гарсия" else None,
    )

    upd, ctx = _make_group_update("/remind Гарсия 02.02 - test")

    asyncio.run(m.remind_command(upd, ctx))

    assert created["count"] == 0
    assert replies
    assert "В групповом чате нельзя" in replies[-1]