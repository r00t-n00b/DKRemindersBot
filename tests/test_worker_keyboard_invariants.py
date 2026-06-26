import asyncio
from types import SimpleNamespace

import pytest


class MockButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class MockMarkup:
    def __init__(self, keyboard):
        self.keyboard = keyboard


class StopWorker(BaseException):
    pass


class DummyBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


class DummyApp:
    def __init__(self):
        self.bot = DummyBot()


def _reminder(reminder_id=123, chat_id=456, text="test reminder", template_id=None):
    return SimpleNamespace(
        id=reminder_id,
        chat_id=chat_id,
        text=text,
        template_id=template_id,
    )


def _install_one_iteration_worker(main_module, monkeypatch, reminder, chat_type):
    calls = {"claim_due": 0}

    def fake_claim_due_reminders(now):
        calls["claim_due"] += 1
        if calls["claim_due"] == 1:
            return [reminder]
        raise StopWorker()

    async def fake_safe_get_chat_type(app, chat_id):
        return chat_type

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(main_module, "claim_due_reminders", fake_claim_due_reminders)
    monkeypatch.setattr(main_module, "reset_stale_processing_reminders", lambda now: 0)
    monkeypatch.setattr(main_module, "mark_reminder_delivery_failed", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_safe_get_chat_type", fake_safe_get_chat_type)
    monkeypatch.setattr(main_module, "mark_reminder_sent", lambda *args, **kwargs: None)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    return calls


def test_worker_private_delivery_uses_snooze_keyboard_not_group_keyboard(main_module, monkeypatch):
    app = DummyApp()
    reminder = _reminder(reminder_id=123, chat_id=456)

    _install_one_iteration_worker(
        main_module,
        monkeypatch,
        reminder=reminder,
        chat_type=main_module.Chat.PRIVATE,
    )

    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: ("SNOOZE", reminder_id))
    monkeypatch.setattr(main_module, "build_group_reminder_keyboard", lambda reminder_id: ("GROUP", reminder_id))

    with pytest.raises(StopWorker):
        asyncio.run(main_module.reminders_worker(app))

    assert len(app.bot.sent) == 1
    sent = app.bot.sent[0]

    assert sent["chat_id"] == 456
    assert sent["text"] == "test reminder"
    assert sent["reply_markup"] == ("SNOOZE", 123)
    assert sent["reply_markup"] != ("GROUP", 123)


def test_worker_group_delivery_uses_group_keyboard_not_snooze_keyboard(main_module, monkeypatch):
    app = DummyApp()
    reminder = _reminder(reminder_id=123, chat_id=-100777)

    _install_one_iteration_worker(
        main_module,
        monkeypatch,
        reminder=reminder,
        chat_type="group",
    )

    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: ("SNOOZE", reminder_id))
    monkeypatch.setattr(main_module, "build_group_reminder_keyboard", lambda reminder_id: ("GROUP", reminder_id))

    with pytest.raises(StopWorker):
        asyncio.run(main_module.reminders_worker(app))

    assert len(app.bot.sent) == 1
    sent = app.bot.sent[0]

    assert sent["chat_id"] == -100777
    assert sent["reply_markup"] == ("GROUP", 123)
    assert sent["reply_markup"] != ("SNOOZE", 123)


def test_worker_private_redelivery_after_snooze_still_uses_snooze_keyboard(main_module, monkeypatch):
    app = DummyApp()

    # This is intentionally just a normal due reminder again.
    # Snooze re-delivery must still be classified by target chat type,
    # not by the fact that the reminder was previously snoozed.
    reminder = _reminder(reminder_id=999, chat_id=456, text="snoozed reminder")

    _install_one_iteration_worker(
        main_module,
        monkeypatch,
        reminder=reminder,
        chat_type=main_module.Chat.PRIVATE,
    )

    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: ("SNOOZE", reminder_id))
    monkeypatch.setattr(main_module, "build_group_reminder_keyboard", lambda reminder_id: ("GROUP_SELF_REMIND", reminder_id))

    with pytest.raises(StopWorker):
        asyncio.run(main_module.reminders_worker(app))

    assert len(app.bot.sent) == 1
    sent = app.bot.sent[0]

    assert sent["reply_markup"] == ("SNOOZE", 999)
    assert sent["reply_markup"] != ("GROUP_SELF_REMIND", 999)


def test_group_reminder_keyboard_contains_self_remind_button(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    markup = main_module.build_group_reminder_keyboard(123)

    buttons = [button for row in markup.keyboard for button in row]

    assert any(button.text == "Напомнить мне лично" for button in buttons)
    assert any(button.callback_data == "selfremind:ask:123" for button in buttons)


def test_snooze_keyboard_does_not_contain_self_remind_button(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    markup = main_module.build_snooze_keyboard(123)

    buttons = [button for row in markup.keyboard for button in row]

    assert all(button.text != "Напомнить мне лично" for button in buttons)
    assert all(not button.callback_data.startswith("selfremind:ask:") for button in buttons)
