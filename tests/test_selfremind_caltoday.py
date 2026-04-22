import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")


class DummyQuery:
    def __init__(self, data: str):
        self.data = data
        self.answers = []
        self.edited_reply_markup = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.answers.append((text, show_alert))

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edited_reply_markup.append(reply_markup)
        raise Exception("message is not modified")


class DummyUpdate:
    def __init__(self, query):
        self.callback_query = query


class DummyContext:
    pass


def test_selfremind_caltoday_ignores_not_modified_error(main_module, monkeypatch):
    m = main_module

    now = datetime(2026, 4, 22, 2, 42, tzinfo=TZ)

    class FakeDateTime:
        @staticmethod
        def now(tz=None):
            return now

    monkeypatch.setattr(m, "datetime", FakeDateTime)

    monkeypatch.setattr(
        m,
        "build_custom_date_keyboard",
        lambda rid, year=None, month=None, callback_prefix="snooze": ("CAL", rid, year, month, callback_prefix),
    )

    query = DummyQuery(data="selfremind_caltoday:123")
    upd = DummyUpdate(query)
    ctx = DummyContext()

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1] == (None, False)
    assert query.edited_reply_markup == [("CAL", 123, 2026, 4, "selfremind")]