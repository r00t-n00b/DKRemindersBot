import asyncio
from types import SimpleNamespace

import created_action_callbacks
import main


def test_created_action_wrappers_delegate_to_flow(monkeypatch):
    async def fake_answer(query, deps):
        fake_answer.calls.append((query, deps))
    fake_answer.calls = []

    async def fake_ensure(query, reminder_id, deps):
        fake_ensure.calls.append((query, reminder_id, deps))
        return True
    fake_ensure.calls = []

    async def fake_reschedule(update, context, deps):
        fake_reschedule.calls.append((update, context, deps))
    fake_reschedule.calls = []

    async def fake_custom(update, context, deps):
        fake_custom.calls.append((update, context, deps))
    fake_custom.calls = []

    async def fake_cancel(update, context, deps):
        fake_cancel.calls.append((update, context, deps))
    fake_cancel.calls = []

    async def fake_back(update, context, deps):
        fake_back.calls.append((update, context, deps))
    fake_back.calls = []

    monkeypatch.setattr(main, "answer_created_action_reminder_missing_impl", fake_answer)
    monkeypatch.setattr(main, "ensure_created_action_reminder_exists_impl", fake_ensure)
    monkeypatch.setattr(main, "handle_created_reschedule_callback", fake_reschedule)
    monkeypatch.setattr(main, "handle_created_snooze_custom_callback", fake_custom)
    monkeypatch.setattr(main, "handle_created_snooze_cancel_callback", fake_cancel)
    monkeypatch.setattr(main, "handle_created_back_callback", fake_back)

    query = SimpleNamespace()
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()

    assert asyncio.run(main._ensure_created_action_reminder_exists(query, 123)) is True
    asyncio.run(main._answer_created_action_reminder_missing(query))
    asyncio.run(main.created_reschedule_callback(update, context))
    asyncio.run(main.created_snooze_custom_callback(update, context))
    asyncio.run(main.created_snooze_cancel_callback(update, context))
    asyncio.run(main.created_back_callback(update, context))

    assert fake_ensure.calls[0][0] is query
    assert fake_ensure.calls[0][1] == 123
    assert fake_answer.calls[0][0] is query
    assert fake_reschedule.calls[0][:2] == (update, context)
    assert fake_custom.calls[0][:2] == (update, context)
    assert fake_cancel.calls[0][:2] == (update, context)
    assert fake_back.calls[0][:2] == (update, context)


def test_created_action_wrappers_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    expected = {
        "_answer_created_action_reminder_missing": "answer_created_action_reminder_missing_impl",
        "_ensure_created_action_reminder_exists": "ensure_created_action_reminder_exists_impl",
        "created_reschedule_callback": "handle_created_reschedule_callback",
        "created_snooze_custom_callback": "handle_created_snooze_custom_callback",
        "created_snooze_cancel_callback": "handle_created_snooze_cancel_callback",
        "created_back_callback": "handle_created_back_callback",
    }

    for name, delegate in expected.items():
        matches = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]

        assert len(matches) == 1

        node = matches[0]
        node_source = ast.get_source_segment(source, node)

        assert delegate in node_source
        assert node.end_lineno - node.lineno + 1 <= 3


def test_created_action_callbacks_module_contains_expected_paths_and_no_main_import():
    source = open("created_action_callbacks.py").read()

    assert "async def answer_created_action_reminder_missing_impl(" in source
    assert "async def ensure_created_action_reminder_exists_impl(" in source
    assert "async def handle_created_reschedule_callback(" in source
    assert "async def handle_created_snooze_custom_callback(" in source
    assert "async def handle_created_snooze_cancel_callback(" in source
    assert "async def handle_created_back_callback(" in source

    assert "MSG_RESCHEDULE_OPEN_FAILED_TEXT" in source
    assert 'callback_prefix="created_snooze"' in source
    assert "build_created_reminder_actions_keyboard_for_reminder" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_created_action_missing_helper_clears_keyboard_for_missing_reminder():
    calls = []

    class Query:
        async def answer(self, text, show_alert=False):
            calls.append(("answer", text, show_alert))

        async def edit_message_reply_markup(self, reply_markup=None):
            calls.append(("edit_markup", reply_markup))

    deps = SimpleNamespace(
        MSG_INVALID_REMINDER_ID="bad-id",
        MSG_REMINDER_NOT_FOUND="not-found",
        MSG_RESCHEDULE_OPEN_FAILED_TEXT="open-failed",
        build_created_reminder_actions_keyboard_for_reminder=lambda reminder_id: "actions",
        build_created_reschedule_keyboard=lambda reminder_id: "reschedule",
        build_custom_date_keyboard=lambda reminder_id, callback_prefix: "date-keyboard",
        get_reminder=lambda reminder_id: None,
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        answer_created_action_reminder_missing=None,
        ensure_created_action_reminder_exists=None,
    )

    asyncio.run(created_action_callbacks.answer_created_action_reminder_missing_impl(Query(), deps))

    assert calls == [
        ("answer", "not-found", True),
        ("edit_markup", None),
    ]


def test_created_action_ensure_uses_get_reminder_and_missing_answer():
    calls = []

    async def answer_missing(query):
        calls.append(("missing", query))

    deps = SimpleNamespace(
        MSG_INVALID_REMINDER_ID="bad-id",
        MSG_REMINDER_NOT_FOUND="not-found",
        MSG_RESCHEDULE_OPEN_FAILED_TEXT="open-failed",
        build_created_reminder_actions_keyboard_for_reminder=lambda reminder_id: "actions",
        build_created_reschedule_keyboard=lambda reminder_id: "reschedule",
        build_custom_date_keyboard=lambda reminder_id, callback_prefix: "date-keyboard",
        get_reminder=lambda reminder_id: None,
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        answer_created_action_reminder_missing=answer_missing,
        ensure_created_action_reminder_exists=None,
    )

    query = object()

    result = asyncio.run(
        created_action_callbacks.ensure_created_action_reminder_exists_impl(
            query,
            777,
            deps,
        )
    )

    assert result is False
    assert calls == [("missing", query)]


def test_created_action_module_exports_handlers():
    assert hasattr(created_action_callbacks, "handle_created_reschedule_callback")
    assert hasattr(created_action_callbacks, "handle_created_snooze_custom_callback")
    assert hasattr(created_action_callbacks, "handle_created_snooze_cancel_callback")
    assert hasattr(created_action_callbacks, "handle_created_back_callback")
