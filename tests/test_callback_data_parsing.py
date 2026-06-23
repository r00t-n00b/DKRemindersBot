import pytest

import main
from callback_data_parsing import parse_optional_int_callback_id


def test_parse_optional_int_callback_id_returns_int_for_valid_id():
    assert parse_optional_int_callback_id("done:123", prefix="done:") == 123


def test_parse_optional_int_callback_id_returns_none_for_invalid_id():
    assert parse_optional_int_callback_id("done:not-an-int", prefix="done:") is None


def test_parse_optional_int_callback_id_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        parse_optional_int_callback_id("snooze:123", prefix="done:")


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
