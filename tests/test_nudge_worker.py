import asyncio
import os
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def _get_row(db_path: str, rid: int) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """
            SELECT
                id,
                delivered,
                acked,
                sent_at,
                nudge_count
            FROM reminders
            WHERE id = ?
            """,
            (rid,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        con.close()


def test_nudge_sent_after_20_min_if_no_action(main_module, monkeypatch):
    m = main_module
    db_path = os.environ["DB_PATH"]

    now = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)

    rid = m.add_reminder(
        chat_id=123,
        text="hello",
        remind_at=now,
        created_by=1,
    )

    # симулируем "уже отправлено, но не подтверждено"
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """
            UPDATE reminders
            SET delivered = 1,
                acked = 0,
                nudge_count = 0,
                sent_at = ?
            WHERE id = ?
            """,
            ((now - timedelta(minutes=21)).isoformat(), rid),
        )
        con.commit()
    finally:
        con.close()

    # чтобы не зависеть от telegram InlineKeyboardButton/Markup
    monkeypatch.setattr(m, "build_snooze_keyboard", lambda _rid: None)

    sent = []

    async def fake_send_message(chat_id, text, reply_markup=None, **kwargs):
        sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return None

    async def fake_get_chat(chat_id):
        return SimpleNamespace(type="private")

    app = SimpleNamespace(
        bot=SimpleNamespace(
            send_message=fake_send_message,
            get_chat=fake_get_chat,
        )
    )

    async def fake_sleep(_):
        raise RuntimeError("stop")

    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(m, "get_now", lambda: now)

    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError as e:
        assert str(e) == "stop"

    assert len(sent) == 1
    assert sent[0]["chat_id"] == 123
    assert "Ты никак не отреагировал" in sent[0]["text"]

    row = _get_row(db_path, rid)
    assert row["nudge_count"] == 1


def test_done_marks_acked_and_prevents_nudge(main_module, monkeypatch):
    m = main_module
    db_path = os.environ["DB_PATH"]

    now = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)

    rid = m.add_reminder(
        chat_id=123,
        text="hello",
        remind_at=now,
        created_by=1,
    )

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """
            UPDATE reminders
            SET delivered = 1,
                acked = 0,
                nudge_count = 0,
                sent_at = ?
            WHERE id = ?
            """,
            ((now - timedelta(minutes=30)).isoformat(), rid),
        )
        con.commit()
    finally:
        con.close()

    # нажали done
    answered = {"ok": False}

    async def fake_answer(*a, **k):
        answered["ok"] = True

    cbq = SimpleNamespace(
        data=f"done:{rid}",
        answer=fake_answer,
        message=None,
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={})

    asyncio.run(m.snooze_callback(upd, ctx))
    assert answered["ok"] is True

    row = _get_row(db_path, rid)
    assert row["acked"] == 1

    # нудж не должен уходить
    sent = []

    async def fake_send_message(chat_id, text, reply_markup=None, **kwargs):
        sent.append({"chat_id": chat_id, "text": text})
        return None

    app = SimpleNamespace(bot=SimpleNamespace(send_message=fake_send_message))

    async def fake_sleep(_):
        raise RuntimeError("stop")

    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(m, "get_now", lambda: now)

    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError:
        pass

    assert sent == []

def test_nudge_not_sent_in_channel(main_module, monkeypatch):
    m = main_module
    db_path = os.environ["DB_PATH"]

    now = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)

    rid = m.add_reminder(
        chat_id=777,
        text="hello",
        remind_at=now,
        created_by=1,
    )

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """
            UPDATE reminders
            SET delivered = 1,
                acked = 0,
                nudge_count = 0,
                sent_at = ?
            WHERE id = ?
            """,
            ((now - timedelta(minutes=21)).isoformat(), rid),
        )
        con.commit()
    finally:
        con.close()

    sent = []

    async def fake_send_message(chat_id, text, reply_markup=None, **kwargs):
        sent.append({"chat_id": chat_id, "text": text})
        return None

    class _FakeChat:
        def __init__(self, chat_type):
            self.type = chat_type

    async def fake_get_chat(_chat_id):
        return _FakeChat("channel")

    app = SimpleNamespace(
        bot=SimpleNamespace(
            send_message=fake_send_message,
            get_chat=fake_get_chat,
        )
    )

    # Worker compares to Chat.PRIVATE
    m.Chat = type("_ChatConst", (), {"PRIVATE": "private"})

    async def fake_sleep(_):
        raise RuntimeError("stop")

    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(m, "get_now", lambda: now)

    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError as e:
        assert str(e) == "stop"

    assert sent == []

    row = _get_row(db_path, rid)
    assert row["nudge_count"] == 0

def test_nudge_is_not_sent_to_group_or_channel(main_module, monkeypatch):
    m = main_module
    db_path = os.environ["DB_PATH"]

    now = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)

    rid = m.add_reminder(
        chat_id=555,
        text="hello",
        remind_at=now,
        created_by=1,
    )

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """
            UPDATE reminders
            SET delivered = 1,
                acked = 0,
                nudge_count = 0,
                sent_at = ?
            WHERE id = ?
            """,
            ((now - timedelta(minutes=25)).isoformat(), rid),
        )
        con.commit()
    finally:
        con.close()

    monkeypatch.setattr(m, "build_snooze_keyboard", lambda _rid: None)

    sent = []

    async def fake_send_message(chat_id, text, reply_markup=None, **kwargs):
        sent.append({"chat_id": chat_id, "text": text})
        return None

    async def fake_get_chat(chat_id):
        return SimpleNamespace(type="channel")

    app = SimpleNamespace(
        bot=SimpleNamespace(
            send_message=fake_send_message,
            get_chat=fake_get_chat,
        )
    )

    async def fake_sleep(_):
        raise RuntimeError("stop")

    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(m, "get_now", lambda: now)

    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError as e:
        assert str(e) == "stop"

    assert sent == []

    row = _get_row(db_path, rid)
    assert row["nudge_count"] == 0

def test_nudge_schedule_and_max_4(main_module, monkeypatch):
    m = main_module
    db_path = os.environ["DB_PATH"]

    base_sent_at = datetime(2025, 1, 1, 10, 0, tzinfo=TZ)

    rid = m.add_reminder(
        chat_id=123,
        text="hello",
        remind_at=base_sent_at,
        created_by=1,
    )

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """
            UPDATE reminders
            SET delivered = 1,
                acked = 0,
                nudge_count = 0,
                sent_at = ?
            WHERE id = ?
            """,
            (base_sent_at.isoformat(), rid),
        )
        con.commit()
    finally:
        con.close()

    monkeypatch.setattr(m, "build_snooze_keyboard", lambda _rid: None)

    async def fake_get_chat(_chat_id):
        return SimpleNamespace(type="private")

    async def stop_sleep(_):
        raise RuntimeError("stop")

    monkeypatch.setattr(m.asyncio, "sleep", stop_sleep)

    sent = []

    async def fake_send_message(chat_id, text, reply_markup=None, **kwargs):
        sent.append({"chat_id": chat_id, "text": text})
        return None

    app = SimpleNamespace(
        bot=SimpleNamespace(
            send_message=fake_send_message,
            get_chat=fake_get_chat,
        )
    )

    # 1) +21m -> nudge_count 0 -> должен уйти
    monkeypatch.setattr(m, "get_now", lambda: base_sent_at + timedelta(minutes=21))
    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError:
        pass
    assert len(sent) == 1
    assert _get_row(db_path, rid)["nudge_count"] == 1

    # 2) +79m -> еще рано (нужно 80) -> не уйдет
    sent.clear()
    monkeypatch.setattr(m, "get_now", lambda: base_sent_at + timedelta(minutes=79))
    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError:
        pass
    assert sent == []
    assert _get_row(db_path, rid)["nudge_count"] == 1

    # 2) +81m -> должен уйти
    monkeypatch.setattr(m, "get_now", lambda: base_sent_at + timedelta(minutes=81))
    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError:
        pass
    assert len(sent) == 1
    assert _get_row(db_path, rid)["nudge_count"] == 2

    # 3) +321m -> должен уйти (порог 320)
    sent.clear()
    monkeypatch.setattr(m, "get_now", lambda: base_sent_at + timedelta(minutes=321))
    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError:
        pass
    assert len(sent) == 1
    assert _get_row(db_path, rid)["nudge_count"] == 3

    # 4) +1041m -> должен уйти (порог 1040) и стать 4
    sent.clear()
    monkeypatch.setattr(m, "get_now", lambda: base_sent_at + timedelta(minutes=1041))
    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError:
        pass
    assert len(sent) == 1
    assert _get_row(db_path, rid)["nudge_count"] == 4

    # дальше никогда
    sent.clear()
    monkeypatch.setattr(m, "get_now", lambda: base_sent_at + timedelta(minutes=2000))
    try:
        asyncio.run(m.reminders_nudge_worker(app))
    except RuntimeError:
        pass
    assert sent == []
    assert _get_row(db_path, rid)["nudge_count"] == 4