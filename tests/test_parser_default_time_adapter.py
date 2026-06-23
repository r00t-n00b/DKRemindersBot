import ast
from pathlib import Path

import pytest

import main
from parser_default_time_adapter import parse_with_optional_default_time


def test_parse_adapter_uses_default_time_when_supported():
    calls = []

    def parser(raw, now, *, default_time=None):
        calls.append((raw, now, default_time))
        return "ok"

    assert (
        parse_with_optional_default_time(
            parser,
            "tomorrow - test",
            "now",
            default_time=(9, 30),
        )
        == "ok"
    )
    assert calls == [("tomorrow - test", "now", (9, 30))]


def test_parse_adapter_falls_back_for_old_parser_signature():
    calls = []

    def parser(raw, now):
        calls.append((raw, now))
        return "legacy-ok"

    assert (
        parse_with_optional_default_time(
            parser,
            "tomorrow - test",
            "now",
            default_time=(9, 30),
        )
        == "legacy-ok"
    )
    assert calls == [("tomorrow - test", "now")]


def test_parse_adapter_reraises_unrelated_type_error():
    def parser(raw, now, *, default_time=None):
        raise TypeError("real parser bug")

    with pytest.raises(TypeError, match="real parser bug"):
        parse_with_optional_default_time(
            parser,
            "tomorrow - test",
            "now",
            default_time=(9, 30),
        )


def test_remind_command_uses_default_parser_adapter_without_nested_helpers():
    source = Path("main.py").read_text()
    tree = ast.parse(source)

    remind_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remind_command"
    ]
    assert len(remind_nodes) == 1

    nested_names = [
        node.name
        for node in remind_nodes[0].body
        if isinstance(node, ast.FunctionDef)
    ]

    assert "parse_date_time_smart_with_default" not in nested_names
    assert "parse_recurring_with_default" not in nested_names
    assert "from parser_default_time_adapter import parse_with_optional_default_time" in source
    assert source.count("parse_with_optional_default_time(") >= 2


def test_main_reexports_default_parser_adapter_helper():
    assert main.parse_with_optional_default_time is parse_with_optional_default_time


def test_remind_command_has_no_old_default_parser_helper_references():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    remind_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remind_command"
    ]
    assert len(remind_nodes) == 1

    remind_source = ast.get_source_segment(source, remind_nodes[0])
    assert "parse_date_time_smart_with_default(" not in remind_source
    assert "parse_recurring_with_default(" not in remind_source


def test_bulk_create_single_reminder_has_no_old_default_parser_helper_references():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    func_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_create_single_reminder_from_line"
    ]
    assert len(func_nodes) == 1

    func_source = ast.get_source_segment(source, func_nodes[0])
    assert "parse_date_time_smart_with_default(" not in func_source
    assert "parse_recurring_with_default(" not in func_source
    assert "parse_with_optional_default_time(" in func_source
