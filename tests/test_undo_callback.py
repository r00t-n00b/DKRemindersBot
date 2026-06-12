import asyncio
from types import SimpleNamespace


def test_undo_callback_no_snapshot_answers_alert(main_module):
    answered = {"called": False, "kwargs": None}

    async def fake_answer(*a, **k):
        answered["called"] = True
        answered["kwargs"] = k

    async def fake_reply_text(*a, **k):
        return None

    cbq = SimpleNamespace(
        data="undo:nope",
        answer=fake_answer,
        message=SimpleNamespace(reply_text=fake_reply_text),
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={"undo_tokens": {}})

    asyncio.run(main_module.undo_callback(upd, ctx))

    assert answered["called"] is True
    assert answered["kwargs"] is not None
    assert answered["kwargs"].get("show_alert") is True


def test_undo_callback_restores_single_reply(main_module, monkeypatch):
    async def fake_answer(*a, **k):
        return None

    replies = []

    async def fake_reply_text(text, **k):
        replies.append(text)

    snapshot = {
        "kind": "single",
        "chat_id": 1,
        "reminder": {"text": "hi", "remind_at": "2025-01-01T10:00:00+01:00", "template_id": None},
        "template": None,
    }

    monkeypatch.setattr(main_module, "restore_deleted_snapshot", lambda snap: "hi")

    cbq = SimpleNamespace(
        data="undo:t1",
        answer=fake_answer,
        message=SimpleNamespace(reply_text=fake_reply_text),
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={"undo_tokens": {"t1": snapshot}})

    asyncio.run(main_module.undo_callback(upd, ctx))

    assert replies
    assert replies[0].startswith("Вернул:")


def test_undo_callback_restores_series_reply(main_module, monkeypatch):
    async def fake_answer(*a, **k):
        return None

    replies = []

    async def fake_reply_text(text, **k):
        replies.append(text)

    snapshot = {
        "kind": "series",
        "chat_id": 1,
        "template": {"text": "series", "pattern_type": "daily", "payload": None},
        "reminders": [
            {"text": "a", "remind_at": "2025-01-01T10:00:00+01:00"},
            {"text": "b", "remind_at": "2025-01-02T10:00:00+01:00"},
        ],
    }

    monkeypatch.setattr(main_module, "restore_deleted_snapshot", lambda snap: [1, 2])

    cbq = SimpleNamespace(
        data="undo:t2",
        answer=fake_answer,
        message=SimpleNamespace(reply_text=fake_reply_text),
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={"undo_tokens": {"t2": snapshot}})

    asyncio.run(main_module.undo_callback(upd, ctx))

    assert replies
    assert replies[0].startswith("Вернул серию:")