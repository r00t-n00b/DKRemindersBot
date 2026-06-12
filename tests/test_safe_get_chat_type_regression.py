import asyncio
from types import SimpleNamespace

import pytest

from test_worker_keyboard_invariants import DummyApp, StopWorker, _install_one_iteration_worker, _reminder


def test_worker_does_not_show_self_remind_button_when_chat_type_is_unknown_for_private_id(main_module, monkeypatch):
    app = DummyApp()
    reminder = _reminder(reminder_id=123, chat_id=456)

    _install_one_iteration_worker(
        main_module,
        monkeypatch,
        reminder=reminder,
        chat_type=None,
    )

    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: ("SNOOZE", reminder_id))
    monkeypatch.setattr(main_module, "build_group_reminder_keyboard", lambda reminder_id: ("GROUP_SELF_REMIND", reminder_id))

    with pytest.raises(StopWorker):
        asyncio.run(main_module.reminders_worker(app))

    assert len(app.bot.sent) == 1
    sent = app.bot.sent[0]

    assert sent["reply_markup"] == ("SNOOZE", 123)
