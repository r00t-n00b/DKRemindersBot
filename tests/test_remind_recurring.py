import asyncio
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo
from tests.test_remind_negative_cases import _mk_private


TZ = ZoneInfo("Europe/Madrid")


def _run_recurring(
    m,
    text,
    now,
    chat_type="private",
    chat_id=999,
    alias_map=None,
):
    alias_map = alias_map or {}

    replies = []
    added = {}

    def fake_add_reminder(**kw):
        added.update(kw)
        return 1

    def fake_create_tpl(**kw):
        return 42

    m.add_reminder = fake_add_reminder
    m.create_recurring_template = fake_create_tpl
    m.get_now = lambda: now
    m.get_chat_id_by_alias = lambda a: alias_map.get(a)

    msg = SimpleNamespace(
        text=text,
        replies=[],
        reply_text=lambda t, **k: replies.append(t),
    )

    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
        effective_message=msg,
        effective_user=SimpleNamespace(
            id=123,
            username="u",
            first_name="U",
            last_name="L",
        ),
    )

    ctx = SimpleNamespace(user_data={}, args=[])

    asyncio.run(m.remind_command(upd, ctx))

    return added, replies

def _run(m, text, *, now, chat_type="private"):
    added = {}

    def fake_add(chat_id, text, remind_at, created_by, template_id=None):
        added["template_id"] = template_id
        return 1

    m.add_reminder = fake_add
    m.get_now = lambda: now
    m.looks_like_recurring = lambda s: True

    msg = SimpleNamespace(
        text=text,
        reply_text=lambda *a, **k: None,
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type=chat_type),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123),
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(m.remind_command(upd, ctx))
    return added


def test_recurring_every_day(main_module):
    now = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)
    added = _run(main_module, "/remind every day 10:00 - standup", now=now)
    assert "template_id" in added


def test_recurring_weekday(main_module):
    now = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)
    added = _run(main_module, "/remind every monday 9:00 - sync", now=now)
    assert "template_id" in added


def test_recurring_forbidden_in_group(main_module):
    now = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)

    msg = SimpleNamespace(
        text="/remind every day 10:00 - hi",
        replies=[],
        reply_text=lambda t, **k: msg.replies.append(t),
    )

    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=999, type="group"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123),
    )

    ctx = SimpleNamespace(user_data={})

    main_module.get_now = lambda: now

    asyncio.run(main_module.remind_command(upd, ctx))

    assert msg.replies


def test_recurring_with_alias_private(main_module):
    now = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)

    added, _replies = _run_recurring(
        main_module,
        "/remind TeamA every day 10:00 - hi",
        now=now,
        alias_map={"TeamA": 777},
    )

    assert added["chat_id"] == 777
    assert isinstance(added["template_id"], int)
    assert added["template_id"] > 0


def test_recurring_invalid_pattern(main_module):
    msg, upd, ctx = _mk_private("/remind every nonsense 10:00 - hi")
    asyncio.run(main_module.remind_command(upd, ctx))
    assert msg.replies