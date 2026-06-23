import pytest

import main
from callback_data_parsing import parse_optional_int_callback_id, parse_snooze_action_callback_data


def test_parse_optional_int_callback_id_returns_int_for_valid_id():
    assert parse_optional_int_callback_id("done:123", prefix="done:") == 123


def test_parse_optional_int_callback_id_returns_none_for_invalid_id():
    assert parse_optional_int_callback_id("done:not-an-int", prefix="done:") is None


def test_parse_optional_int_callback_id_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        parse_optional_int_callback_id("snooze:123", prefix="done:")



def test_parse_snooze_action_callback_data_returns_id_and_action():
    assert parse_snooze_action_callback_data("snooze:123:1h") == (123, "1h")


def test_parse_snooze_action_callback_data_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        parse_snooze_action_callback_data("done:123")


def test_parse_snooze_action_callback_data_rejects_invalid_id():
    with pytest.raises(ValueError):
        parse_snooze_action_callback_data("snooze:not-int:1h")


def test_snooze_action_uses_callback_parser():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "snooze_callback"
    ]
    assert len(nodes) == 1

    snooze_source = ast.get_source_segment(source, nodes[0])

    assert "parse_snooze_action_callback_data" in source

    direct_start = snooze_source.index('if data.startswith("snooze:"):')
    cal_start = snooze_source.index('if data.startswith("snooze_cal:"):', direct_start)
    direct_source = snooze_source[direct_start:cal_start]

    assert "parse_snooze_action_callback_data(data)" in direct_source
    assert '_, rid_str, action = data.split(":", 2)' not in direct_source
    assert "rid = int(rid_str)" not in direct_source

def test_snooze_callback_uses_done_callback_id_parser():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "snooze_callback"
    ]
    assert len(nodes) == 1

    snooze_source = ast.get_source_segment(source, nodes[0])

    assert "from callback_data_parsing import parse_optional_int_callback_id" in source

    done_start = snooze_source.index('if data.startswith("done:"):')
    snooze_start = snooze_source.index('if data.startswith("snooze:"):', done_start)
    done_source = snooze_source[done_start:snooze_start]

    assert 'parse_optional_int_callback_id(data, prefix="done:")' in done_source
    assert "_, rid_str = data.split" not in done_source
    assert "rid = int(rid_str)" not in done_source



def test_snooze_cancel_uses_callback_id_parser():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "snooze_callback"
    ]
    assert len(nodes) == 1

    snooze_source = ast.get_source_segment(source, nodes[0])

    cancel_start = snooze_source.index('if data.startswith("snooze_cancel:"):')
    noop_start = snooze_source.index('if data == "noop":', cancel_start)
    cancel_source = snooze_source[cancel_start:noop_start]

    assert 'parse_optional_int_callback_id(data, prefix="snooze_cancel:")' in cancel_source
    assert "_, rid_str = data.split" not in cancel_source
    assert "rid = int(rid_str)" not in cancel_source

def test_main_reexports_callback_id_parser():
    assert main.parse_optional_int_callback_id is parse_optional_int_callback_id
