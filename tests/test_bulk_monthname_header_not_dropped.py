import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo


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


def test_bulk_monthname_first_line_not_dropped(main_module, monkeypatch):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2026, 2, 27, 10, 0, tzinfo=TZ)

    monkeypatch.setattr(m, "get_now", lambda: now)
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    # Важно: именно такой формат, как у тебя в реальном кейсе.
    full_text = (
        "/remind Тест\n"
        "On March 1 - test1\n"
        "On March 2 - test2\n"
        "On March 3 - test3\n"
    )

    chat = DummyChat(chat_id=999, chat_type="private")
    msg = DummyMessage(full_text)
    user = DummyUser(user_id=123)
    upd = DummyUpdate(chat, msg, user)
    ctx = DummyContext()

    # Если у тебя в remind_command had_newline=True, raw_args собирается из message.text,
    # но на всякий случай стабим extract_after_command, если вдруг пойдет в else-ветку.
    monkeypatch.setattr(
        m,
        "extract_after_command",
        lambda _: "Тест\nOn March 1 - test1\nOn March 2 - test2\nOn March 3 - test3",
    )

    # В этом тесте нам важна логика bulk-нарезки.
    # Парсинг дат и создание в БД не важны, поэтому _create_single_reminder_from_line стабим.
    seen_lines = []

    def fake_create_single_reminder_from_line(*, line, now, target_chat_id, user):
        seen_lines.append(line)

    monkeypatch.setattr(m, "_create_single_reminder_from_line", fake_create_single_reminder_from_line)

    # recurring здесь не нужен
    monkeypatch.setattr(m, "looks_like_recurring", lambda s: False)

    # остальное безопасно заглушаем
    monkeypatch.setattr(m, "upsert_user_chat", lambda **kwargs: None)

    async def fake_safe_reply(message, text, **kwargs):
        return None

    monkeypatch.setattr(m, "safe_reply", fake_safe_reply)

    if hasattr(m, "logger"):
        monkeypatch.setattr(m, "logger", SimpleNamespace(info=lambda *a, **k: None))

    asyncio.run(m.remind_command(upd, ctx))

    # Ключевой контракт: заголовок "Тест" игнорится, а все 3 строки напоминаний доходят.
    assert seen_lines == [
        "On March 1 - test1",
        "On March 2 - test2",
        "On March 3 - test3",
    ]