import asyncio

class DummyInlineKeyboardButton:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.kwargs = kwargs


class DummyInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard

class DummyMessage:
    def __init__(self):
        self.replies = []
        self.edits = []
        self.chat = None

    async def reply_text(self, text, reply_markup=None):
        self.replies.append((text, reply_markup))

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


class DummyChat:
    def __init__(self, chat_id):
        self.id = chat_id


class DummyCallbackQuery:
    def __init__(self, data, chat_id=1):
        self.data = data
        self.message = DummyMessage()
        self.message.chat = DummyChat(chat_id)
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))

    async def edit_message_text(self, text, reply_markup=None):
        # PTB shortcut: query.edit_message_text(...)
        await self.message.edit_message_text(text, reply_markup=reply_markup)


class DummyUpdate:
    def __init__(self, query):
        self.callback_query = query


class DummyContext:
    def __init__(self):
        self.user_data = {}


def test_delete_choose_del_one_calls_recurring_delete(main_module, fixed_now, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)
    chat_id = 555
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="daily",
        payload={},
        time_hour=23,
        time_minute=0,
        created_by=user_id,
    )
    r1 = m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=fixed_now.replace(day=29, hour=23, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    ctx = DummyContext()
    ctx.user_data["list_chat_id"] = chat_id
    ctx.user_data["list_ids"] = [r1]

    called = {"ok": False}
    real_fn = m.delete_recurring_one_instance_and_reschedule

    def _wrapped(rid, cid):
        called["ok"] = True
        return real_fn(rid, cid)

    monkeypatch.setattr(m, "delete_recurring_one_instance_and_reschedule", _wrapped)

    q = DummyCallbackQuery(data=f"del_one:{r1}", chat_id=chat_id)
    upd = DummyUpdate(q)

    asyncio.run(m.delete_choose_callback(upd, ctx))

    assert called["ok"] is True

    # Серия должна жить: в БД должен быть хотя бы один reminder с этим template_id
    rows = m.get_active_reminders_for_chat(chat_id)
    assert any(int(r.get("template_id") or 0) == int(tpl_id) for r in rows)

    # Новое правильное поведение: не reply_text, а замена текущего сообщения на undo-result
    assert q.message.replies == []
    assert q.message.edits, "Ожидали edit_message_text с undo"

    edited_text, reply_markup = q.message.edits[-1]
    assert edited_text.startswith("Удалил ближайшее повторяющееся напоминание: ")
    assert "series" in edited_text
    assert reply_markup is not None


def test_delete_choose_del_series_deactivates_template(main_module, fixed_now, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)

    chat_id = 666
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="weekly",
        payload={"weekday": 0},
        time_hour=11,
        time_minute=0,
        created_by=user_id,
    )
    r1 = m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=fixed_now.replace(day=29, hour=11, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    ctx = DummyContext()
    ctx.user_data["list_chat_id"] = chat_id
    ctx.user_data["list_ids"] = [r1]

    q = DummyCallbackQuery(data=f"del_series:{tpl_id}", chat_id=chat_id)
    upd = DummyUpdate(q)

    asyncio.run(m.delete_choose_callback(upd, ctx))

    tpl = m.get_recurring_template(tpl_id)
    assert tpl is not None
    assert tpl["active"] is False

    # Инстансы серии должны быть удалены
    rows = m.get_active_reminders_for_chat(chat_id)
    assert all(int(r.get("template_id") or 0) != int(tpl_id) for r in rows)