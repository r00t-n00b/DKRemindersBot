import ast
from pathlib import Path


def _get_function_source(function_name):
    source = Path("main.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name
    ]
    assert len(nodes) == 1

    return source, nodes[0], ast.get_source_segment(source, nodes[0])


def test_snooze_callback_is_router_after_9x_refactor():
    _, _, source = _get_function_source("snooze_callback")

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


def test_snooze_callback_does_not_reintroduce_business_logic():
    _, _, source = _get_function_source("snooze_callback")

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


def test_snooze_callback_size_stays_bounded():
    _, node, _ = _get_function_source("snooze_callback")

    # Current post-9.x size is about 332 lines.
    # This guard allows small routing changes but prevents the function from growing back.
    assert node.end_lineno - node.lineno + 1 <= 360
