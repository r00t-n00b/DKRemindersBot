import asyncio
from types import SimpleNamespace

import timezone_features


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.edits = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.message = FakeMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.message.edits.append((text, kwargs))


def test_timezone_preset_callback_saves_cet_and_asks_migration_when_active_reminders_exist():
    saved = []
    asked_counts = []

    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Moscow",
        set_user_timezone_name=lambda user_id, tz: saved.append((user_id, tz)),
        count_active_reminders_for_user=lambda user_id: 3,
        move_active_reminders_timezone_for_user=lambda **kwargs: {"reminders": 0, "templates": 0},
    )

    query = FakeQuery("tz:preset:cet")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(timezone_features.handle_timezone_callback(update, context, deps))

    assert saved == [(42, "Europe/Madrid")]
    assert context.user_data["pending_timezone_migration"] == {
        "old_tz": "Europe/Moscow",
        "new_tz": "Europe/Madrid",
    }
    assert query.message.replies
    assert "Перенести их в новый часовой пояс?" in query.message.replies[0][0]


def test_timezone_migration_callback_calls_storage_migration():
    calls = []

    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        set_user_timezone_name=lambda user_id, tz: None,
        count_active_reminders_for_user=lambda user_id: 0,
        move_active_reminders_timezone_for_user=lambda **kwargs: calls.append(kwargs) or {
            "reminders": 5,
            "templates": 2,
        },
    )

    query = FakeQuery("tz:migrate:oneoff")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        user_data={
            "pending_timezone_migration": {
                "old_tz": "Europe/Moscow",
                "new_tz": "Europe/Madrid",
            }
        }
    )

    asyncio.run(timezone_features.handle_timezone_callback(update, context, deps))

    assert calls == [{
        "user_id": 42,
        "old_tz": "Europe/Moscow",
        "new_tz": "Europe/Madrid",
        "mode": "oneoff",
    }]
    assert "Перенёс напоминания" in query.message.edits[0][0]


def test_timezone_location_handler_saves_detected_timezone(monkeypatch):
    saved = []

    monkeypatch.setattr(
        timezone_features,
        "detect_timezone_from_location",
        lambda latitude, longitude: "Asia/Tbilisi",
    )

    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        set_user_timezone_name=lambda user_id, tz: saved.append((user_id, tz)),
        count_active_reminders_for_user=lambda user_id: 0,
        move_active_reminders_timezone_for_user=lambda **kwargs: {"reminders": 0, "templates": 0},
    )

    message = FakeMessage()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=42),
        message=message,
    )
    update.effective_message.location = SimpleNamespace(latitude=41.38, longitude=2.17)
    context = SimpleNamespace(user_data={})

    asyncio.run(timezone_features.handle_timezone_location_message(update, context, deps))

    assert saved == [(42, "Asia/Tbilisi")]
    assert "Ок, поставил часовой пояс" in message.replies[0][0]
