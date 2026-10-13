import asyncio
from types import SimpleNamespace

import dkreminders_bot.callbacks.delete_undo_router as delete_undo_router
import main


def test_main_delete_callback_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_delete_callback", fake_router)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="del:1"))
    context = SimpleNamespace(user_data={})

    asyncio.run(main.delete_callback(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "delete_single_reminder_with_snapshot")
    assert hasattr(calls[0][2], "build_recurring_delete_choice_keyboard")


def test_main_delete_choose_callback_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_delete_choose_callback", fake_router)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="del_cancel:1"))
    context = SimpleNamespace(user_data={})

    asyncio.run(main.delete_choose_callback(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "delete_recurring_series_with_snapshot")
    assert hasattr(calls[0][2], "delete_recurring_one_instance_and_reschedule")


def test_main_undo_callback_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_undo_callback", fake_router)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="undo:abc"))
    context = SimpleNamespace(user_data={})

    asyncio.run(main.undo_callback(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "restore_deleted_snapshot")
    assert hasattr(calls[0][2], "format_restored_single_text")


def test_delete_undo_router_module_exposes_handlers():
    assert hasattr(delete_undo_router, "handle_delete_callback")
    assert hasattr(delete_undo_router, "handle_delete_choose_callback")
    assert hasattr(delete_undo_router, "handle_undo_callback")


def test_delete_undo_callback_wrappers_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    expected = {
        "delete_callback": "handle_delete_callback(update, context, _build_delete_undo_callback_deps())",
        "delete_choose_callback": "handle_delete_choose_callback(update, context, _build_delete_undo_callback_deps())",
        "undo_callback": "handle_undo_callback(update, context, _build_delete_undo_callback_deps())",
    }

    for name, call in expected.items():
        node = [
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == name
        ][0]

        wrapper_source = ast.get_source_segment(source, node)

        assert call in wrapper_source
        assert node.end_lineno - node.lineno + 1 <= 3


def test_delete_undo_router_contains_expected_routes():
    import ast
    from pathlib import Path

    source = Path("dkreminders_bot/callbacks/delete_undo_router.py").read_text()
    tree = ast.parse(source)

    handlers = {
        node.name: ast.get_source_segment(source, node)
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    }

    assert 'data.startswith("del:")' in handlers["handle_delete_callback"]
    assert 'data.startswith("del_cancel:")' in handlers["handle_delete_choose_callback"]
    assert 'data.startswith("del_one:")' in handlers["handle_delete_choose_callback"]
    assert 'data.startswith("del_series:")' in handlers["handle_delete_choose_callback"]
    assert 'data.startswith("undo:")' in handlers["handle_undo_callback"]


def test_delete_undo_router_does_not_import_main():
    source = open("dkreminders_bot/callbacks/delete_undo_router.py").read()

    assert "import main" not in source
    assert "from main import" not in source


def test_paginated_refresh_refills_page_after_delete(tmp_path, monkeypatch):
    import sqlite3
    from datetime import datetime
    from dkreminders_bot.ui.presentation import build_active_reminders_list_response

    db = tmp_path / "reminders.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE recurring_templates (
            id INTEGER PRIMARY KEY,
            pattern_type TEXT,
            payload TEXT,
            timezone_name TEXT
        );
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            text TEXT,
            remind_at TEXT,
            template_id INTEGER,
            delivered INTEGER DEFAULT 0,
            timezone_name TEXT
        );
    """)

    for idx in range(1, 42):
        conn.execute(
            """
            INSERT INTO reminders
                (id, chat_id, text, remind_at, delivered, timezone_name)
            VALUES (?, 100, ?, ?, 0, 'Europe/Madrid')
            """,
            (
                idx,
                f"reminder {idx}",
                f"2026-11-{((idx - 1) % 28) + 1:02d}T10:00:00+01:00",
            ),
        )
    conn.commit()
    conn.close()

    # Simulate reminder #1 already deleted.
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM reminders WHERE id = 1")
    conn.commit()
    conn.close()

    class Button:
        def __init__(self, text, callback_data=None, **kwargs):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    monkeypatch.setattr(delete_undo_router, "sqlite3", sqlite3)

    def keyboard(count, *, page=0, total_pages=1):
        rows = []
        for idx in range(1, count + 1):
            rows.append([Button(f"❌{idx}", f"del:{idx}")])
        if total_pages > 1:
            nav = []
            if page > 0:
                nav.append(Button("◀️", f"list_page:{page - 1}"))
            nav.append(Button(f"{page + 1}/{total_pages}", "noop"))
            if page < total_pages - 1:
                nav.append(Button("▶️", f"list_page:{page + 1}"))
            rows.append(nav)
        return Markup(rows)

    deps = SimpleNamespace(
        DB_PATH=str(db),
        sqlite3=sqlite3,
        build_active_reminders_list_response=build_active_reminders_list_response,
        build_list_delete_keyboard=keyboard,
        get_now=lambda: datetime.fromisoformat("2026-10-13T10:00:00+02:00"),
    )

    # _apply_deps expects the complete router dependency contract.
    for name in delete_undo_router._DEP_NAMES:
        if not hasattr(deps, name):
            setattr(deps, name, getattr(delete_undo_router, name, None))

    context = SimpleNamespace(
        user_data={
            "list_all_ids": list(range(1, 42)),
            "list_ids": list(range(1, 21)),
            "list_page": 0,
            "list_page_size": 20,
            "list_chat_id": 100,
            "list_alias": None,
        }
    )

    reply, keyboard_result, ids = delete_undo_router._refresh_paginated_list_state(
        context,
        deps,
    )

    assert len(context.user_data["list_all_ids"]) == 40
    assert 1 not in context.user_data["list_all_ids"]
    assert len(ids) == 20
    assert context.user_data["list_page"] == 0
    assert "Страница 1/2 · всего 40." in reply

    callbacks = [
        button.callback_data
        for row in keyboard_result.inline_keyboard
        for button in row
    ]
    assert "list_page:1" in callbacks


def test_paginated_refresh_clamps_disappearing_last_page(tmp_path, monkeypatch):
    import sqlite3
    from datetime import datetime
    from dkreminders_bot.ui.presentation import build_active_reminders_list_response

    db = tmp_path / "reminders.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE recurring_templates (
            id INTEGER PRIMARY KEY,
            pattern_type TEXT,
            payload TEXT,
            timezone_name TEXT
        );
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            text TEXT,
            remind_at TEXT,
            template_id INTEGER,
            delivered INTEGER DEFAULT 0,
            timezone_name TEXT
        );
    """)

    for idx in range(1, 41):
        conn.execute(
            """
            INSERT INTO reminders
                (id, chat_id, text, remind_at, delivered, timezone_name)
            VALUES (?, 100, ?, ?, 0, 'Europe/Madrid')
            """,
            (
                idx,
                f"reminder {idx}",
                f"2026-11-{((idx - 1) % 28) + 1:02d}T10:00:00+01:00",
            ),
        )
    conn.commit()
    conn.close()

    monkeypatch.setattr(delete_undo_router, "sqlite3", sqlite3)

    def keyboard(count, *, page=0, total_pages=1):
        return (count, page, total_pages)

    deps = SimpleNamespace(
        DB_PATH=str(db),
        sqlite3=sqlite3,
        build_active_reminders_list_response=build_active_reminders_list_response,
        build_list_delete_keyboard=keyboard,
        get_now=lambda: datetime.fromisoformat("2026-10-13T10:00:00+02:00"),
    )

    for name in delete_undo_router._DEP_NAMES:
        if not hasattr(deps, name):
            setattr(deps, name, getattr(delete_undo_router, name, None))

    context = SimpleNamespace(
        user_data={
            "list_all_ids": list(range(1, 42)),
            "list_ids": [41],
            "list_page": 2,
            "list_page_size": 20,
            "list_chat_id": 100,
            "list_alias": None,
        }
    )

    reply, keyboard_result, ids = delete_undo_router._refresh_paginated_list_state(
        context,
        deps,
    )

    assert context.user_data["list_page"] == 1
    assert len(context.user_data["list_all_ids"]) == 40
    assert len(ids) == 20
    assert keyboard_result == (20, 1, 2)
    assert "Страница 2/2 · всего 40." in reply


class _DeleteTestChat:
    def __init__(self, chat_id=100):
        self.id = chat_id


class _DeleteTestMessage:
    def __init__(self, chat_id=100, message_id=500):
        self.chat = _DeleteTestChat(chat_id)
        self.message_id = message_id
        self.replies = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append((text, reply_markup))


class _DeleteTestQuery:
    def __init__(self, data, chat_id=100):
        self.data = data
        self.message = _DeleteTestMessage(chat_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


def _complete_delete_router_deps(**overrides):
    deps = SimpleNamespace()

    for name in delete_undo_router._DEP_NAMES:
        setattr(deps, name, getattr(delete_undo_router, name, None))

    for name, value in overrides.items():
        setattr(deps, name, value)

    return deps


def test_real_oneoff_delete_uses_paginated_refresh(monkeypatch):
    refresh_calls = []

    def fake_refresh(context, deps):
        refresh_calls.append(list(context.user_data.get("list_ids") or []))
        context.user_data["list_all_ids"] = list(range(2, 42))
        context.user_data["list_ids"] = list(range(2, 22))
        return "REFRESHED PAGE", "PAGE KEYBOARD", list(range(2, 22))

    monkeypatch.setattr(
        delete_undo_router,
        "_refresh_paginated_list_state",
        fake_refresh,
    )

    snapshot = {
        "reminder": {
            "id": 1,
            "remind_at": "2026-11-01T10:00:00+01:00",
            "text": "first reminder",
        },
        "template": None,
    }

    deps = _complete_delete_router_deps(
        get_reminder_row=lambda rid: {
            "id": rid,
            "template_id": None,
        },
        delete_single_reminder_with_snapshot=lambda rid, chat_id: snapshot,
        format_deleted_human=lambda *args, **kwargs: "deleted reminder",
        make_undo_token=lambda: "token",
        InlineKeyboardButton=lambda text, callback_data=None: (text, callback_data),
        InlineKeyboardMarkup=lambda rows: rows,
        cb_undo=lambda token: f"undo:{token}",
        msg_created_deleted=lambda text: f"deleted: {text}",
    )

    query = _DeleteTestQuery("del:1")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={
            "list_all_ids": list(range(1, 42)),
            "list_ids": list(range(1, 21)),
            "list_page": 0,
            "list_page_size": 20,
            "list_chat_id": 100,
            "list_alias": None,
        }
    )

    asyncio.run(
        delete_undo_router.handle_delete_callback(
            update,
            context,
            deps,
        )
    )

    assert len(refresh_calls) == 1
    assert query.edits == [("REFRESHED PAGE", "PAGE KEYBOARD")]
    assert context.user_data["list_ids"] == list(range(2, 22))
    assert context.user_data["list_all_ids"] == list(range(2, 42))


def test_real_recurring_delete_one_refreshes_stored_paginated_list(monkeypatch):
    refresh_calls = []

    def fake_refresh(context, deps):
        refresh_calls.append(True)
        context.user_data["list_all_ids"] = list(range(2, 42))
        context.user_data["list_ids"] = list(range(2, 22))
        return "REFRESHED RECURRING PAGE", "PAGE KEYBOARD", list(range(2, 22))

    monkeypatch.setattr(
        delete_undo_router,
        "_refresh_paginated_list_state",
        fake_refresh,
    )

    snapshot = {
        "kind": "single",
        "reminder": {
            "id": 1,
            "remind_at": "2026-11-01T10:00:00+01:00",
            "text": "recurring reminder",
        },
        "template": {
            "id": 7,
            "pattern_type": "daily",
            "payload": {},
        },
    }

    deps = _complete_delete_router_deps(
        delete_recurring_one_instance_and_reschedule=lambda rid, chat_id: snapshot,
        format_deleted_human=lambda *args, **kwargs: "deleted recurring reminder",
        make_undo_token=lambda: "token",
        InlineKeyboardButton=lambda text, callback_data=None: (text, callback_data),
        InlineKeyboardMarkup=lambda rows: rows,
        cb_undo=lambda token: f"undo:{token}",
        format_deleted_snapshot_text=lambda label, text: f"{label}: {text}",
    )

    query = _DeleteTestQuery("del_one:1")
    update = SimpleNamespace(callback_query=query)

    bot_edits = []

    async def edit_message_text(**kwargs):
        bot_edits.append(kwargs)

    context = SimpleNamespace(
        user_data={
            "list_all_ids": list(range(1, 42)),
            "list_ids": list(range(1, 21)),
            "list_page": 0,
            "list_page_size": 20,
            "list_chat_id": 100,
            "list_alias": None,
            "delete_choice_source": "list",
            "list_message_ref": {
                "chat_id": 100,
                "message_id": 500,
            },
        },
        bot=SimpleNamespace(edit_message_text=edit_message_text),
    )

    asyncio.run(
        delete_undo_router.handle_delete_choose_callback(
            update,
            context,
            deps,
        )
    )

    assert len(refresh_calls) == 1
    assert bot_edits == [
        {
            "chat_id": 100,
            "message_id": 500,
            "text": "REFRESHED RECURRING PAGE",
            "reply_markup": "PAGE KEYBOARD",
        }
    ]
    assert context.user_data["list_ids"] == list(range(2, 22))


def test_real_recurring_delete_series_refreshes_stored_paginated_list(monkeypatch):
    refresh_calls = []

    def fake_refresh(context, deps):
        refresh_calls.append(True)
        context.user_data["list_all_ids"] = list(range(5, 42))
        context.user_data["list_ids"] = list(range(5, 25))
        return "REFRESHED SERIES PAGE", "SERIES KEYBOARD", list(range(5, 25))

    monkeypatch.setattr(
        delete_undo_router,
        "_refresh_paginated_list_state",
        fake_refresh,
    )

    snapshot = {
        "kind": "series",
        "reminders": [
            {
                "id": 1,
                "remind_at": "2026-11-01T10:00:00+01:00",
                "text": "series reminder",
            },
            {
                "id": 2,
                "remind_at": "2026-11-02T10:00:00+01:00",
                "text": "series reminder",
            },
        ],
        "template": {
            "id": 7,
            "text": "series reminder",
            "pattern_type": "daily",
            "payload": {},
        },
    }

    deps = _complete_delete_router_deps(
        delete_recurring_series_with_snapshot=lambda tpl_id, chat_id: snapshot,
        format_deleted_human=lambda *args, **kwargs: "deleted series",
        make_undo_token=lambda: "token",
        InlineKeyboardButton=lambda text, callback_data=None: (text, callback_data),
        InlineKeyboardMarkup=lambda rows: rows,
        cb_undo=lambda token: f"undo:{token}",
        format_deleted_snapshot_text=lambda label, text: f"{label}: {text}",
    )

    query = _DeleteTestQuery("del_series:7")
    update = SimpleNamespace(callback_query=query)

    bot_edits = []

    async def edit_message_text(**kwargs):
        bot_edits.append(kwargs)

    context = SimpleNamespace(
        user_data={
            "list_all_ids": list(range(1, 42)),
            "list_ids": list(range(1, 21)),
            "list_page": 0,
            "list_page_size": 20,
            "list_chat_id": 100,
            "list_alias": None,
            "delete_choice_source": "list",
            "list_message_ref": {
                "chat_id": 100,
                "message_id": 500,
            },
        },
        bot=SimpleNamespace(edit_message_text=edit_message_text),
    )

    asyncio.run(
        delete_undo_router.handle_delete_choose_callback(
            update,
            context,
            deps,
        )
    )

    assert len(refresh_calls) == 1
    assert bot_edits == [
        {
            "chat_id": 100,
            "message_id": 500,
            "text": "REFRESHED SERIES PAGE",
            "reply_markup": "SERIES KEYBOARD",
        }
    ]
    assert context.user_data["list_ids"] == list(range(5, 25))
