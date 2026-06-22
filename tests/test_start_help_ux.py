import asyncio
from types import SimpleNamespace


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_start_is_short_onboarding(main_module):
    message = FakeMessage()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type=main_module.Chat.PRIVATE, id=100),
        effective_user=SimpleNamespace(
            id=1000,
            username="user",
            first_name="User",
            last_name=None,
        ),
        effective_message=message,
    )
    context = SimpleNamespace(args=[])

    asyncio.run(main_module.start(update, context))

    text = message.replies[-1][0]

    assert "Привет. Я бот для напоминаний." in text
    assert "/help - короткая справка" in text
    assert "/list - активные напоминания" in text
    assert "/defaulttime - время по умолчанию" in text
    assert "10:00" in text
    assert len(text) < 700


def test_help_is_structured_but_not_full_documentation(main_module):
    message = FakeMessage()
    update = SimpleNamespace(effective_message=message)
    context = SimpleNamespace(args=[])

    asyncio.run(main_module.help_command(update, context))

    text = message.replies[-1][0]

    assert "🟢 САМЫЙ ПРОСТОЙ СПОСОБ" in text
    assert "✍️ ЯВНЫЙ ФОРМАТ" in text
    assert "⏱ ВРЕМЯ ПО УМОЛЧАНИЮ" in text
    assert "🔁 ПОВТОРЯЮЩИЕСЯ" in text
    assert "📋 СПИСОК" in text
    assert "🔗 АЛИАСЫ" in text
    assert "👤 НАПОМНИТЬ МНЕ ЛИЧНО" in text
    assert "======================" not in text
    assert len(text) < 2600
