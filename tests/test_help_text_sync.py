import asyncio
from types import SimpleNamespace


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_help_mentions_defaulttime_and_current_system_default(main_module):
    message = FakeMessage()
    update = SimpleNamespace(effective_message=message)
    context = SimpleNamespace(args=[])

    asyncio.run(main_module.help_command(update, context))

    text = message.replies[-1][0]

    assert "/defaulttime" in text
    assert "/defaulttime 09:30" in text
    assert "/defaulttime reset" in text
    assert "10:00" in text
    assert "11:00" not in text
    assert "системное поведение" not in text


def test_help_mentions_current_core_flows(main_module):
    message = FakeMessage()
    update = SimpleNamespace(effective_message=message)
    context = SimpleNamespace(args=[])

    asyncio.run(main_module.help_command(update, context))

    text = message.replies[-1][0]

    assert "Напомнить мне лично" in text
    assert "до события" in text
    assert "удалить только ближайшее или всю серию" in text
    assert "every 90 minutes" in text
    assert "/list @username" in text
    assert "/renamealias Наташа -> Ната" in text
