from datetime import datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace
import asyncio


def test_private_chat_does_not_ignore_alias(main_module, monkeypatch):
    """
    Защита: в private-чате alias ДОЛЖЕН работать.
    """
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))
    monkeypatch.setattr(m, "get_now", lambda: now)
    monkeypatch.setattr(m, "looks_like_recurring", lambda s: False)
    monkeypatch.setattr(m, "upsert_user_chat", lambda **kw: None)

    monkeypatch.setattr(m, "get_chat_id_by_alias", lambda a: 777)

    added = {}

    def fake_add_reminder(chat_id, text, remind_at, created_by, template_id=None):
        added["chat_id"] = chat_id
        return 1

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    msg = SimpleNamespace(
        text="/remind TeamA 02.02 - hi",
        reply_text=lambda *a, **k: None,
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=msg,
        effective_user=SimpleNamespace(
            id=123,
            username="u",
            first_name="U",
            last_name="L",
        )
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(m.remind_command(upd, ctx))

    assert added["chat_id"] == 777
