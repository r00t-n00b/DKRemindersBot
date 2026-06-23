import ast
from pathlib import Path


def _get_top_level_async_function_source(path, function_name):
    source = Path(path).read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name
    ]
    assert len(nodes) == 1

    return source, nodes[0], ast.get_source_segment(source, nodes[0])


def test_main_snooze_callback_is_thin_wrapper_after_9x_refactor():
    _, node, source = _get_top_level_async_function_source("main.py", "snooze_callback")

    assert "handle_reminder_callback(update, context, _build_reminder_callback_deps())" in source
    assert node.end_lineno - node.lineno + 1 <= 3


def test_reminder_callback_router_contains_expected_routes():
    _, _, source = _get_top_level_async_function_source(
        "reminder_callback_router.py",
        "handle_reminder_callback",
    )

    required_router_calls = [
        "handle_pastdate_callback(",
        "handle_self_remind_ask(",
        "handle_self_remind_cancel_personal(",
        "handle_self_remind_back(",
        "handle_self_remind_mode(",
        "handle_self_remind_event_custom(",
        "handle_self_remind_event_before(",
        "handle_self_remind_set(",
        "handle_self_remind_calendar_month(",
        "handle_self_remind_calendar_today(",
        "handle_self_remind_pickdate(",
        "handle_self_remind_picktime(",
        "handle_self_remind_event_cancel_callback(",
        "handle_self_remind_cancel_callback(",
        "handle_done_callback_data(",
        "handle_direct_snooze_action(",
        "show_custom_snooze_calendar(",
        "enter_custom_snooze_time_picker(",
        "handle_custom_snooze_picktime(",
        "handle_snooze_cancel_callback_data(",
        "handle_noop_callback(",
    ]

    for call in required_router_calls:
        assert call in source


def test_reminder_callback_router_does_not_import_main():
    source = Path("reminder_callback_router.py").read_text()

    assert "import main" not in source
    assert "from main import" not in source


def test_reminder_callback_router_does_not_reintroduce_business_logic():
    _, _, source = _get_top_level_async_function_source(
        "reminder_callback_router.py",
        "handle_reminder_callback",
    )

    forbidden_fragments = [
        "target_chat_id = get_user_chat_id_by_user_id",
        "source_chat_title = await get_source_chat_title_for_self_remind",
        "personal_text = format_self_remind_text",
        "new_reminder_id = add_reminder",
        "event_at = extract_event_datetime_from_text",
        "remind_at = compute_event_before_time",
        "remind_at = compute_self_remind_time",
        "year, month, day = map(int",
        "hour, minute = map(int",
        "await context.bot.send_message(",
        "await query.answer(\"Эта дата уже прошла. Выбери другую.\"",
        "await query.answer(\"Личное напоминание создано\")",
        "await query.answer(\"Отправил варианты в личку\")",
        "await query.answer(\"Вернул выбор\")",
    ]

    for fragment in forbidden_fragments:
        assert fragment not in source


def test_reminder_callback_router_size_stays_bounded():
    _, node, _ = _get_top_level_async_function_source(
        "reminder_callback_router.py",
        "handle_reminder_callback",
    )

    assert node.end_lineno - node.lineno + 1 <= 430
