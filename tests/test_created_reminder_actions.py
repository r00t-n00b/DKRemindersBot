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


def test_build_created_reschedule_keyboard_has_back_without_hide(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    keyboard = m.build_created_reschedule_keyboard(123)

    flattened = [button for row in keyboard.inline_keyboard for button in row]

    assert any(b.callback_data == "created_snooze:123:20m" for b in flattened)
    assert any(b.callback_data == "created_snooze:123:1h" for b in flattened)
    assert any(b.callback_data == "created_snooze:123:3h" for b in flattened)
    assert any(b.callback_data == "created_snooze:123:tomorrow" for b in flattened)
    assert any(b.callback_data == "created_snooze_custom:123" for b in flattened)
    assert all(not b.callback_data.startswith("snooze:123:") for b in flattened)
    assert keyboard.inline_keyboard[-1][0].text == "⬅️ Назад"
    assert keyboard.inline_keyboard[-1][0].callback_data == "created_back:123"

    flattened = [button for row in keyboard.inline_keyboard for button in row]
    assert all(button.callback_data != "created_hide:123" for button in flattened)
    assert all(button.text != "Скрыть" for button in flattened)


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

    monkeypatch.setattr(m, "get_reminder", lambda rid: SimpleNamespace(template_id=None))

    def fake_build_created_reminder_actions_keyboard(rid, is_recurring=False):
        seen.append((rid, is_recurring))
        return created_actions_keyboard

    monkeypatch.setattr(m, "build_created_reminder_actions_keyboard", fake_build_created_reminder_actions_keyboard)

    query = FakeQuery("created_back:789")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(m.created_back_callback(update, SimpleNamespace()))

    assert seen == [(789, False)]
    assert query.answers
    assert query.edited_reply_markup is created_actions_keyboard


def test_created_back_callback_restores_recurring_created_actions_keyboard(main_module, monkeypatch):
    m = main_module
    created_actions_keyboard = object()
    seen = []

    monkeypatch.setattr(m, "get_reminder", lambda rid: SimpleNamespace(template_id=999))

    def fake_build_created_reminder_actions_keyboard(rid, is_recurring=False):
        seen.append((rid, is_recurring))
        return created_actions_keyboard

    monkeypatch.setattr(m, "build_created_reminder_actions_keyboard", fake_build_created_reminder_actions_keyboard)

    query = FakeQuery("created_back:789")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(m.created_back_callback(update, SimpleNamespace()))

    assert seen == [(789, True)]
    assert query.answers
    assert query.edited_reply_markup is created_actions_keyboard




class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeChat:
    PRIVATE = "private"

    def __init__(self, chat_id=12345):
        self.id = chat_id
        self.type = "private"


def test_recurring_reminder_success_has_created_actions_keyboard(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    monkeypatch.setattr(m, "Chat", FakeChat)

    message = FakeMessage("/remind every day - recurring task")
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=FakeChat(12345),
        effective_user=SimpleNamespace(id=1000, username="tester", first_name="Tester"),
    )
    context = SimpleNamespace(args=["every", "day", "-", "recurring", "task"], user_data={})

    asyncio.run(m.remind_command(update, context))

    assert message.replies
    reply, kwargs = message.replies[0]
    assert "Ок, создал повторяющееся напоминание." in reply

    keyboard = kwargs.get("reply_markup")
    assert keyboard is not None
    assert keyboard.inline_keyboard[0][0].text == "❌ Удалить ближайшее/серию"
    assert keyboard.inline_keyboard[0][0].callback_data.startswith("created_del:")
    assert keyboard.inline_keyboard[0][1].text == "⏰ Перенести ближайшее"
    assert keyboard.inline_keyboard[0][1].callback_data.startswith("created_resched:")


def test_build_created_reminder_actions_keyboard_for_recurring_says_nearest(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    keyboard = m.build_created_reminder_actions_keyboard(123, is_recurring=True)

    assert keyboard.inline_keyboard[0][0].text == "❌ Удалить ближайшее/серию"
    assert keyboard.inline_keyboard[0][0].callback_data == "created_del:123"
    assert keyboard.inline_keyboard[0][1].text == "⏰ Перенести ближайшее"
    assert keyboard.inline_keyboard[0][1].callback_data == "created_resched:123"


def test_created_delete_callback_for_recurring_shows_one_or_series_choice(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    deleted = []

    monkeypatch.setattr(m, "get_reminder_row", lambda rid: {"id": rid, "chat_id": 777, "template_id": 999})
    monkeypatch.setattr(
        m,
        "delete_single_reminder_with_snapshot",
        lambda rid, chat_id: deleted.append((rid, chat_id)),
    )

    query = FakeQuery("created_del:456")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})

    asyncio.run(m.created_delete_callback(update, context))

    assert deleted == []
    assert query.answers
    assert query.edited_reply_markup is not None

    keyboard = query.edited_reply_markup
    assert keyboard.inline_keyboard[0][0].text == "🗑 Удалить ближайшее"
    assert keyboard.inline_keyboard[0][0].callback_data == "del_one:456"
    assert keyboard.inline_keyboard[1][0].text == "🧨 Удалить всю серию"
    assert keyboard.inline_keyboard[1][0].callback_data == "del_series:999"
    assert keyboard.inline_keyboard[2][0].text == "⬅️ Отмена"
    assert keyboard.inline_keyboard[2][0].callback_data == "del_cancel:456"


def test_created_reschedule_keyboard_uses_created_custom_callback(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    keyboard = m.build_created_reschedule_keyboard(123)

    flattened = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.callback_data == "created_snooze_custom:123" for button in flattened)
    assert all(button.callback_data != "snooze:123:custom" for button in flattened)


def test_created_snooze_cancel_returns_created_reschedule_keyboard(main_module, monkeypatch):
    m = main_module
    created_keyboard = object()
    seen = []

    def fake_build_created_reschedule_keyboard(rid):
        seen.append(rid)
        return created_keyboard

    monkeypatch.setattr(m, "build_created_reschedule_keyboard", fake_build_created_reschedule_keyboard)
    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: (_ for _ in ()).throw(AssertionError("must not ack on cancel")))

    query = FakeQuery("created_snooze_cancel:789")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(m.created_snooze_cancel_callback(update, SimpleNamespace()))

    assert seen == [789]
    assert query.answers
    assert query.answers[0][0] == "Вернул варианты"
    assert query.edited_reply_markup is created_keyboard


def test_created_reschedule_keyboard_does_not_use_normal_snooze_callbacks(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    keyboard = m.build_created_reschedule_keyboard(123)
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "created_snooze:123:20m" in callbacks
    assert "created_snooze:123:1h" in callbacks
    assert "created_snooze:123:3h" in callbacks
    assert "created_snooze:123:tomorrow" in callbacks
    assert "created_snooze:123:nextmon" in callbacks
    assert "created_snooze_custom:123" in callbacks
    assert not any(cb.startswith("snooze:123:") for cb in callbacks)


def test_created_snooze_updates_existing_reminder_instead_of_creating_copy(main_module, fixed_now, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)

    rid = m.add_reminder(
        chat_id=12345,
        text="created task",
        remind_at=fixed_now.replace(hour=18, minute=0),
        created_by=1000,
    )

    def fail_add_reminder(*args, **kwargs):
        raise AssertionError("created_snooze must update existing reminder, not create a copy")

    monkeypatch.setattr(m, "add_reminder", fail_add_reminder)

    query = FakeQuery(f"created_snooze:{rid}:1h")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})

    asyncio.run(m.created_snooze_callback(update, context))

    reminder = m.get_reminder(rid)
    assert reminder is not None

    expected = fixed_now + m.timedelta(hours=1)
    assert reminder.remind_at == expected

    when_str = expected.strftime("%d.%m %H:%M")
    assert query.edited_text == f"Перенёс напоминание на {when_str}: created task"
    assert query.answers == [(f"Перенесено на {when_str}", {})]


def test_created_snooze_custom_calendar_uses_created_prefix(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    keyboard = m.build_custom_date_keyboard(123, callback_prefix="created_snooze")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert any(cb.startswith("created_snooze_pickdate:123:") for cb in callbacks)
    assert any(cb.startswith("created_snooze_cal:123:") for cb in callbacks)
    assert "created_snooze_cancel:123" in callbacks
    assert not any(cb.startswith("snooze_pickdate:123:") for cb in callbacks)


def test_undo_single_restores_created_actions_keyboard(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    snapshot = {
        "kind": "single",
        "reminder": {
            "id": 456,
            "chat_id": 777,
            "text": "test task",
            "remind_at": "2026-06-22T18:00:00+02:00",
            "created_by": 1000,
        },
        "template": None,
    }

    monkeypatch.setattr(m, "restore_deleted_snapshot", lambda snap: 999)
    monkeypatch.setattr(m, "format_deleted_human", lambda *args, **kwargs: "22.06 18:00 - test task")

    query = FakeQuery("undo:tok123")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"undo_tokens": {"tok123": snapshot}})

    asyncio.run(m.undo_callback(update, context))

    assert query.edited_text == "Вернул: 22.06 18:00 - test task"

    keyboard = query.edited_text_kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "created_del:999"
    assert keyboard.inline_keyboard[0][1].callback_data == "created_resched:999"

def test_recurring_delete_choice_cancel_from_created_restores_created_actions(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    query = FakeQuery("del_cancel:456")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"delete_choice_source": "created"})

    asyncio.run(m.delete_choose_callback(update, context))

    assert context.user_data.get("delete_choice_source") is None
    assert query.edited_reply_markup is not None
    assert query.edited_reply_markup.inline_keyboard[0][0].text == "❌ Удалить ближайшее/серию"
    assert query.edited_reply_markup.inline_keyboard[0][0].callback_data == "created_del:456"
    assert query.edited_reply_markup.inline_keyboard[0][1].text == "⏰ Перенести ближайшее"
    assert query.edited_reply_markup.inline_keyboard[0][1].callback_data == "created_resched:456"


def test_recurring_delete_choice_cancel_from_list_closes_choice_message(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    query = FakeQuery("del_cancel:456")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"delete_choice_source": "list"})

    asyncio.run(m.delete_choose_callback(update, context))

    assert context.user_data.get("delete_choice_source") is None
    assert query.edited_text == "Ок, ничего не удалил."
    assert query.edited_text_kwargs["reply_markup"] is None



def test_undo_recurring_one_instance_uses_specific_restore_text(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    snapshot = {
        "kind": "single",
        "reminder": {
            "id": 456,
            "chat_id": 777,
            "text": "recurring task",
            "remind_at": "2026-06-22T18:00:00+02:00",
        },
        "template": {
            "id": 999,
            "text": "recurring task",
            "pattern_type": "daily",
            "payload": {},
        },
    }

    monkeypatch.setattr(m, "restore_deleted_snapshot", lambda snap: 456)
    monkeypatch.setattr(m, "format_deleted_human", lambda *args, **kwargs: "22.06 18:00 - recurring task")
    monkeypatch.setattr(m, "build_created_reminder_actions_keyboard", lambda rid, is_recurring=False: "actions-keyboard")

    query = FakeQuery("undo:tok123")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"undo_tokens": {"tok123": snapshot}})

    asyncio.run(m.undo_callback(update, context))

    assert "tok123" not in context.user_data["undo_tokens"]
    assert query.edited_text == "Вернул ближайшее повторяющееся напоминание: 22.06 18:00 - recurring task"
    assert query.edited_text_kwargs["reply_markup"] == "actions-keyboard"
