import asyncio
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo

def test_remind_private_alias_absolute_date_regression(main_module, monkeypatch):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    fixed_now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    # ---- окружение ----
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    # фиксируем now
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)

    # алиас -> чат
    monkeypatch.setattr(m, "get_chat_id_by_alias", lambda a: 777 if a == "Каталония" else None)

    # не recurring
    monkeypatch.setattr(m, "looks_like_recurring", lambda s: False)

    # не трогаем БД
    monkeypatch.setattr(m, "upsert_user_chat", lambda **kw: None)

    added = {}

    def fake_add_reminder(chat_id, text, remind_at, created_by, template_id=None):
        added["chat_id"] = chat_id
        added["text"] = text
        added["remind_at"] = remind_at
        return 1

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    # ---- апдейт ----
    msg = SimpleNamespace(
        text="/remind Каталония 02.02 12:00 - завтра футбол",
        reply_text=lambda *a, **k: None,
    )
    chat = SimpleNamespace(id=999, type="private")
    user = SimpleNamespace(id=123, username="u", first_name="U", last_name="L")

    upd = SimpleNamespace(
        effective_chat=chat,
        effective_message=msg,
        effective_user=user,
    )
    ctx = SimpleNamespace(user_data={})

    # ---- выполняем ----
    asyncio.run(m.remind_command(upd, ctx))

    # ---- проверки ----
    assert added["chat_id"] == 777
    assert added["text"] == "завтра футбол"
    assert added["remind_at"].day == 2
    assert added["remind_at"].month == 2
    assert added["remind_at"].hour == 12