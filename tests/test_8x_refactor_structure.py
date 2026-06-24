
import ast

from pathlib import Path

def _source():

    return Path("main.py").read_text()

def _top_level_function(name):

    tree = ast.parse(_source())

    matches = [

        node

        for node in tree.body

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name

    ]

    assert len(matches) == 1

    return matches[0]

def test_8x_helper_imports_are_present():

    source = _source()

    assert "from bulk_header_detection import drop_optional_bulk_header" in source

    assert "from bulk_single_reminder import create_single_reminder_from_line" in source

    assert "from parser_default_time_adapter import parse_with_optional_default_time" in source

    assert "from remind_arg_utils import strip_first_token_from_first_line" in source

    assert "from remind_group_routing import reject_group_remind_target_prefix_if_needed" in source

    assert "from single_oneoff_reminder import handle_single_oneoff_reminder" in source

    assert "from single_recurring_reminder import try_handle_single_recurring_reminder" in source

def test_remind_command_delegates_extracted_flows():

    source = _source()

    remind = _top_level_function("remind_command")

    remind_source = ast.get_source_segment(source, remind)

    dispatch_source = Path("remind_dispatch.py").read_text()

    assert "reject_group_remind_target_prefix_if_needed(" in remind_source
    assert "dispatch_remind_creation(" in remind_source

    assert "try_handle_single_recurring_reminder(" in dispatch_source

    assert "handle_single_oneoff_reminder(" in dispatch_source

    assert "drop_optional_bulk_header(" in dispatch_source

def test_remind_command_no_longer_contains_extracted_business_logic():

    source = _source()

    remind = _top_level_function("remind_command")

    remind_source = ast.get_source_segment(source, remind)

    assert "def parse_date_time_smart_with_default(" not in remind_source

    assert "def parse_recurring_with_default(" not in remind_source

    assert "normalize_plain_text_reminder_with_gemini(raw_single, created_by)" not in remind_source

    assert "if looks_like_recurring(raw_single):" not in remind_source

    assert "# В group-чате запрещаем" not in remind_source

    assert "Создан recurring reminder id=" not in remind_source

    assert "Создан reminder id=%s chat_id=%s at=%s text=%s" not in remind_source

def test_bulk_single_wrapper_delegates_to_extracted_module():

    source = _source()

    func = _top_level_function("_create_single_reminder_from_line")

    func_source = ast.get_source_segment(source, func)

    assert "create_single_reminder_from_line(" in func_source

    assert "Создан bulk recurring reminder" not in func_source

    assert "Создан bulk reminder id=" not in func_source

def test_main_has_no_excessive_blank_line_runs():

    source = _source()

    assert "\n\n\n\n" not in source

