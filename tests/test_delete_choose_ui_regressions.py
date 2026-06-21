import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


class MockButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class MockMarkup:
    def __init__(self, keyboard):
        self.keyboard = keyboard


class DummyMessage:
    def __init__(self, chat_id=456):
        self.chat = SimpleNamespace(id=chat_id)
        self.message_id = 999
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class DummyQuery:
    def __init__(self, data, chat_id=456):
        self.data = data
        self.message = DummyMessage(chat_id=chat_id)
        self.answers = []
        self.edits = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))



class DummyBot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)


class DummyUpdate:
    def __init__(self, query):
        self.callback_query = query


def _ctx(list_ids, list_chat_id=456):
    return SimpleNamespace(
        user_data={
            "list_ids": list_ids,
            "list_chat_id": list_chat_id,
        },
        bot=DummyBot(),
    )


def _snapshot_one(reminder_id=101, text="old reminder"):
    return {
        "kind": "one",
        "reminder": {
            "id": reminder_id,
            "chat_id": 456,
            "text": text,
            "remind_at": datetime(2026, 6, 12, 10, 30, tzinfo=TZ).isoformat(),
            "created_by": 123,
            "template_id": 77,
        },
        "template": {
            "id": 77,
            "pattern_type": "interval",
            "payload": {"value": 2, "unit": "hours"},
        },
    }


def _snapshot_series(template_id=77):
    return {
        "kind": "series",
        "template": {
            "id": template_id,
            "pattern_type": "interval",
            "payload": {"value": 2, "unit": "hours"},
        },
        "reminders": [
            {
                "id": 101,
                "chat_id": 456,
                "text": "first in series",
                "remind_at": datetime(2026, 6, 12, 10, 30, tzinfo=TZ).isoformat(),
                "created_by": 123,
                "template_id": template_id,
            },
            {
                "id": 102,
                "chat_id": 456,
                "text": "second in series",
                "remind_at": datetime(2026, 6, 12, 12, 30, tzinfo=TZ).isoformat(),
                "created_by": 123,
                "template_id": template_id,
            },
        ],
    }


def test_delete_choose_del_one_empty_list_replaces_message_with_undo(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)
    monkeypatch.setattr(main_module, "make_undo_token", lambda: "undo-token-1")
    monkeypatch.setattr(
        main_module,
        "delete_recurring_one_instance_and_reschedule",
        lambda rid, chat_id: _snapshot_one(reminder_id=rid),
    )

    query = DummyQuery("del_one:101")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_choose_callback(update, context))

    assert query.answers[0] == (None, False)
    assert context.user_data["list_ids"] == []

    assert "undo-token-1" in context.user_data["undo_tokens"]
    assert context.user_data["undo_tokens"]["undo-token-1"]["kind"] == "one"

    assert query.message.replies == []
    assert len(query.edits) == 1

    edited_text, kwargs = query.edits[0]
    assert edited_text.startswith("Удалил ближайший из серии: ")
    assert "old reminder" in edited_text
    assert "Напоминаний больше нет" not in edited_text

    undo_markup = kwargs["reply_markup"]
    buttons = [button for row in undo_markup.keyboard for button in row]
    assert any(button.callback_data == "undo:undo-token-1" for button in buttons)
    assert any("Вернуть" in button.text or "Отменить" in button.text for button in buttons)




def test_delete_choose_del_one_from_list_updates_original_list_and_edits_choice_to_undo(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)
    monkeypatch.setattr(main_module, "make_undo_token", lambda: "undo-token-2")
    monkeypatch.setattr(
        main_module,
        "delete_recurring_one_instance_and_reschedule",
        lambda rid, chat_id: _snapshot_one(reminder_id=rid),
    )

    remaining_id = main_module.add_reminder(
        chat_id=456,
        text="remaining reminder",
        remind_at=datetime(2026, 6, 13, 11, 0, tzinfo=TZ),
        created_by=123,
    )

    query = DummyQuery("del_one:101")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101, remaining_id], list_chat_id=456)
    context.user_data["delete_choice_source"] = "list"
    context.user_data["list_message_ref"] = {"chat_id": 456, "message_id": 999}

    asyncio.run(main_module.delete_choose_callback(update, context))

    assert context.user_data["list_ids"] == [remaining_id]
    assert len(context.bot.edits) == 1
    assert context.bot.edits[0]["chat_id"] == 456
    assert context.bot.edits[0]["message_id"] == 999
    assert "remaining reminder" in context.bot.edits[0]["text"]
    assert "old reminder" not in context.bot.edits[0]["text"]

    assert query.message.replies == []
    assert len(query.edits) == 1
    edited_text, kwargs = query.edits[0]
    assert edited_text.startswith("Удалил ближайший из серии: ")
    assert "old reminder" in edited_text

    buttons = [button for row in kwargs["reply_markup"].keyboard for button in row]
    assert any(button.callback_data == "undo:undo-token-2" for button in buttons)
    assert "delete_choice_source" not in context.user_data


def test_delete_choose_del_series_from_list_updates_original_list_and_edits_choice_to_undo(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)
    monkeypatch.setattr(main_module, "make_undo_token", lambda: "undo-token-series")
    monkeypatch.setattr(
        main_module,
        "delete_recurring_series_with_snapshot",
        lambda tpl_id, chat_id: _snapshot_series(template_id=tpl_id),
    )

    query = DummyQuery("del_series:77")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101, 102], list_chat_id=456)
    context.user_data["delete_choice_source"] = "list"
    context.user_data["list_message_ref"] = {"chat_id": 456, "message_id": 999}

    asyncio.run(main_module.delete_choose_callback(update, context))

    assert context.user_data["list_ids"] == []
    assert len(context.bot.edits) == 1
    assert context.bot.edits[0]["text"] == "Напоминаний больше нет."

    assert query.message.replies == []
    assert len(query.edits) == 1
    edited_text, kwargs = query.edits[0]
    assert edited_text.startswith("Удалил всю серию: ")
    assert "first in series" in edited_text

    buttons = [button for row in kwargs["reply_markup"].keyboard for button in row]
    assert any(button.callback_data == "undo:undo-token-series" for button in buttons)
    assert "delete_choice_source" not in context.user_data

def test_delete_choose_invalid_ids_do_nothing(main_module, monkeypatch):
    one_called = False
    series_called = False

    def fake_delete_one(*args, **kwargs):
        nonlocal one_called
        one_called = True

    def fake_delete_series(*args, **kwargs):
        nonlocal series_called
        series_called = True

    monkeypatch.setattr(main_module, "delete_recurring_one_instance_and_reschedule", fake_delete_one)
    monkeypatch.setattr(main_module, "delete_recurring_series_with_snapshot", fake_delete_series)

    for data in ["del_one:not-int", "del_series:not-int"]:
        query = DummyQuery(data)
        update = DummyUpdate(query)
        context = _ctx(list_ids=[101], list_chat_id=456)

        asyncio.run(main_module.delete_choose_callback(update, context))

        assert query.answers == [(None, False)]
        assert query.edits == []
        assert query.message.replies == []

    assert one_called is False
    assert series_called is False


def test_delete_choose_missing_snapshot_shows_alert(main_module, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "delete_recurring_one_instance_and_reschedule",
        lambda rid, chat_id: None,
    )

    query = DummyQuery("del_one:101")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_choose_callback(update, context))

    assert query.answers == [
        (None, False),
        (main_module.MSG_DELETE_FAILED_SHORT, True),
    ]
    assert query.edits == []
    assert query.message.replies == []



def test_delete_choose_del_index_for_recurring_reminder_shows_delete_mode_choice(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    remind_at = datetime(2026, 6, 12, 10, 30, tzinfo=TZ).isoformat()

    monkeypatch.setattr(
        main_module,
        "get_reminder_row",
        lambda rid: {
            "id": rid,
            "chat_id": 456,
            "text": "drink water",
            "remind_at": remind_at,
            "template_id": 77,
        },
    )
    monkeypatch.setattr(
        main_module,
        "get_recurring_template_row",
        lambda tpl_id: {
            "id": tpl_id,
            "pattern_type": "interval",
            "payload": {"value": 2, "unit": "hours"},
        },
    )

    query = DummyQuery("del:1")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_callback(update, context))

    # /list остается списком, а вопрос удаления recurring приходит отдельным сообщением.
    assert query.edits == []
    assert len(query.message.replies) == 1

    reply_text, kwargs = query.message.replies[0]
    assert reply_text.startswith("Это повторяющееся напоминание. Как удалить?")
    assert "drink water" in reply_text
    assert "🔁 every 2 hours" in reply_text

    assert context.user_data["delete_choice_source"] == "list"
    assert context.user_data["list_message_ref"] == {"chat_id": 456, "message_id": 999}

    buttons = [button for row in kwargs["reply_markup"].keyboard for button in row]
    assert any(button.callback_data == "del_one:101" for button in buttons)
    assert any(button.callback_data == "del_series:77" for button in buttons)

def test_delete_choose_del_index_for_missing_reminder_shows_already_deleted(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "get_reminder_row", lambda rid: None)

    query = DummyQuery("del:1")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_callback(update, context))

    assert query.answers == [(None, False), ("Уже удалено", True)]
    assert query.edits == []
    assert query.message.replies == []




def test_delete_choose_del_index_for_regular_reminder_empty_list_deletes_and_creates_undo(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)
    monkeypatch.setattr(main_module, "make_undo_token", lambda: "undo-token-regular")

    remind_at = datetime(2026, 6, 12, 10, 30, tzinfo=TZ).isoformat()

    monkeypatch.setattr(
        main_module,
        "get_reminder_row",
        lambda rid: {
            "id": rid,
            "chat_id": 456,
            "text": "regular reminder",
            "remind_at": remind_at,
            "template_id": None,
        },
    )
    monkeypatch.setattr(
        main_module,
        "delete_single_reminder_with_snapshot",
        lambda rid, chat_id: {
            "kind": "single",
            "reminder": {
                "id": rid,
                "chat_id": chat_id,
                "text": "regular reminder",
                "remind_at": remind_at,
                "created_by": 123,
                "template_id": None,
            },
            "template": None,
        },
    )

    query = DummyQuery("del:1")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_callback(update, context))

    # /list обновляется на месте.
    assert context.user_data["list_ids"] == []
    assert len(query.edits) == 1
    assert query.edits[0][0] == "Напоминаний больше нет."

    # Undo-уведомление приходит отдельным сообщением.
    assert len(query.message.replies) == 1
    reply_text, kwargs = query.message.replies[0]
    assert reply_text.startswith("Удалил: ")
    assert "regular reminder" in reply_text

    assert "undo-token-regular" in context.user_data["undo_tokens"]
    assert context.user_data["undo_tokens"]["undo-token-regular"]["kind"] == "single"

    buttons = [button for row in kwargs["reply_markup"].keyboard for button in row]
    assert any(button.callback_data == "undo:undo-token-regular" for button in buttons)


def test_delete_choose_del_index_for_regular_reminder_rebuilds_remaining_list(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)
    monkeypatch.setattr(main_module, "make_undo_token", lambda: "undo-token-regular-2")

    deleted_at = datetime(2026, 6, 12, 10, 30, tzinfo=TZ).isoformat()

    monkeypatch.setattr(
        main_module,
        "get_reminder_row",
        lambda rid: {
            "id": rid,
            "chat_id": 456,
            "text": "deleted reminder",
            "remind_at": deleted_at,
            "template_id": None,
        },
    )
    monkeypatch.setattr(
        main_module,
        "delete_single_reminder_with_snapshot",
        lambda rid, chat_id: {
            "kind": "single",
            "reminder": {
                "id": rid,
                "chat_id": chat_id,
                "text": "deleted reminder",
                "remind_at": deleted_at,
                "created_by": 123,
                "template_id": None,
            },
            "template": None,
        },
    )

    remaining_id = main_module.add_reminder(
        chat_id=456,
        text="remaining reminder",
        remind_at=datetime(2026, 6, 13, 11, 0, tzinfo=TZ),
        created_by=123,
    )

    query = DummyQuery("del:1")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101, remaining_id], list_chat_id=456)

    asyncio.run(main_module.delete_callback(update, context))

    # /list остается списком и обновляется на месте.
    assert context.user_data["list_ids"] == [remaining_id]
    assert len(query.edits) == 1

    edited_text, _kwargs = query.edits[0]
    assert "Активные напоминания:" in edited_text
    assert "remaining reminder" in edited_text
    assert "deleted reminder" not in edited_text
    assert "Удалил:" not in edited_text

    # Undo-уведомление приходит отдельным сообщением.
    assert len(query.message.replies) == 1
    reply_text, kwargs = query.message.replies[0]
    assert reply_text.startswith("Удалил: ")
    assert "deleted reminder" in reply_text

    assert "undo-token-regular-2" in context.user_data["undo_tokens"]
    assert context.user_data["undo_tokens"]["undo-token-regular-2"]["kind"] == "single"

    buttons = [button for row in kwargs["reply_markup"].keyboard for button in row]
    assert any(button.callback_data == "undo:undo-token-regular-2" for button in buttons)

def test_delete_choose_del_index_out_of_range_shows_not_found_alert(main_module, monkeypatch):
    called = False

    def fake_get_reminder_row(rid):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(main_module, "get_reminder_row", fake_get_reminder_row)

    query = DummyQuery("del:999")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_callback(update, context))

    assert called is False
    assert query.answers == [
        (None, False),
        ("Не нашел такое напоминание", True),
    ]
    assert query.edits == []
    assert query.message.replies == []


def test_delete_choose_del_index_invalid_number_does_nothing(main_module, monkeypatch):
    called = False

    def fake_get_reminder_row(rid):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(main_module, "get_reminder_row", fake_get_reminder_row)

    query = DummyQuery("del:not-int")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_callback(update, context))

    assert called is False
    assert query.answers == [(None, False)]
    assert query.edits == []
    assert query.message.replies == []


def test_delete_callback_single_reminder_from_list_updates_list_and_sends_undo_message(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)
    monkeypatch.setattr(main_module, "make_undo_token", lambda: "undo-token-single")
    monkeypatch.setattr(
        main_module,
        "get_reminder_row",
        lambda rid: {"id": rid, "chat_id": 456, "text": "plain reminder", "template_id": None},
    )
    monkeypatch.setattr(
        main_module,
        "delete_single_reminder_with_snapshot",
        lambda rid, chat_id: {
            "kind": "single",
            "reminder": {
                "id": rid,
                "chat_id": chat_id,
                "text": "plain reminder",
                "remind_at": datetime(2026, 6, 12, 10, 30, tzinfo=TZ).isoformat(),
                "created_by": 123,
                "template_id": None,
            },
            "template": None,
        },
    )

    query = DummyQuery("del:1")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_callback(update, context))

    assert context.user_data["list_ids"] == []
    assert len(query.edits) == 1
    assert query.edits[0][0] == "Напоминаний больше нет."

    assert len(query.message.replies) == 1
    reply_text, kwargs = query.message.replies[0]
    assert reply_text.startswith("Удалил: ")
    assert "plain reminder" in reply_text

    buttons = [button for row in kwargs["reply_markup"].keyboard for button in row]
    assert any(button.callback_data == "undo:undo-token-single" for button in buttons)


def test_delete_callback_recurring_from_list_keeps_list_and_sends_delete_choice(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    remind_at = datetime(2026, 6, 12, 10, 30, tzinfo=TZ).isoformat()

    monkeypatch.setattr(
        main_module,
        "get_reminder_row",
        lambda rid: {
            "id": rid,
            "chat_id": 456,
            "text": "recurring reminder",
            "remind_at": remind_at,
            "template_id": 77,
        },
    )
    monkeypatch.setattr(
        main_module,
        "get_recurring_template_row",
        lambda tpl_id: {
            "id": tpl_id,
            "pattern_type": "daily",
            "payload": {},
        },
    )

    query = DummyQuery("del:1")
    update = DummyUpdate(query)
    context = _ctx(list_ids=[101], list_chat_id=456)

    asyncio.run(main_module.delete_callback(update, context))

    assert query.edits == []
    assert len(query.message.replies) == 1

    reply_text, kwargs = query.message.replies[0]
    assert reply_text.startswith("Это повторяющееся напоминание. Как удалить?")
    assert "recurring reminder" in reply_text
    assert "🔁 daily" in reply_text

    assert context.user_data["delete_choice_source"] == "list"
    assert context.user_data["list_message_ref"] == {"chat_id": 456, "message_id": 999}

    buttons = [button for row in kwargs["reply_markup"].keyboard for button in row]
    assert any(button.callback_data == "del_one:101" for button in buttons)
    assert any(button.callback_data == "del_series:77" for button in buttons)
