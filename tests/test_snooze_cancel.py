import asyncio
from types import SimpleNamespace


class DummyQuery:
    def __init__(self, data: str):
        self.data = data
        self.answers = []
        self.edited_reply_markup = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.answers.append((text, show_alert))

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edited_reply_markup.append(reply_markup)


class DummyUpdate:
    def __init__(self, query):
        self.callback_query = query


class DummyContext:
    pass


def test_snooze_cancel_restores_keyboard(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: None)
    monkeypatch.setattr(m, "build_snooze_keyboard", lambda rid: ("SNOOZE", rid))

    query = DummyQuery(data="snooze_cancel:123")
    upd = DummyUpdate(query)
    ctx = DummyContext()

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1] == ("Вернул варианты", False)
    assert query.edited_reply_markup == [("SNOOZE", 123)]