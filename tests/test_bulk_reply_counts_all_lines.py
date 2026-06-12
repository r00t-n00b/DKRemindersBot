import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")


class DummyMessage:
    def __init__(self, text: str):
        self.text = text


class DummyChat:
    def __init__(self, chat_id: int, chat_type: str):
        self.id = chat_id
        self.type = chat_type


class DummyUser:
    def __init__(self, user_id: int):
        self.id = user_id
        self.username = "u"
        self.first_name = "f"
        self.last_name = "l"


class DummyUpdate:
    def __init__(self, chat, message, user):
        self.effective_chat = chat
        self.effective_message = message
        self.effective_user = user


class DummyContext:
    pass


def test_bulk_reply_says_created_3_when_three_valid_lines(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    now = datetime(2026, 2, 27, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)

    # чтобы не уехать в recurring
    monkeypatch.setattr(m, "looks_like_recurring", lambda s: False)

    # заголовок "Тест" в личке не должен маршрутизировать куда-то
    monkeypatch.setattr(m, "get_chat_id_by_alias", lambda token: None)
    monkeypatch.setattr(m, "get_user_chat_id_by_username", lambda token: None)
    monkeypatch.setattr(m, "upsert_user_chat", lambda **kwargs: None)

    # делаем так, чтобы каждая строка bulk создавалась успешно
    def fake_create_single_reminder_from_line(line, now, target_chat_id, user):
        return None

    monkeypatch.setattr(m, "_create_single_reminder_from_line", fake_create_single_reminder_from_line)

    replies = []

    async def fake_safe_reply(message, text, **kwargs):
        replies.append(text)

    monkeypatch.setattr(m, "safe_reply", fake_safe_reply)

    full_text = (
        "/remind Тест\n"
        "On March 1 - test1\n"
        "On March 2 - test2\n"
        "On March 3 - test3\n"
    )

    msg = DummyMessage(full_text)
    chat = DummyChat(chat_id=999, chat_type="private")
    user = DummyUser(user_id=123)
    upd = DummyUpdate(chat, msg, user)
    ctx = DummyContext()

    asyncio.run(m.remind_command(upd, ctx))

    assert replies, "bot did not reply"
    # Проверяем главное: создано 3
    assert "Создано напоминаний: 3" in replies[-1]
    # И как минимум не сказано, что были ошибки
    assert "Не удалось" not in replies[-1]