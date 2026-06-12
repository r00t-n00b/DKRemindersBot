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


def test_bulk_monthname_lines_are_not_dropped_and_parser_not_called_twice(main_module, monkeypatch):
    """
    Регрессия по реальному багу:
    /remind <title>
    On March 1 - a
    On March 2 - b
    ...

    1) Первая строка "On March 1 - ..." не должна считаться заголовком и выкидываться.
    2) Детект заголовка не должен вызывать parse_date_time_smart, иначе в bulk будет "двойной парсинг"
       (видно через monkeypatch и ломает тесты, а в проде может давать лишние сайд-эффекты).
    """
    m = main_module

    # Подменяем Chat.PRIVATE, чтобы код нормально определял приватный чат
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    now = datetime(2026, 2, 27, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)

    # Обязательно: recurring здесь не нужен
    monkeypatch.setattr(m, "looks_like_recurring", lambda s: False)

    # alias/username routing не нужен, просто выключаем
    monkeypatch.setattr(m, "get_chat_id_by_alias", lambda token: None)
    monkeypatch.setattr(m, "get_user_chat_id_by_username", lambda token: None)

    # Чтобы не трогать базу
    monkeypatch.setattr(m, "upsert_user_chat", lambda **kwargs: None)

    # Ловим вызовы парсера: должны быть РОВНО по одному на каждую строку напоминания
    seen = []

    def fake_parse_date_time_smart(s: str, now_dt: datetime):
        seen.append(s)
        return now_dt, "x"

    monkeypatch.setattr(m, "parse_date_time_smart", fake_parse_date_time_smart)

    created = {"count": 0}

    def fake_add_reminder(**kwargs):
        created["count"] += 1
        return created["count"]

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    # safe_reply не важен, но чтобы не было побочных эффектов
    async def fake_safe_reply(message, text, **kwargs):
        return None

    monkeypatch.setattr(m, "safe_reply", fake_safe_reply)

    # Запускаем bulk: первая строка "Тест" - это заголовок, а 3 строки "On March ..." - напоминания
    full_text = (
        "/remind Тест\n"
        "On March 1 - a\n"
        "On March 2 - b\n"
        "On March 3 - c\n"
    )

    msg = DummyMessage(full_text)
    chat = DummyChat(chat_id=999, chat_type="private")
    user = DummyUser(user_id=123)
    upd = DummyUpdate(chat, msg, user)
    ctx = DummyContext()

    asyncio.run(m.remind_command(upd, ctx))

    assert created["count"] == 3
    assert seen == ["On March 1 - a", "On March 2 - b", "On March 3 - c"]