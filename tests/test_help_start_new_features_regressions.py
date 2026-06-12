import asyncio
from types import SimpleNamespace


class DummyMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _mk_update():
    message = DummyMessage()
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(id=123, type="private"),
        effective_user=SimpleNamespace(id=123, username="owner", first_name="Owner"),
        message=message,
    )
    context = SimpleNamespace(args=[], user_data={})
    return update, context, message


def _reply_text(message):
    assert message.replies
    return "\n".join(text for text, _kwargs in message.replies)


def test_help_documents_plain_text_as_simplest_flow(main_module):
    update, context, message = _mk_update()

    asyncio.run(main_module.help_command(update, context))

    text = _reply_text(message)

    assert "САМЫЙ ПРОСТОЙ СПОСОБ" in text
    assert "Просто напиши обычным текстом" in text
    assert "напомни завтра в 11 купить молоко" in text
    assert "через 2 часа проверить духовку" in text


def test_help_documents_voice_reminders(main_module):
    update, context, message = _mk_update()

    asyncio.run(main_module.help_command(update, context))

    text = _reply_text(message)

    assert "Голосом тоже можно" in text
    assert "отправь голосовое в личке" in text
    assert "напомни завтра в 11 купить молоко" in text


def test_help_documents_interval_recurring_reminders(main_module):
    update, context, message = _mk_update()

    asyncio.run(main_module.help_command(update, context))

    text = _reply_text(message)

    assert "Интервалы" in text
    assert "/remind every 3 days - пить лекарство" in text
    assert "/remind каждые 2 часа - размяться" in text
    assert "/remind every 10 minutes - выпить воды" in text
    assert "/remind каждые 2 недели 09:00 - отчет" in text


def test_help_documents_alias_management_commands(main_module):
    update, context, message = _mk_update()

    asyncio.run(main_module.help_command(update, context))

    text = _reply_text(message)

    assert "/linkchat football" in text
    assert "/linkuser misha @username" in text
    assert "/aliases" in text
    assert "/unalias Наташа" in text
    assert "/renamealias Наташа -> Ната" in text
    assert "/list @username" in text


def test_start_documents_plain_text_voice_aliases_and_help(main_module):
    update, context, message = _mk_update()

    asyncio.run(main_module.start_command(update, context))

    text = _reply_text(message)

    assert "Привет. Я бот для напоминаний." in text
    assert "Что я умею:" in text
    assert "принимать голосовые в личке" in text
    assert "напомни завтра в 11 купить молоко" in text
    assert "напомни Наташе завтра в 12 позвонить" in text
    assert "/remind завтра 11:00 - купить молоко" in text
    assert "/remind every day 10:00 - пить воду" in text
    assert "/linkuser Наташа @username" in text
    assert "/aliases - показать все алиасы" in text
    assert "Все форматы и подробности: /help" in text
