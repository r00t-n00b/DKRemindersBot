import asyncio
from types import SimpleNamespace


def test_undo_callback_no_snapshot_answers_alert(main_module):
    answered = {"called": False, "kwargs": None}

    async def fake_answer(*a, **k):
        answered["called"] = True
        answered["kwargs"] = k

    async def fake_reply_text(*a, **k):
        return None

    cbq = SimpleNamespace(
        data="undo:nope",
        answer=fake_answer,
        message=SimpleNamespace(reply_text=fake_reply_text),
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={"undo_tokens": {}})

    asyncio.run(main_module.undo_callback(upd, ctx))

    assert answered["called"] is True
    assert answered["kwargs"] is not None
    assert answered["kwargs"].get("show_alert") is True


def test_undo_callback_restores_single_reply(main_module, monkeypatch):
    async def fake_answer(*a, **k):
        return None

    edited = {}

    async def fake_edit_message_text(text, **kwargs):
        edited["text"] = text
        edited["kwargs"] = kwargs

    snapshot = {
        "kind": "single",
        "reminder": {
            "chat_id": 1,
            "text": "task",
            "remind_at": "2025-01-01T10:00:00+01:00",
        },
        "template": None,
    }

    monkeypatch.setattr(main_module, "restore_deleted_snapshot", lambda snap: 77)

    keyboard = SimpleNamespace(
        inline_keyboard=[
            [
                SimpleNamespace(callback_data="created_del:77"),
                SimpleNamespace(callback_data="created_resched:77"),
            ]
        ]
    )
    keyboard_calls = []

    def fake_created_actions_keyboard_for_reminder(reminder_id):
        keyboard_calls.append(reminder_id)
        return keyboard

    monkeypatch.setattr(
        main_module,
        "build_created_reminder_actions_keyboard_for_reminder",
        fake_created_actions_keyboard_for_reminder,
    )

    cbq = SimpleNamespace(
        data="undo:t1",
        answer=fake_answer,
        edit_message_text=fake_edit_message_text,
        message=SimpleNamespace(),
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={"undo_tokens": {"t1": snapshot}})

    asyncio.run(main_module.undo_callback(upd, ctx))

    assert edited["text"].startswith("Вернул: ")
    keyboard = edited["kwargs"]["reply_markup"]
    assert keyboard is not None
    assert keyboard_calls == [77]
    assert keyboard.inline_keyboard[0][0].callback_data == "created_del:77"
    assert keyboard.inline_keyboard[0][1].callback_data == "created_resched:77"
    assert ctx.user_data["undo_tokens"] == {}

def test_undo_callback_restores_series_reply(main_module, monkeypatch):
    async def fake_answer(*a, **k):
        return None

    edited = {}

    async def fake_edit_message_text(text, **kwargs):
        edited["text"] = text
        edited["kwargs"] = kwargs

    snapshot = {
        "kind": "series",
        "chat_id": 1,
        "template": {"text": "series", "pattern_type": "daily", "payload": None},
        "reminders": [
            {"text": "a", "remind_at": "2025-01-01T10:00:00+01:00"},
            {"text": "b", "remind_at": "2025-01-02T10:00:00+01:00"},
        ],
    }

    monkeypatch.setattr(main_module, "restore_deleted_snapshot", lambda snap: [1, 2])

    keyboard = SimpleNamespace(
        inline_keyboard=[
            [
                SimpleNamespace(callback_data="created_del:1"),
                SimpleNamespace(callback_data="created_resched:1"),
            ]
        ]
    )
    keyboard_calls = []

    def fake_created_actions_keyboard_for_reminder(reminder_id):
        keyboard_calls.append(reminder_id)
        return keyboard

    monkeypatch.setattr(
        main_module,
        "build_created_reminder_actions_keyboard_for_reminder",
        fake_created_actions_keyboard_for_reminder,
    )

    cbq = SimpleNamespace(
        data="undo:t2",
        answer=fake_answer,
        edit_message_text=fake_edit_message_text,
        message=SimpleNamespace(),
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={"undo_tokens": {"t2": snapshot}})

    asyncio.run(main_module.undo_callback(upd, ctx))

    assert edited["text"] == "Вернул серию: series  🔁 daily (инстансов: 2)"
    assert edited["kwargs"]["reply_markup"] is keyboard
    assert keyboard_calls == [1]
    assert ctx.user_data["undo_tokens"] == {}
