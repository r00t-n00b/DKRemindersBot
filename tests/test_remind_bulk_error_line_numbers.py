import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")


def test_bulk_partial_success_includes_line_numbers(main_module):
    m = main_module
    now = datetime(2026, 1, 31, 12, 0, tzinfo=TZ)

    m.get_now = lambda: now
    m.looks_like_recurring = lambda s: False
    m.upsert_user_chat = lambda **kw: None

    replies = []
    msg = SimpleNamespace(
        text="/remind\n02.02 12:00 - ok\nfoo bar\n",
        reply_text=lambda t, **k: replies.append(t),
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=999, type="private"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123, username="u", first_name="U", last_name="L"),
    )
    ctx = SimpleNamespace(user_data={})

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append((chat_id, text, remind_at))
        return 1

    m.add_reminder = fake_add_reminder

    asyncio.run(m.remind_command(upd, ctx))

    assert len(created) == 1
    assert replies
    joined = "\n".join(replies)

    assert "Не удалось разобрать" in joined
    assert "Проблемные строки" in joined
    assert "2)" in joined
    assert "foo bar" in joined