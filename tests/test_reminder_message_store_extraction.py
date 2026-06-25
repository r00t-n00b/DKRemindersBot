import asyncio
import sqlite3
from datetime import datetime
from types import SimpleNamespace

import main
import reminder_message_store


def test_main_register_reminder_message_delegates_to_impl(monkeypatch):
    calls = []

    def fake_impl(reminder_id, chat_id, message_id, kind, deps):
        calls.append((reminder_id, chat_id, message_id, kind, deps))

    monkeypatch.setattr(main, "register_reminder_message_impl", fake_impl)

    main.register_reminder_message(1, 2, 3, "delivery")

    assert len(calls) == 1
    assert calls[0][:4] == (1, 2, 3, "delivery")


def test_main_get_reminder_messages_delegates_to_impl(monkeypatch):
    calls = []

    def fake_impl(reminder_id, deps):
        calls.append((reminder_id, deps))
        return [{"message_id": 10}]

    monkeypatch.setattr(main, "get_reminder_messages_impl", fake_impl)

    rows = main.get_reminder_messages(7)

    assert rows == [{"message_id": 10}]
    assert len(calls) == 1
    assert calls[0][0] == 7


def test_main_clear_reminder_message_keyboards_delegates_to_impl(monkeypatch):
    calls = []

    async def fake_impl(bot, reminder_id, deps, replacement_text=None):
        calls.append((bot, reminder_id, deps, replacement_text))

    monkeypatch.setattr(main, "clear_reminder_message_keyboards_impl", fake_impl)

    bot = object()
    asyncio.run(main.clear_reminder_message_keyboards(bot, 99))

    assert len(calls) == 1
    assert calls[0][0] is bot
    assert calls[0][1] == 99
    assert calls[0][3] is None


def test_main_clear_reminder_message_keyboards_passes_replacement_text(monkeypatch):
    calls = []

    async def fake_impl(bot, reminder_id, deps, replacement_text=None):
        calls.append((bot, reminder_id, deps, replacement_text))

    monkeypatch.setattr(main, "clear_reminder_message_keyboards_impl", fake_impl)

    bot = object()
    asyncio.run(
        main.clear_reminder_message_keyboards(
            bot,
            99,
            replacement_text="updated reminder text",
        )
    )

    assert len(calls) == 1
    assert calls[0][0] is bot
    assert calls[0][1] == 99
    assert calls[0][3] == "updated reminder text"


def test_reminder_message_store_module_does_not_import_main():
    source = open("reminder_message_store.py").read()

    assert "import main" not in source
    assert "from main import" not in source


def test_reminder_message_store_register_and_fetch_roundtrip(tmp_path):
    db_path = tmp_path / "reminders.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE reminder_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(reminder_id, chat_id, message_id)
        )
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(
        DB_PATH=str(db_path),
        get_now=lambda: datetime(2026, 1, 2, 3, 4, 5),
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        sqlite3=sqlite3,
    )

    reminder_message_store.register_reminder_message_impl(1, 10, 100, "delivery", deps)
    reminder_message_store.register_reminder_message_impl(1, 10, 100, "delivery", deps)
    reminder_message_store.register_reminder_message_impl(1, 10, 101, "nudge", deps)

    rows = reminder_message_store.get_reminder_messages_impl(1, deps)

    assert [row["message_id"] for row in rows] == [100, 101]
    assert rows[0]["kind"] == "delivery"
    assert rows[1]["kind"] == "nudge"


def test_reminder_message_store_clear_keyboards_uses_registered_messages(tmp_path):
    db_path = tmp_path / "reminders.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE reminder_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(reminder_id, chat_id, message_id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO reminder_messages(reminder_id, chat_id, message_id, kind, created_at)
        VALUES (5, 1000, 2000, 'delivery', '2026-01-02T03:04:05')
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(
        DB_PATH=str(db_path),
        get_now=lambda: datetime(2026, 1, 2, 3, 4, 5),
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        sqlite3=sqlite3,
    )

    class Bot:
        def __init__(self):
            self.calls = []

        async def edit_message_reply_markup(self, **kwargs):
            self.calls.append(kwargs)

    bot = Bot()

    asyncio.run(reminder_message_store.clear_reminder_message_keyboards_impl(bot, 5, deps))

    assert bot.calls == [
        {
            "chat_id": 1000,
            "message_id": 2000,
            "reply_markup": None,
        }
    ]


def test_reminder_message_store_replaces_text_when_replacement_text_is_passed(tmp_path):
    db_path = tmp_path / "reminders.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE reminder_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(reminder_id, chat_id, message_id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO reminder_messages(reminder_id, chat_id, message_id, kind, created_at)
        VALUES (5, 1000, 2000, 'nudge', '2026-01-02T03:04:05')
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(
        DB_PATH=str(db_path),
        get_now=lambda: datetime(2026, 1, 2, 3, 4, 5),
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        sqlite3=sqlite3,
    )

    class Bot:
        def __init__(self):
            self.text_calls = []
            self.markup_calls = []

        async def edit_message_text(self, **kwargs):
            self.text_calls.append(kwargs)

        async def edit_message_reply_markup(self, **kwargs):
            self.markup_calls.append(kwargs)

    bot = Bot()

    asyncio.run(
        reminder_message_store.clear_reminder_message_keyboards_impl(
            bot,
            5,
            deps,
            replacement_text="Обновленный текст",
        )
    )

    assert bot.text_calls == [
        {
            "chat_id": 1000,
            "message_id": 2000,
            "text": "Обновленный текст",
            "reply_markup": None,
        }
    ]
    assert bot.markup_calls == []
