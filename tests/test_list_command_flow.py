import asyncio
from types import SimpleNamespace

import list_command_flow
import main


async def safe_reply(message, text, reply_markup=None):
    message.replies.append((text, reply_markup))


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, query, params):
        self.executed.append((query, params))

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class FakeSqlite3:
    def __init__(self, rows):
        self.rows = rows
        self.connections = []

    def connect(self, path):
        conn = FakeConn(self.rows)
        self.connections.append((path, conn))
        return conn


def make_deps(**overrides):
    fake_sqlite = FakeSqlite3([])

    deps = SimpleNamespace(
        Chat=SimpleNamespace(PRIVATE="private"),
        DB_PATH="/tmp/test.db",
        sqlite3=fake_sqlite,
        build_active_reminders_list_response=lambda rows, header, now_local, list_delete_keyboard_builder: (
            f"{header} {len(rows)}",
            [row[0] for row in rows],
            "keyboard",
        ),
        build_list_delete_keyboard=lambda ids: f"delete:{ids}",
        build_target_user_presentation_rows=lambda rows, recurring_template_loader: rows,
        build_target_user_reminders_list_response=lambda rows, target_label, list_delete_keyboard_builder: (
            f"target {target_label}: {len(rows)}",
            [row[0] for row in rows],
            "target-keyboard",
        ),
        format_empty_active_reminders_list_text=lambda chat_alias=None: f"empty:{chat_alias}",
        get_active_reminders_created_by_for_chat=lambda chat_id, created_by: [],
        get_all_aliases=lambda user_id: [],
        get_chat_id_by_alias_for_user=lambda alias, user_id: None,
        get_now=lambda: "NOW",
        get_private_chat_id_by_username=lambda username: None,
        get_recurring_template=lambda template_id: None,
        get_user_alias_chat_id_for_user=lambda alias, user_id: None,
        safe_reply=safe_reply,
    )
    for key, value in overrides.items():
        setattr(deps, key, value)
    return deps


def make_update_and_context(*, chat_type="private", args=None):
    message = SimpleNamespace(replies=[])
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=100, type=chat_type),
        effective_message=message,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(args=args or [], user_data={})
    return update, context, message


def run_flow(deps, update, context):
    asyncio.run(list_command_flow.handle_list_command_flow(update, context, deps))


def test_main_list_command_delegates_to_flow(monkeypatch):
    calls = []

    async def fake_flow(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_list_command_flow", fake_flow)

    update, context, _ = make_update_and_context()

    asyncio.run(main.list_command(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "build_active_reminders_list_response")


def test_list_username_unknown_replies_and_aborts():
    deps = make_deps()
    update, context, message = make_update_and_context(args=["@bob"])

    run_flow(deps, update, context)

    assert message.replies == [(
        "Пользователь @bob еще не писал боту.\n"
        "Он должен сначала нажать Start или поставить любой ремайндер.",
        None,
    )]
    assert context.user_data == {}


def test_list_username_target_sets_ids_and_owner_chat_id():
    deps = make_deps(
        get_private_chat_id_by_username=lambda username: 555,
        get_active_reminders_created_by_for_chat=lambda chat_id, created_by: [
            (1, "one"),
            (2, "two"),
        ],
    )
    update, context, message = make_update_and_context(args=["@bob"])

    run_flow(deps, update, context)

    assert message.replies == [("target @bob: 2", "target-keyboard")]
    assert context.user_data["list_ids"] == [1, 2]
    assert context.user_data["list_chat_id"] == 555


def test_list_unknown_alias_without_known_aliases_replies():
    deps = make_deps()
    update, context, message = make_update_and_context(args=["team"])

    run_flow(deps, update, context)

    assert message.replies == [(
        "Alias 'team' не найден.\n"
        "Сначала зайди в нужный чат и выполни /linkchat название.\n"
        "Или создай user-alias: /linkuser team @username",
        None,
    )]


def test_list_unknown_alias_with_known_aliases_replies_known_aliases():
    deps = make_deps(get_all_aliases=lambda user_id: [("work", 1, 2), ("home", 3, 4)])
    update, context, message = make_update_and_context(args=["team"])

    run_flow(deps, update, context)

    assert message.replies == [(
        "Alias 'team' не найден.\n"
        "Из известных chat-alias: work, home",
        None,
    )]


def test_list_user_alias_uses_created_by_filter_like_username():
    calls = []

    def get_created_by_rows(chat_id, created_by):
        calls.append((chat_id, created_by))
        return [
            (1, "mine"),
            (2, "also mine"),
        ]

    deps = make_deps(
        get_user_alias_chat_id_for_user=lambda alias, user_id: 777,
        get_active_reminders_created_by_for_chat=get_created_by_rows,
    )
    update, context, message = make_update_and_context(args=["natasha"])

    run_flow(deps, update, context)

    assert calls == [(777, 42)]
    assert message.replies == [("target natasha: 2", "target-keyboard")]
    assert context.user_data["list_ids"] == [1, 2]
    assert context.user_data["list_chat_id"] == 777


def test_list_user_alias_does_not_read_all_reminders_for_target_chat():
    fake_sqlite = FakeSqlite3([
        (999, " чужой reminder", "2026-01-01T10:00:00+00:00", None, None, None),
    ])

    deps = make_deps(
        sqlite3=fake_sqlite,
        get_user_alias_chat_id_for_user=lambda alias, user_id: 777,
        get_active_reminders_created_by_for_chat=lambda chat_id, created_by: [],
    )
    update, context, message = make_update_and_context(args=["natasha"])

    run_flow(deps, update, context)

    assert message.replies == [("target natasha: 0", None)]
    assert context.user_data == {}
    assert fake_sqlite.connections == []


def test_list_chat_alias_reads_active_reminders_and_sets_ids():
    fake_sqlite = FakeSqlite3([
        (10, "text", "2026-01-01T10:00:00+00:00", None, None, None),
        (11, "text2", "2026-01-01T11:00:00+00:00", None, None, None),
    ])
    deps = make_deps(
        sqlite3=fake_sqlite,
        get_chat_id_by_alias_for_user=lambda alias, user_id: -100,
    )
    update, context, message = make_update_and_context(args=["team"])

    run_flow(deps, update, context)

    assert message.replies == [("Активные напоминания для чата 'team': 2", "keyboard")]
    assert context.user_data["list_ids"] == [10, 11]
    assert context.user_data["list_chat_id"] == -100
    assert fake_sqlite.connections[0][0] == "/tmp/test.db"
    assert fake_sqlite.connections[0][1].closed is True
    assert fake_sqlite.connections[0][1].cursor_obj.executed[0][1] == (-100,)


def test_list_default_chat_reads_active_reminders_and_sets_ids():
    fake_sqlite = FakeSqlite3([
        (10, "text", "2026-01-01T10:00:00+00:00", None, None, None),
    ])
    deps = make_deps(sqlite3=fake_sqlite)
    update, context, message = make_update_and_context(chat_type="group")

    run_flow(deps, update, context)

    assert message.replies == [("Активные напоминания: 1", "keyboard")]
    assert context.user_data["list_ids"] == [10]
    assert context.user_data["list_chat_id"] == 100


def test_list_command_wrapper_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    node = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_command"
    ][0]

    wrapper_source = ast.get_source_segment(source, node)

    assert "handle_list_command_flow(update, context, _build_list_command_deps())" in wrapper_source
    assert node.end_lineno - node.lineno + 1 <= 3


def test_list_command_flow_contains_expected_routes():
    import ast
    from pathlib import Path

    source = Path("list_command_flow.py").read_text()
    tree = ast.parse(source)

    node = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_list_command_flow"
    ][0]

    flow_source = ast.get_source_segment(source, node)

    assert "get_private_chat_id_by_username(" in flow_source
    assert "get_user_alias_chat_id_for_user(" in flow_source
    assert "get_chat_id_by_alias_for_user(" in flow_source
    assert "build_active_reminders_list_response(" in flow_source
