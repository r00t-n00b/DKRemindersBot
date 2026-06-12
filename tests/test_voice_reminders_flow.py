import asyncio
from types import SimpleNamespace


class DummyMessage:
    def __init__(self, text=None, voice=None):
        self.text = text
        self.voice = voice
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class DummyVoice:
    def __init__(self, file_id="voice-file-id"):
        self.file_id = file_id


def _mk_update(chat_type="private", user_id=123, chat_id=456):
    message = DummyMessage(voice=DummyVoice())
    chat = SimpleNamespace(id=chat_id, type=chat_type)
    user = SimpleNamespace(id=user_id, username="u", first_name="U", last_name="L")
    update = SimpleNamespace(
        effective_chat=chat,
        effective_message=message,
        effective_user=user,
        message=message,
    )
    context = SimpleNamespace(args=[], user_data={})
    return update, context, message


def test_voice_reminder_ignores_group_chat(main_module, monkeypatch):
    called = False

    async def fake_transcribe(*args, **kwargs):
        nonlocal called
        called = True
        return "завтра 18:00 - test"

    monkeypatch.setattr(main_module, "transcribe_voice_message", fake_transcribe)

    update, context, message = _mk_update(chat_type="group")

    asyncio.run(main_module.voice_remind_command(update, context))

    assert called is False
    assert message.replies == []


def test_voice_reminder_transcription_error_replies_with_overloaded_message(main_module, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        raise RuntimeError("gemini overloaded")

    monkeypatch.setattr(main_module, "transcribe_voice_message", fake_transcribe)

    update, context, message = _mk_update()

    asyncio.run(main_module.voice_remind_command(update, context))

    assert len(message.replies) == 1
    reply, _ = message.replies[0]

    assert "Не смог распознать голосовое" in reply
    assert "Попробуй еще раз чуть позже" in reply
    assert "напиши текстом" in reply


def test_voice_reminder_empty_transcription_replies_not_heard(main_module, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        return ""

    monkeypatch.setattr(main_module, "transcribe_voice_message", fake_transcribe)

    update, context, message = _mk_update()

    asyncio.run(main_module.voice_remind_command(update, context))

    assert len(message.replies) == 1
    reply, _ = message.replies[0]

    assert reply == "Не услышал текст в голосовом."


def test_voice_reminder_normalized_text_is_proxied_to_remind_command(main_module, monkeypatch):
    seen = {}

    async def fake_transcribe(*args, **kwargs):
        return "завтра 18:00 - купить молоко"

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "transcribe_voice_message", fake_transcribe)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update()

    asyncio.run(main_module.voice_remind_command(update, context))

    assert seen["text"] == "/remind завтра 18:00 - купить молоко"

    assert len(message.replies) == 1
    reply, _ = message.replies[0]

    assert "Я понял:" in reply
    assert "завтра 18:00 - купить молоко" in reply
    assert "Ок, напомню" in reply


def test_voice_reminder_applies_gemini_interval_normalization_before_proxy(main_module, monkeypatch):
    seen = {}

    async def fake_transcribe(*args, **kwargs):
        return "каждые полтора часа - попить воды"

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "transcribe_voice_message", fake_transcribe)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update()

    asyncio.run(main_module.voice_remind_command(update, context))

    assert seen["text"] == "/remind every 90 minutes - попить воды"

    assert len(message.replies) == 1
    reply, _ = message.replies[0]

    assert "Я понял:" in reply
    assert "every 90 minutes - попить воды" in reply
    assert "Ок, напомню" in reply


def test_voice_reminder_local_fallback_normalizes_spoken_text_before_proxy(main_module, monkeypatch):
    seen = {}

    async def fake_transcribe(*args, **kwargs):
        return "напомни завтра в 18:00 купить молоко"

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "transcribe_voice_message", fake_transcribe)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update()

    asyncio.run(main_module.voice_remind_command(update, context))

    assert seen["text"] == "/remind завтра 18:00 - купить молоко"

    assert len(message.replies) == 1
    reply, _ = message.replies[0]

    assert "Я понял:" in reply
    assert "завтра 18:00 - купить молоко" in reply
    assert "Ок, напомню" in reply
