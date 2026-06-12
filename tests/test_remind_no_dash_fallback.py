import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")


def _run_remind_capture(
    main_module,
    monkeypatch,
    *,
    cmd_text: str,
    now: datetime,
    chat_type: str = "private",
    chat_id: int = 999,
    alias_map=None,
    username_map=None,
):
    m = main_module

    # Telegram constants used in code
    m.Chat = type("_ChatConst", (), {"PRIVATE": "private"})

    monkeypatch.setattr(m, "get_now", lambda: now)

    # Maps for alias/@username resolution
    alias_map = alias_map or {}
    username_map = username_map or {}

    monkeypatch.setattr(m, "get_chat_id_by_alias", lambda alias: alias_map.get(alias))
    monkeypatch.setattr(m, "get_user_chat_id_by_username", lambda u: username_map.get(u))

    captured = {}

    def fake_add_reminder(**kwargs):
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    # Avoid touching DB in this test
    monkeypatch.setattr(m, "upsert_user_chat", lambda **k: None)

    msg = SimpleNamespace(
        text=cmd_text,
        replies=[],
        reply_text=lambda t, **k: msg.replies.append(t),
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type, title="T"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123, username="u", first_name="U", last_name="L"),
    )
    ctx = SimpleNamespace(user_data={}, args=[])

    asyncio.run(m.remind_command(upd, ctx))
    return captured, msg.replies


def test_no_dash_parses_absolute_date_time(main_module, monkeypatch):
    now = datetime(2026, 1, 29, 19, 0, tzinfo=TZ)

    added, _replies = _run_remind_capture(
        main_module,
        monkeypatch,
        cmd_text="/remind 5.02.2026 17:00 test",
        now=now,
    )

    assert added["chat_id"] == 999
    assert added["text"] == "test"

    dt = added["remind_at"]
    assert dt.year == 2026
    assert dt.month == 2
    assert dt.day == 5
    assert dt.hour == 17
    assert dt.minute == 0


def test_no_dash_with_alias_private_routes_to_alias_chat(main_module, monkeypatch):
    now = datetime(2026, 1, 29, 19, 0, tzinfo=TZ)

    added, _replies = _run_remind_capture(
        main_module,
        monkeypatch,
        cmd_text="/remind TeamA 5.02.2026 17:00 test",
        now=now,
        alias_map={"TeamA": 777},
    )

    assert added["chat_id"] == 777
    assert added["text"] == "test"


def test_no_dash_with_username_private_routes_to_user_chat(main_module, monkeypatch):
    now = datetime(2026, 1, 29, 19, 0, tzinfo=TZ)

    added, _replies = _run_remind_capture(
        main_module,
        monkeypatch,
        cmd_text="/remind @friend1 5.02.2026 17:00 test",
        now=now,
        username_map={"@friend1": 888},
    )

    assert added["chat_id"] == 888
    assert added["text"] == "test"


def test_dash_format_still_works(main_module, monkeypatch):
    now = datetime(2026, 1, 29, 19, 0, tzinfo=TZ)

    added, _replies = _run_remind_capture(
        main_module,
        monkeypatch,
        cmd_text="/remind 5.02.2026 17:00 - test",
        now=now,
    )

    assert added["chat_id"] == 999
    assert added["text"] == "test"


def test_dash_text_with_hyphen_preserved(main_module, monkeypatch):
    now = datetime(2026, 1, 29, 19, 0, tzinfo=TZ)

    added, _replies = _run_remind_capture(
        main_module,
        monkeypatch,
        cmd_text="/remind 5.02.2026 17:00 - pay-for-stuff",
        now=now,
    )

    assert added["text"] == "pay-for-stuff"


def test_group_alias_like_token_is_ignored_and_reminder_created_in_group(main_module, monkeypatch):
    now = datetime(2026, 1, 29, 19, 0, tzinfo=TZ)

    added, _replies = _run_remind_capture(
        main_module,
        monkeypatch,
        cmd_text="/remind TeamA 5.02.2026 17:00 test",
        now=now,
        chat_type="group",
        chat_id=999,
        alias_map={"TeamA": 777},
    )

    # Новое правило: в группе alias в начале запрещен
    assert not added