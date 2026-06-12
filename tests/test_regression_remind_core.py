import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace

TZ = ZoneInfo("Europe/Madrid")


import asyncio
from types import SimpleNamespace


def _run_remind(
    m,
    text,
    now,
    chat_type="private",
    chat_id=999,
    alias_map=None,
    username_map=None,
    return_replies=False,
    monkeypatch=None,
):
    alias_map = alias_map or {}
    username_map = username_map or {}

    if monkeypatch is not None:
        monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    m.get_now = lambda: now
    m.looks_like_recurring = lambda s: False
    m.upsert_user_chat = lambda **kw: None

    m.get_chat_id_by_alias = lambda a: alias_map.get(a)
    m.get_user_chat_id_by_username = lambda u: username_map.get(u)

    replies = []
    msg = SimpleNamespace(
        text=text,
        reply_text=lambda t, **k: replies.append(t),
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123, username="u", first_name="U", last_name="L"),
    )
    ctx = SimpleNamespace(user_data={})

    added = {}

    def fake_add_reminder(chat_id, text, remind_at, created_by, template_id=None):
        added["chat_id"] = chat_id
        added["text"] = text
        added["remind_at"] = remind_at
        return 1

    m.add_reminder = fake_add_reminder

    asyncio.run(m.remind_command(upd, ctx))

    if return_replies:
        return added, replies
    return added


# ---------- ABSOLUTE DATE REGRESSIONS ----------

def test_dot_date_not_misread_as_time(main_module):
    now = datetime(2025, 11, 28, 10, 0, tzinfo=TZ)
    added = _run_remind(main_module, "/remind 29.11 - hi", now=now)
    assert added["chat_id"] == 999


def test_ddmm_time_with_dash(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)
    added = _run_remind(
        main_module,
        "/remind 02.02 12:00 - завтра футбол",
        now=now,
    )
    assert added["chat_id"] == 999


def test_time_only_moves_to_next_day(main_module):
    now = datetime(2025, 1, 24, 23, 50, tzinfo=TZ)
    added = _run_remind(main_module, "/remind 23:40 - hi", now=now)
    assert added["chat_id"] == 999
    assert added["remind_at"].day == 25


# ---------- ALIAS / USERNAME REGRESSIONS ----------

def test_private_chat_alias_works(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)
    added = _run_remind(
        main_module,
        "/remind TeamA 02.02 - hi",
        now=now,
        chat_type="private",
        alias_map={"TeamA": 777},
    )
    assert added["chat_id"] == 777


def test_group_chat_ignores_alias(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        main_module,
        "/remind TeamA 02.02 - hi",
        now=now,
        chat_type="group",
        chat_id=999,
        alias_map={"TeamA": 777},
    )

    # Новое правило: в группе запрещаем alias как переключатель
    assert not added


def test_group_chat_ignores_username(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        main_module,
        "/remind @someone 02.02 - hi",
        now=now,
        chat_type="group",
        chat_id=999,
        username_map={"@someone": 777},
    )

    # Новое правило: в группе запрещаем @username как переключатель
    assert not added


# ---------- BULK / FORMAT REGRESSIONS ----------

def test_bulk_single_line_still_works(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)
    added = _run_remind(
        main_module,
        "/remind\n- 02.02 12:00 - hi",
        now=now,
    )
    assert added["chat_id"] == 999

def test_bulk_with_alias_in_group_creates_nothing(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        main_module,
        "/remind\n- TeamA 02.02 - hi",
        now=now,
        chat_type="group",
        alias_map={"TeamA": 777},
    )

    assert added == {}


def test_bulk_with_username_in_group_creates_nothing(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        main_module,
        "/remind\n- @someone 02.02 - hi",
        now=now,
        chat_type="group",
        username_map={"@someone": 777},
    )

    assert added == {}


def test_bulk_without_dash_is_ignored(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added = _run_remind(
        main_module,
        "/remind\n02.02 12:00 - hi",
        now=now,
    )

    assert added["chat_id"] == 999
    assert added["text"] == "hi"
    assert added["remind_at"].strftime("%d.%m %H:%M") == "02.02 12:00"


def test_bulk_partial_success(main_module):
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    added, replies = _run_remind(
        main_module,
        "/remind\n- 02.02 12:00 - ok\n- foo bar",
        now=now,
        return_replies=True,
    )

    assert added["text"] == "ok"
    assert any("Не удалось разобрать" in r for r in replies)