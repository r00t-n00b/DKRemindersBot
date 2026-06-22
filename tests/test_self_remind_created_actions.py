import asyncio
from datetime import datetime
from types import SimpleNamespace


class DummyInlineKeyboardButton:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.kwargs = kwargs


class DummyInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard
        self.keyboard = inline_keyboard


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=42)
        self.edits = []
        self.answers = []
        self.message = SimpleNamespace(
            text="source message",
            chat=SimpleNamespace(id=-100, title="Тест-группа для бота"),
        )

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))

    async def edit_message_reply_markup(self, **kwargs):
        self.edits.append(("", kwargs))


def _patch_keyboard_classes(main_module, monkeypatch):
    import keyboards

    monkeypatch.setattr(main_module, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)
    monkeypatch.setattr(keyboards, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(keyboards, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)


def _callback_data(markup):
    result = []
    rows = getattr(markup, "inline_keyboard", None)
    if rows is None:
        rows = getattr(markup, "keyboard", None)
    if rows is None:
        rows = []

    for row in rows:
        for button in row:
            data = getattr(button, "callback_data", None)
            if data is not None:
                result.append(data)

    return result


def _assert_created_action_buttons(markup, reminder_id):
    assert markup is not None
    callbacks = set(_callback_data(markup))
    assert f"created_del:{reminder_id}" in callbacks
    assert f"created_resched:{reminder_id}" in callbacks


def _install_common_mocks(main_module, monkeypatch, source_text="callback builders test"):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    source_reminder = SimpleNamespace(
        id=123,
        chat_id=-100,
        text=source_text,
        remind_at=datetime(2026, 6, 22, 18, 0, tzinfo=m.TZ),
        sent_at=datetime(2026, 6, 22, 17, 0, tzinfo=m.TZ),
        created_by=111,
        template_id=None,
    )

    def fake_get_reminder(reminder_id):
        reminder_id = int(reminder_id)
        if reminder_id == 123:
            return source_reminder
        if reminder_id == 777:
            return SimpleNamespace(
                id=777,
                chat_id=555,
                text=f'Из чата "Тест-группа для бота": {source_text}',
                remind_at=datetime(2026, 6, 22, 19, 0, tzinfo=m.TZ),
                sent_at=None,
                created_by=42,
                template_id=None,
            )
        return None

    async def fake_get_source_chat_title_for_self_remind(context, src, query):
        return "Тест-группа для бота"

    created = {}

    def fake_add_reminder(**kwargs):
        created.clear()
        created.update(kwargs)
        assert kwargs["chat_id"] == 555
        assert kwargs["created_by"] == 42
        return 777

    monkeypatch.setattr(m, "get_reminder", fake_get_reminder)
    monkeypatch.setattr(m, "get_now", lambda: datetime(2026, 6, 22, 18, 0, tzinfo=m.TZ))
    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555)
    monkeypatch.setattr(m, "get_source_chat_title_for_self_remind", fake_get_source_chat_title_for_self_remind)
    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    return created


def test_self_remind_set_success_has_created_action_buttons(main_module, monkeypatch):
    m = main_module
    created = _install_common_mocks(m, monkeypatch)

    query = FakeQuery("selfremind:set:123:1h")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()

    asyncio.run(m.snooze_callback(update, context))

    assert query.edits
    text, kwargs = query.edits[-1]
    assert "Ок, напомню" in text
    assert created["template_id"] is None
    _assert_created_action_buttons(kwargs.get("reply_markup"), 777)


def test_self_remind_event_before_success_has_created_action_buttons(main_module, monkeypatch):
    m = main_module
    created = _install_common_mocks(
        m,
        monkeypatch,
        source_text="завтра футбол в 20:00",
    )

    query = FakeQuery("selfremind:event_before:123:1h")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()

    asyncio.run(m.snooze_callback(update, context))

    assert query.edits
    text, kwargs = query.edits[-1]
    assert "Ок, напомню" in text
    assert created["remind_at"] == datetime(2026, 6, 23, 19, 0, tzinfo=m.TZ)
    _assert_created_action_buttons(kwargs.get("reply_markup"), 777)


def test_self_remind_picktime_success_has_created_action_buttons(main_module, monkeypatch):
    m = main_module
    created = _install_common_mocks(m, monkeypatch)

    query = FakeQuery("selfremind_picktime:123:2026-06-23:19:30")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()

    asyncio.run(m.snooze_callback(update, context))

    assert query.edits
    text, kwargs = query.edits[-1]
    assert "Ок, напомню" in text
    assert created["remind_at"] == datetime(2026, 6, 23, 19, 30, tzinfo=m.TZ)
    assert created["template_id"] is None
    _assert_created_action_buttons(kwargs.get("reply_markup"), 777)
