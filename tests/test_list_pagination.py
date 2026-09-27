import asyncio
from types import SimpleNamespace

from dkreminders_bot.ui.keyboards import build_list_delete_keyboard
from dkreminders_bot.callbacks.list_pagination import handle_list_page_callback


class CapturedButton:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data


class CapturedMarkup:
    def __init__(self, rows):
        self.rows = rows


def _build_captured_keyboard(monkeypatch, count, *, page, total_pages):
    import dkreminders_bot.ui.keyboards as keyboards

    monkeypatch.setattr(keyboards, "InlineKeyboardButton", CapturedButton)
    monkeypatch.setattr(keyboards, "InlineKeyboardMarkup", CapturedMarkup)

    return keyboards.build_list_delete_keyboard(
        count,
        page=page,
        total_pages=total_pages,
    )


def _callback_data(keyboard):
    return [
        button.callback_data
        for row in keyboard.rows
        for button in row
    ]


def test_first_page_keyboard_has_next_only(monkeypatch):
    kb = _build_captured_keyboard(
        monkeypatch, 20, page=0, total_pages=3
    )
    data = _callback_data(kb)

    assert "list_page:1" in data
    assert "list_page:0" not in data
    assert "list_page:2" not in data


def test_middle_page_keyboard_has_previous_and_next(monkeypatch):
    kb = _build_captured_keyboard(
        monkeypatch, 20, page=1, total_pages=3
    )
    data = _callback_data(kb)

    assert "list_page:0" in data
    assert "list_page:2" in data


def test_last_page_keyboard_has_previous_only_and_12_deletes(monkeypatch):
    kb = _build_captured_keyboard(
        monkeypatch, 12, page=2, total_pages=3
    )
    data = _callback_data(kb)

    assert "list_page:1" in data
    assert "list_page:3" not in data

    deletes = [value for value in data if value.startswith("del:")]
    assert deletes == [f"del:{idx}" for idx in range(1, 13)]


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.last_query = ""

    def execute(self, query, params):
        self.last_query = query

    def fetchall(self):
        if "PRAGMA table_info(reminders)" in self.last_query:
            return [
                (0, "id"),
                (1, "text"),
                (2, "remind_at"),
                (3, "template_id"),
                (4, "timezone_name"),
            ]
        if "PRAGMA table_info(recurring_templates)" in self.last_query:
            return [
                (0, "id"),
                (1, "pattern_type"),
                (2, "payload"),
                (3, "timezone_name"),
            ]
        return self.rows


class FakeConn:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


class FakeSqlite:
    def __init__(self, rows):
        self.rows = rows

    def connect(self, path):
        return FakeConn(self.rows)


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.edits = []

    async def answer(self, *args, **kwargs):
        pass

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


def test_page_callback_updates_visible_delete_ids():
    rows = [
        (
            idx,
            f"reminder {idx}",
            f"2026-10-{((idx - 1) % 28) + 1:02d}T10:00:00+02:00",
            None,
            None,
            None,
            "Europe/Madrid",
        )
        for idx in range(21, 41)
    ]

    query = FakeQuery("list_page:1")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "list_all_ids": list(range(1, 53)),
            "list_ids": list(range(1, 21)),
            "list_page": 0,
            "list_page_size": 20,
            "list_chat_id": 100,
            "list_alias": None,
        }
    )

    def build_response(rows, header, now_local, list_delete_keyboard_builder):
        ids = [row[0] for row in rows]
        return header, ids, list_delete_keyboard_builder(len(ids))

    deps = SimpleNamespace(
        DB_PATH="/tmp/test.db",
        sqlite3=FakeSqlite(rows),
        get_now=lambda: None,
        build_active_reminders_list_response=build_response,
        build_list_delete_keyboard=build_list_delete_keyboard,
    )

    asyncio.run(handle_list_page_callback(update, context, deps))

    assert context.user_data["list_page"] == 1
    assert context.user_data["list_ids"] == list(range(21, 41))
    assert "Страница 2/3 · всего 52." in query.edits[0][0]


def test_main_list_keyboard_proxy_preserves_pagination(monkeypatch):
    import main
    import dkreminders_bot.ui.keyboards as keyboards

    monkeypatch.setattr(keyboards, "InlineKeyboardButton", CapturedButton)
    monkeypatch.setattr(keyboards, "InlineKeyboardMarkup", CapturedMarkup)

    # main's proxy synchronizes classes from main, so patch those too.
    monkeypatch.setattr(main, "InlineKeyboardButton", CapturedButton)
    monkeypatch.setattr(main, "InlineKeyboardMarkup", CapturedMarkup)

    kb = main.build_list_delete_keyboard(
        20,
        page=0,
        total_pages=3,
    )
    data = _callback_data(kb)

    assert "list_page:1" in data
    assert "noop" in data
    assert "list_page:0" not in data
