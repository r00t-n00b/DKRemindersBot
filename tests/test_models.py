from datetime import datetime

import main
from dkreminders_bot.domain.models import Reminder


def test_reminder_model_fields_and_defaults():
    reminder = Reminder(
        id=1,
        chat_id=2,
        text="test",
        remind_at=datetime(2026, 6, 23, 10, 0),
        created_by=3,
    )

    assert reminder.id == 1
    assert reminder.chat_id == 2
    assert reminder.text == "test"
    assert reminder.created_by == 3
    assert reminder.template_id is None
    assert reminder.sent_at is None


def test_main_reexports_reminder_model_for_existing_callers():
    assert main.Reminder is Reminder


def test_reminder_model_is_no_longer_defined_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "class Reminder:" not in source
    assert "from dataclasses import dataclass" not in source
    assert "from dkreminders_bot.domain.models import Reminder" in source
