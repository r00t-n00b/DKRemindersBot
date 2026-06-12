import asyncio
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo


def _run_remind(m, text, fixed_now, alias_map=None, chat_type="private"):
    TZ = ZoneInfo("Europe/Madrid")

    # --- окружение ---
    m.Chat = SimpleNamespace(PRIVATE="private", GROUP="group")

    m.get_now = lambda: fixed_now
    m.looks_like_recurring = lambda s: False
    m.upsert_user_chat = lambda **kw: None

    if alias_map:
        m.get_chat_id_by_alias = lambda a: alias_map.get(a)
    else:
        m.get_chat_id_by_alias = lambda a: None

    added = {}

    def fake_add_reminder(chat_id, text, remind_at, created_by, template_id=None):
        added["chat_id"] = chat_id
        added["text"] = text
        added["remind_at"] = remind_at
        return 1

    m.add_reminder = fake_add_reminder

    msg = SimpleNamespace(
        text=text,
        reply_text=lambda *a, **k: None,
    )
    chat = SimpleNamespace(id=999, type=chat_type)
    user = SimpleNamespace(id=123, username="u", first_name="U", last_name="L")

    upd = SimpleNamespace(
        effective_chat=chat,
        effective_message=msg,
        effective_user=user,
    )
    ctx = SimpleNamespace(user_data={})

    asyncio.run(m.remind_command(upd, ctx))
    return added

def test_private_alias_absolute_datetime(main_module):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        m,
        "/remind TeamA 02.02 12:00 - demo",
        fixed_now=now,
        alias_map={"TeamA": 777},
        chat_type="private",
    )

    assert added["chat_id"] == 777
    assert added["text"] == "demo"


def test_private_alias_date_only(main_module):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        m,
        "/remind TeamA 02.02 - demo",
        fixed_now=now,
        alias_map={"TeamA": 777},
    )

    assert added["chat_id"] == 777


def test_private_alias_time_only(main_module):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 10, 0, tzinfo=TZ)

    added = _run_remind(
        m,
        "/remind TeamA 23:59 - demo",
        fixed_now=now,
        alias_map={"TeamA": 777},
    )

    assert added["chat_id"] == 777


def test_alias_not_found_does_not_add(main_module):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        m,
        "/remind Unknown 02.02 - demo",
        fixed_now=now,
        alias_map={},
    )

    assert added == {}


def test_group_chat_with_alias_creates_in_current_chat(main_module):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        m,
        "/remind TeamA 02.02 - demo",
        fixed_now=now,
        alias_map={"TeamA": 777},
        chat_type="group",
    )

    # Новое правило: в группе alias в начале запрещен
    assert not added

def test_alias_without_date_does_not_create_reminder(main_module):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        m,
        "/remind TeamA - hi",
        fixed_now=now,
        alias_map={"TeamA": 777},
        chat_type="private",
    )

    assert added == {}

def test_invalid_date_does_not_create_reminder(main_module):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        m,
        "/remind 99.99 - hi",
        fixed_now=now,
        chat_type="private",
    )

    assert added == {}