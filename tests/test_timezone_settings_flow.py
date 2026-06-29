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


def test_timezone_labels_are_user_facing_not_iana_names():
    assert timezone_features.timezone_label("Europe/Madrid") == "CET"
    assert timezone_features.timezone_label("Europe/Moscow") == "Россия / Москва"


def test_other_timezone_callback_keeps_user_in_choose_flow():
    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        set_user_timezone_name=lambda user_id, tz: None,
        count_active_reminders_for_user=lambda user_id: 0,
        move_active_reminders_timezone_for_user=lambda **kwargs: {"reminders": 0, "templates": 0},
    )

    query = FakeQuery("tz:other")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(timezone_features.handle_timezone_callback(update, context, deps))

    assert query.message.edits
    text, kwargs = query.message.edits[0]
    assert "выбери часовой пояс" in text.lower()
    assert "IANA" not in text
    assert "debug" not in text
    assert kwargs.get("reply_markup") is not None


def test_geo_callback_edits_existing_message_and_shows_inline_fallback():
    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        set_user_timezone_name=lambda user_id, tz: None,
        count_active_reminders_for_user=lambda user_id: 0,
        move_active_reminders_timezone_for_user=lambda **kwargs: {"reminders": 0, "templates": 0},
    )

    query = FakeQuery("tz:geo")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(timezone_features.handle_timezone_callback(update, context, deps))

    assert len(query.message.replies) == 1
    assert "Кнопка для отправки геопозиции" in query.message.replies[0][0]
    assert query.message.replies[0][1].get("reply_markup") is not None
    assert len(query.message.edits) == 1
    text, kwargs = query.message.edits[0]
    assert "геопози" in text.lower()
    assert "выбери часовой пояс" in text.lower()
    assert kwargs.get("reply_markup") is not None


def test_timezone_preset_same_timezone_does_not_ask_migration():
    saved = []

    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        set_user_timezone_name=lambda user_id, tz: saved.append((user_id, tz)),
        count_active_reminders_for_user=lambda user_id: 5,
        move_active_reminders_timezone_for_user=lambda **kwargs: {"reminders": 0, "templates": 0},
    )

    query = FakeQuery("tz:preset:cet")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(timezone_features.handle_timezone_callback(update, context, deps))

    assert saved == []
    assert "pending_timezone_migration" not in context.user_data
    assert query.message.edits
    text, kwargs = query.message.edits[0]
    assert "уже выбран" in text
    assert "Перенести их" not in text


def test_geo_fallback_keyboard_does_not_loop_to_geo_again():
    keyboard = timezone_features.build_timezone_other_keyboard()
    callback_data = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "tz:geo" not in callback_data
    assert "tz:preset:cet" in callback_data
    assert "tz:preset:moscow" in callback_data
    assert "tz:back" in callback_data


def test_geo_callback_edits_to_desktop_explanation_without_retry_geo_button():
    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        set_user_timezone_name=lambda user_id, tz: None,
        count_active_reminders_for_user=lambda user_id: 0,
        move_active_reminders_timezone_for_user=lambda **kwargs: {"reminders": 0, "templates": 0},
    )

    query = FakeQuery("tz:geo")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(timezone_features.handle_timezone_callback(update, context, deps))

    assert len(query.message.replies) == 1
    assert "Кнопка для отправки геопозиции" in query.message.replies[0][0]
    assert query.message.replies[0][1].get("reply_markup") is not None
    assert len(query.message.edits) == 1
    text, kwargs = query.message.edits[0]
    assert "геопози" in text.lower()
    keyboard = kwargs["reply_markup"]
    callback_data = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "tz:geo" not in callback_data


def test_same_timezone_confirmation_has_no_picker_keyboard():
    saved = []

    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        set_user_timezone_name=lambda user_id, tz: saved.append((user_id, tz)),
        count_active_reminders_for_user=lambda user_id: 5,
        move_active_reminders_timezone_for_user=lambda **kwargs: {"reminders": 0, "templates": 0},
    )

    query = FakeQuery("tz:preset:cet")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(user_data={})

    asyncio.run(timezone_features.handle_timezone_callback(update, context, deps))

    assert saved == []
    assert "pending_timezone_migration" not in context.user_data
    assert query.message.edits
    text, kwargs = query.message.edits[0]
    assert "уже выбран" in text
    assert "reply_markup" not in kwargs


def test_location_same_timezone_does_not_ask_migration(monkeypatch):
    saved = []

    monkeypatch.setattr(
        timezone_features,
        "detect_timezone_from_location",
        lambda latitude, longitude: "Europe/Madrid",
    )

    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        set_user_timezone_name=lambda user_id, tz: saved.append((user_id, tz)),
        count_active_reminders_for_user=lambda user_id: 5,
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

    assert saved == []
    assert "pending_timezone_migration" not in context.user_data
    assert message.replies
    assert "уже выбран" in message.replies[0][0]

