import asyncio
import os
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")


def _db_rows(sql: str, params=()):
    con = sqlite3.connect(os.environ["DB_PATH"])
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


class _FakeBot:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        if self.fail:
            raise RuntimeError("send failed")
        self.sent.append({"chat_id": chat_id, "text": text, "kwargs": kwargs})


def _run_worker_once(main_module, monkeypatch, *, now, bot):
    m = main_module

    # Worker compares to Chat.PRIVATE
    m.Chat = type("_ChatConst", (), {"PRIVATE": "private"})

    monkeypatch.setattr(m, "get_now", lambda: now)

    # Stop after first sleep
    async def stop_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(m.asyncio, "sleep", stop_sleep)

    app = SimpleNamespace(bot=bot)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(m.reminders_worker(app))


def test_worker_sends_due_oneoff_and_marks_delivered(main_module, monkeypatch):
    m = main_module

    now = datetime(2025, 1, 24, 10, 0, tzinfo=TZ)

    rid = m.add_reminder(
        chat_id=777,
        text="hello",
        remind_at=now - timedelta(minutes=1),
        created_by=1,
    )

    bot = _FakeBot()
    _run_worker_once(m, monkeypatch, now=now, bot=bot)

    assert len(bot.sent) == 1
    assert bot.sent[0]["chat_id"] == 777
    assert "hello" in bot.sent[0]["text"]

    row = _get_row(os.environ["DB_PATH"], rid)
    assert row["delivered"] == 1
    assert row["acked"] == 0
    assert row["sent_at"] is not None
    assert row["nudge_count"] == 0

    # Second run should not re-send delivered reminder
    bot2 = _FakeBot()
    _run_worker_once(m, monkeypatch, now=now, bot=bot2)
    assert bot2.sent == []


def test_worker_recurring_reschedules_next(main_module, monkeypatch):
    m = main_module

    now = datetime(2025, 1, 24, 10, 0, tzinfo=TZ)

    tpl_id = m.create_recurring_template(
        chat_id=888,
        text="ping",
        pattern_type="daily",
        payload=None,
        time_hour=10,
        time_minute=0,
        created_by=1,
    )

    rid = m.add_reminder(
        chat_id=888,
        text="ping",
        remind_at=now - timedelta(minutes=1),
        created_by=1,
        template_id=tpl_id,
    )

    bot = _FakeBot()
    _run_worker_once(m, monkeypatch, now=now, bot=bot)

    row_old = _get_row(os.environ["DB_PATH"], rid)
    assert row_old["delivered"] == 1
    assert row_old["acked"] == 0
    assert row_old["sent_at"] is not None
    assert row_old["nudge_count"] == 0

    rows_all = _db_rows(
        "SELECT id, delivered, remind_at FROM reminders WHERE template_id = ? ORDER BY id ASC",
        (tpl_id,),
    )
    assert len(rows_all) == 2
    assert rows_all[1]["delivered"] == 0
    assert rows_all[1]["id"] != rid


def test_worker_send_failure_does_not_mark_delivered_or_reschedule(main_module, monkeypatch):
    m = main_module

    now = datetime(2025, 1, 24, 10, 0, tzinfo=TZ)

    tpl_id = m.create_recurring_template(
        chat_id=999,
        text="oops",
        pattern_type="daily",
        payload=None,
        time_hour=10,
        time_minute=0,
        created_by=1,
    )

    rid = m.add_reminder(
        chat_id=999,
        text="oops",
        remind_at=now - timedelta(minutes=1),
        created_by=1,
        template_id=tpl_id,
    )

    bot = _FakeBot(fail=True)
    _run_worker_once(m, monkeypatch, now=now, bot=bot)

    row_old = _get_row(os.environ["DB_PATH"], rid)
    assert row_old["delivered"] == 0
    assert row_old["acked"] == 0
    assert row_old["sent_at"] is None
    assert row_old["nudge_count"] == 0

    rows_tpl = _db_rows("SELECT id FROM reminders WHERE template_id = ?", (tpl_id,))
    assert len(rows_tpl) == 1

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