import asyncio
from types import SimpleNamespace


class FakeInlineKeyboardButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class FakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.edited_text = None
        self.edited_text_kwargs = None
        self.edited_reply_markup = "not-called"

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edited_text = text
        self.edited_text_kwargs = kwargs

    async def edit_message_reply_markup(self, **kwargs):
        self.edited_reply_markup = kwargs.get("reply_markup")


def _patch_keyboard_classes(m, monkeypatch):
    monkeypatch.setattr(m, "InlineKeyboardButton", FakeInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", FakeInlineKeyboardMarkup)


def test_build_created_reminder_actions_keyboard(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    keyboard = m.build_created_reminder_actions_keyboard(123)

    assert keyboard.inline_keyboard[0][0].text == "❌ Удалить"
    assert keyboard.inline_keyboard[0][0].callback_data == "created_del:123"
    assert keyboard.inline_keyboard[0][1].text == "⏰ Перенести"
    assert keyboard.inline_keyboard[0][1].callback_data == "created_resched:123"


def test_build_created_reschedule_keyboard_has_back_and_hide(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    keyboard = m.build_created_reschedule_keyboard(123)

    flattened = [button for row in keyboard.inline_keyboard for button in row]

    assert any(b.callback_data == "snooze:123:20m" for b in flattened)
    assert any(b.callback_data == "snooze:123:1h" for b in flattened)
    assert any(b.callback_data == "snooze:123:3h" for b in flattened)
    assert any(b.callback_data == "snooze:123:tomorrow" for b in flattened)
    assert any(b.callback_data == "snooze:123:custom" for b in flattened)
    assert keyboard.inline_keyboard[-1][0].text == "⬅️ Назад"
    assert keyboard.inline_keyboard[-1][0].callback_data == "created_back:123"
    assert keyboard.inline_keyboard[-1][1].text == "Скрыть"
    assert keyboard.inline_keyboard[-1][1].callback_data == "created_hide:123"


def test_created_delete_callback_soft_deletes_and_shows_undo(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    snapshot = {
        "reminder": {
            "id": 456,
            "chat_id": 777,
            "text": "test task",
            "remind_at": "2026-06-22T18:00:00+02:00",
        },
        "template": None,
    }
    seen = {}

    monkeypatch.setattr(m, "get_reminder_row", lambda rid: {"id": rid, "chat_id": 777})
    def fake_delete_single_reminder_with_snapshot(rid, chat_id):
        seen["deleted"] = (rid, chat_id)
        return snapshot

    monkeypatch.setattr(
        m,
        "delete_single_reminder_with_snapshot",
        fake_delete_single_reminder_with_snapshot,
    )
    monkeypatch.setattr(m, "make_undo_token", lambda: "tok123")
    monkeypatch.setattr(m, "format_deleted_human", lambda *args, **kwargs: "22.06 18:00 - test task")

    query = FakeQuery("created_del:456")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})

    asyncio.run(m.created_delete_callback(update, context))

    assert seen["deleted"] == (456, 777)
    assert context.user_data["undo_tokens"]["tok123"] == snapshot
    assert query.answers[0][0] == "Удалено"
    assert query.edited_text == "Удалил: 22.06 18:00 - test task"

    keyboard = query.edited_text_kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "↩️ Вернуть ремайндер"
    assert keyboard.inline_keyboard[0][0].callback_data == "undo:tok123"


def test_created_reschedule_callback_replaces_keyboard_with_created_reschedule_keyboard(main_module, monkeypatch):
    m = main_module
    created_reschedule_keyboard = object()
    seen = []

    def fake_build_created_reschedule_keyboard(rid):
        seen.append(rid)
        return created_reschedule_keyboard

    monkeypatch.setattr(m, "build_created_reschedule_keyboard", fake_build_created_reschedule_keyboard)

    query = FakeQuery("created_resched:789")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(m.created_reschedule_callback(update, SimpleNamespace()))

    assert seen == [789]
    assert query.answers
    assert query.edited_reply_markup is created_reschedule_keyboard


def test_created_back_callback_restores_created_actions_keyboard(main_module, monkeypatch):
    m = main_module
    created_actions_keyboard = object()
    seen = []

    def fake_build_created_reminder_actions_keyboard(rid):
        seen.append(rid)
        return created_actions_keyboard

    monkeypatch.setattr(m, "build_created_reminder_actions_keyboard", fake_build_created_reminder_actions_keyboard)

    query = FakeQuery("created_back:789")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(m.created_back_callback(update, SimpleNamespace()))

    assert seen == [789]
    assert query.answers
    assert query.edited_reply_markup is created_actions_keyboard


def test_created_hide_callback_removes_keyboard(main_module):
    query = FakeQuery("created_hide:789")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(main_module.created_hide_callback(update, SimpleNamespace()))

    assert query.answers
    assert query.edited_reply_markup is None
