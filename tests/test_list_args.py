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


def _mk_private(text):
    msg = SimpleNamespace(
        text=text,
        replies=[],
        reply_text=lambda t, **k: msg.replies.append(t),
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123, username="u", first_name="U", last_name="L"),
    )
    ctx = SimpleNamespace(user_data={}, args=[])
    return msg, upd, ctx


def test_list_alias_not_found_shows_known(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    monkeypatch.setattr(main_module, "get_user_alias_chat_id_for_user", lambda alias, user_id: None)
    monkeypatch.setattr(main_module, "get_chat_id_by_alias_for_user", lambda alias, user_id: None)
    monkeypatch.setattr(main_module, "get_all_aliases", lambda user_id: [("TeamA", 777, "My Group")])

    msg, upd, ctx = _mk_private("/list TeamX")
    ctx.args = ["TeamX"]

    asyncio.run(main_module.list_command(upd, ctx))

    assert msg.replies
    reply = "\n".join(msg.replies)
    assert "TeamX" in reply
    assert "TeamA" in reply

def test_list_alias_found_lists_reminders(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    monkeypatch.setattr(main_module, "get_chat_id_by_alias", lambda a: 777)

    now = datetime(2025, 1, 24, 10, 0, tzinfo=TZ)
    rid = main_module.add_reminder(
        chat_id=777,
        text="hi",
        remind_at=now,
        created_by=123,
    )
    assert isinstance(rid, int)

    msg, upd, ctx = _mk_private("/list TeamA")
    ctx.args = ["TeamA"]

    asyncio.run(main_module.list_command(upd, ctx))

    assert msg.replies
    reply = "\n".join(msg.replies)
    assert "Активные напоминания" in reply
    assert "TeamA" in reply
    assert "hi" in reply

    assert ctx.user_data.get("list_chat_id") == 777
    assert rid in ctx.user_data.get("list_ids", [])

def test_list_username_not_started(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    monkeypatch.setattr(main_module, "get_private_chat_id_by_username", lambda u: None)

    msg, upd, ctx = _mk_private("/list @someone")
    ctx.args = ["@someone"]

    asyncio.run(main_module.list_command(upd, ctx))

    assert msg.replies
    reply = "\n".join(msg.replies)
    assert "@someone" in reply
    assert "еще не писал" in reply

def test_list_username_no_rows_for_creator(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    monkeypatch.setattr(main_module, "get_private_chat_id_by_username", lambda u: 777)
    monkeypatch.setattr(main_module, "get_active_reminders_created_by_for_chat", lambda **kw: [])

    msg, upd, ctx = _mk_private("/list @someone")
    ctx.args = ["@someone"]

    asyncio.run(main_module.list_command(upd, ctx))

    assert msg.replies
    reply = "\n".join(msg.replies)
    assert "Ты не ставил" in reply
    assert "@someone" in reply

def test_list_username_happy_path_sets_context(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", MockButton, raising=False)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", MockMarkup, raising=False)

    monkeypatch.setattr(main_module, "get_private_chat_id_by_username", lambda u: 777)

    now = datetime(2025, 1, 24, 10, 0, tzinfo=TZ).isoformat()
    rows = [
        {"id": 101, "text": "hello", "remind_at": now, "template_id": None},
        {"id": 102, "text": "world", "remind_at": now, "template_id": None},
    ]
    monkeypatch.setattr(main_module, "get_active_reminders_created_by_for_chat", lambda **kw: rows)

    msg, upd, ctx = _mk_private("/list @someone")
    ctx.args = ["@someone"]

    asyncio.run(main_module.list_command(upd, ctx))

    assert msg.replies
    reply = "\n".join(msg.replies)
    assert "Напоминания, которые ты поставил пользователю @someone" in reply
    assert "hello" in reply
    assert "world" in reply

    assert ctx.user_data.get("list_chat_id") == 777
    assert ctx.user_data.get("list_ids") == [101, 102]