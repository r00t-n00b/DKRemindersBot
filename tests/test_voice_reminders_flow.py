import asyncio
from types import SimpleNamespace

import pytest


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


def test_voice_reminder_keeps_self_recipient_and_verbatim_task(main_module, monkeypatch, fixed_now):
    import json
    import sqlite3

    from dkreminders_bot.integrations.gemini_transcription import gemini_transcribe_audio_with_retries
    from test_gemini_transcription import FakeClient, FakeGenaiTypes

    task = "переслать Диме сообщение, которое я отправила Наташе."
    client = FakeClient([json.dumps({
        "transcript": f"Напомню, мне в 9.30 утра {task}",
        "command": "Дима 09:30 - переслать сообщение, которое я отправил Наташе.",
    }, ensure_ascii=False)])

    async def fake_transcribe(*args, **kwargs):
        return await gemini_transcribe_audio_with_retries(
            client=client, audio_bytes=b"voice", genai_types=FakeGenaiTypes,
            logger=main_module.logger, aliases_prompt="Дима, Наташа",
        )

    monkeypatch.setattr(main_module, "transcribe_voice_message", fake_transcribe)
    monkeypatch.setattr(main_module, "get_now", lambda: fixed_now.replace(hour=0))
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "test-model")
    main_module.set_user_timezone_name(456, "Europe/Madrid")
    main_module.set_user_alias("Дима", 789, 789, "dima", 456)
    main_module.set_user_alias("Наташа", 999, 999, "natasha", 456)

    update, context, message = _mk_update(user_id=456, chat_id=456)
    asyncio.run(main_module.voice_remind_command(update, context))

    with sqlite3.connect(main_module.DB_PATH) as conn:
        assert conn.execute("SELECT chat_id, text, remind_at FROM reminders").fetchall() == [
            (456, task, fixed_now.replace(hour=9, minute=30).isoformat()),
        ]
    assert any(task in reply for reply, _ in message.replies)


@pytest.mark.parametrize("transcript, command, expected_chat", [
    ("Напомни завтра в 11 позвонить Олегу", "Олег завтра 11:00 - позвонить", None),
    ("Напомни позвонить Олегу завтра в 11", "Олег завтра 11:00 - позвонить", None),
    ("Напомни мне через час написать Олегу", "Олег через час - написать", None),
    ("Напомни отправить отчёт в офис завтра", "Офис завтра 11:00 - отправить отчёт", None),
    ("Напомни позвонить в банк завтра", "позвонить завтра 11:00 - в банк", None),
    ("Напомни Олегу завтра в 11 позвонить Наташе", "Наташа завтра 11:00 - позвонить", None),
    ("Напомни Олегу завтра в 11 позвонить Наташе", "Олег завтра 11:00 - позвонить Наташе", 789),
    ("Напомни Наташе завтра в 11 позвонить Олегу", "Наташа завтра 11:00 - позвонить Олегу", 999),
    ("Напомни офис завтра в 11 отправить отчёт", "Офис завтра 11:00 - отправить отчёт", -100),
    ("Напомни завтра в 11 позвонить Олегу", "завтра 11:00 - позвонить Олегу", 456),
    ("Напомни мне завтра позвонить Олегу", "me Олег завтра 11:00 - позвонить", None),
    (None, "Олег завтра 11:00 - позвонить", None),
])
def test_voice_requires_spoken_recipient_before_schedule(
    main_module, monkeypatch, fixed_now, transcript, command, expected_chat,
):
    import json
    import sqlite3

    from dkreminders_bot.integrations.gemini_transcription import gemini_transcribe_audio_with_retries
    from test_gemini_transcription import FakeClient, FakeGenaiTypes

    response = command if transcript is None else json.dumps({"transcript": transcript, "command": command})
    client = FakeClient([response])

    async def fake_transcribe(*args, **kwargs):
        return await gemini_transcribe_audio_with_retries(
            client=client, audio_bytes=b"voice", genai_types=FakeGenaiTypes,
            logger=main_module.logger,
        )

    monkeypatch.setattr(main_module, "transcribe_voice_message", fake_transcribe)
    monkeypatch.setattr(main_module, "get_now", lambda: fixed_now)
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "test-model")
    main_module.set_user_timezone_name(456, "Europe/Madrid")
    main_module.set_user_alias("Олег", 789, 789, "oleg", 456)
    main_module.set_user_alias("Наташа", 999, 999, "natasha", 456)
    main_module.set_user_alias("позвонить", 888, 888, None, 456)
    main_module.set_chat_alias("Офис", -100, "Офис", 456)

    update, context, message = _mk_update(user_id=456, chat_id=456)
    asyncio.run(main_module.voice_remind_command(update, context))

    with sqlite3.connect(main_module.DB_PATH) as conn:
        rows = conn.execute("SELECT chat_id, text FROM reminders").fetchall()
    if expected_chat is None:
        assert rows == []
        assert "Не удалось подтвердить, кому" in message.replies[-1][0]
    else:
        assert rows == [(expected_chat, command.split(" - ", 1)[1])]
