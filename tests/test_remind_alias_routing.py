# tests/test_remind_alias_routing.py
import asyncio
from datetime import datetime
from types import SimpleNamespace


class DummyMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))


class DummyChat:
    def __init__(self, chat_id: int, chat_type: str):
        self.id = chat_id
        self.type = chat_type


class DummyUser:
    def __init__(self, user_id: int, username: str = "u", first_name: str = "f", last_name: str = "l"):
        self.id = user_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name


class DummyUpdate:
    def __init__(self, chat: DummyChat, message: DummyMessage, user: DummyUser):
        self.effective_chat = chat
        self.effective_message = message
        self.effective_user = user


class DummyContext:
    def __init__(self):
        self.user_data = {}
        self.args = []


def test_remind_private_alias_oneoff_routes_and_strips_alias(main_module, fixed_now, monkeypatch):
    m = main_module

    # делаем "личку"
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    full_text = "/remind Каталония 02.02 12:00 - завтра футбол в 20:45"
    msg = DummyMessage(full_text)
    chat = DummyChat(chat_id=999, chat_type="private")
    user = DummyUser(user_id=123)
    upd = DummyUpdate(chat, msg, user)
    ctx = DummyContext()

    monkeypatch.setattr(m, "extract_after_command", lambda _: "Каталония 02.02 12:00 - завтра футбол в 20:45")

    monkeypatch.setattr(m, "get_chat_id_by_alias", lambda alias: 777 if alias == "Каталония" else None)
    monkeypatch.setattr(m, "looks_like_recurring", lambda s: False)

    called = {"seen": None}

    def fake_parse_date_time_smart(s: str, now: datetime):
        called["seen"] = s
        assert s == "02.02 12:00 - завтра футбол в 20:45"
        # now не проверяем - в этом тесте это не цель
        return fixed_now, "текст"

    monkeypatch.setattr(m, "parse_date_time_smart", fake_parse_date_time_smart)

    added = {"chat_id": None, "text": None, "created_by": None}

    def fake_add_reminder(chat_id, text, remind_at, created_by, template_id=None):
        added["chat_id"] = chat_id
        added["text"] = text
        added["created_by"] = created_by
        return 1

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)
    monkeypatch.setattr(m, "upsert_user_chat", lambda **kwargs: None)

    if hasattr(m, "logger"):
        monkeypatch.setattr(m, "logger", SimpleNamespace(info=lambda *a, **k: None))

    asyncio.run(m.remind_command(upd, ctx))

    assert called["seen"] == "02.02 12:00 - завтра футбол в 20:45"
    assert added["chat_id"] == 777
    assert added["created_by"] == 123
    assert msg.replies, "ожидали reply_text"


def test_remind_private_alias_bulk_strips_alias_for_each_line(main_module, fixed_now, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    full_text = "/remind Каталония\n- 02.02 12:00 - a\n- 03.02 - b"
    msg = DummyMessage(full_text)
    chat = DummyChat(chat_id=999, chat_type="private")
    user = DummyUser(user_id=123)
    upd = DummyUpdate(chat, msg, user)
    ctx = DummyContext()

    monkeypatch.setattr(m, "extract_after_command", lambda _: "Каталония\n- 02.02 12:00 - a\n- 03.02 - b")
    monkeypatch.setattr(m, "get_chat_id_by_alias", lambda alias: 777 if alias == "Каталония" else None)
    monkeypatch.setattr(m, "looks_like_recurring", lambda s: False)
    monkeypatch.setattr(m, "upsert_user_chat", lambda **kwargs: None)

    seen = []

    def fake_parse_date_time_smart(s: str, now: datetime):
        seen.append(s)
        assert not s.startswith("Каталония")
        return fixed_now, "x"

    monkeypatch.setattr(m, "parse_date_time_smart", fake_parse_date_time_smart)

    monkeypatch.setattr(m, "add_reminder", lambda **kwargs: 1)
    monkeypatch.setattr(m, "create_recurring_template", lambda **kwargs: 1)
    monkeypatch.setattr(
        m,
        "parse_recurring",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("parse_recurring не должен вызываться")),
    )

    if hasattr(m, "logger"):
        monkeypatch.setattr(m, "logger", SimpleNamespace(info=lambda *a, **k: None))

    asyncio.run(m.remind_command(upd, ctx))

    assert seen == ["02.02 12:00 - a", "03.02 - b"]
    assert msg.replies, "ожидали reply_text"