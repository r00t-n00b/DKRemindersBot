import pytest

import main
from callback_data_parsing import parse_optional_int_callback_id, parse_snooze_action_callback_data, parse_snooze_calendar_callback_data, parse_snooze_pickdate_callback_data, parse_snooze_picktime_callback_data, parse_required_int_callback_id



def test_parse_required_int_callback_id_returns_int_for_valid_id():
    assert parse_required_int_callback_id("snooze_caltoday:123", prefix="snooze_caltoday:") == 123


def test_parse_required_int_callback_id_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        parse_required_int_callback_id("done:123", prefix="snooze_caltoday:")


def test_parse_required_int_callback_id_rejects_invalid_id():
    with pytest.raises(ValueError):
        parse_required_int_callback_id("snooze_caltoday:not-int", prefix="snooze_caltoday:")





def test_selfremind_caltoday_uses_required_id_parser():
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

    calendar_source = Path("self_remind_calendar_flow.py").read_text()

    today_start = snooze_source.index('if data.startswith("selfremind_caltoday:") or data.startswith("selfremind_event_caltoday:"):')
    pickdate_start = snooze_source.index('if data.startswith("selfremind_pickdate:") or data.startswith("selfremind_event_pickdate:"):', today_start)
    today_source = snooze_source[today_start:pickdate_start]

    assert "parse_required_int_callback_id=parse_required_int_callback_id" in today_source
    assert 'parse_required_int_callback_id(\n        data,\n        prefix=f"{callback_prefix}_caltoday:",' in calendar_source
    assert '_, rid_str = data.split(":", 1)' not in today_source
    assert "rid = int(rid_str)" not in today_source

def test_selfremind_event_cancel_uses_required_id_parser():
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

    event_cancel_start = snooze_source.index('if data.startswith("selfremind_event_cancel:"):')
    cancel_start = snooze_source.index('if data.startswith("selfremind_cancel:"):', event_cancel_start)
    event_cancel_source = snooze_source[event_cancel_start:cancel_start]

    assert "handle_self_remind_event_cancel_callback(" in event_cancel_source
    assert "parse_required_int_callback_id=parse_required_int_callback_id" in event_cancel_source
    assert '_, rid_str = data.split(":", 1)' not in event_cancel_source
    assert "rid = int(rid_str)" not in event_cancel_source
    simple_flows_source = Path("callback_simple_flows.py").read_text()
    assert "await query.answer(msg_invalid_reminder_id, show_alert=True)" in simple_flows_source

def test_selfremind_cancel_uses_required_id_parser():
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

    cancel_start = snooze_source.index('if data.startswith("selfremind_cancel:"):')
    done_start = snooze_source.index('if data.startswith("done:"):', cancel_start)
    cancel_source = snooze_source[cancel_start:done_start]

    assert "handle_self_remind_cancel_callback(" in cancel_source
    assert "parse_required_int_callback_id=parse_required_int_callback_id" in cancel_source
    assert '_, rid_str = data.split(":", 1)' not in cancel_source
    assert "rid = int(rid_str)" not in cancel_source
    simple_flows_source = Path("callback_simple_flows.py").read_text()
    assert "await query.answer(msg_invalid_reminder_id, show_alert=True)" in simple_flows_source

def test_snooze_caltoday_uses_required_id_parser():
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

    assert "parse_required_int_callback_id" in source

    today_start = snooze_source.index('if data.startswith("snooze_caltoday:"):')
    pickdate_start = snooze_source.index('if data.startswith("snooze_pickdate:"):', today_start)
    today_source = snooze_source[today_start:pickdate_start]

    assert "handle_snooze_current_month_callback(" in today_source
    assert "parse_required_int_callback_id=parse_required_int_callback_id" in today_source
    assert '_, rid_str = data.split(":", 1)' not in today_source
    assert "rid = int(rid_str)" not in today_source

def test_parse_optional_int_callback_id_returns_int_for_valid_id():
    assert parse_optional_int_callback_id("done:123", prefix="done:") == 123


def test_parse_optional_int_callback_id_returns_none_for_invalid_id():
    assert parse_optional_int_callback_id("done:not-an-int", prefix="done:") is None


def test_parse_optional_int_callback_id_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        parse_optional_int_callback_id("snooze:123", prefix="done:")






def test_parse_snooze_picktime_callback_data_returns_id_date_and_time():
    assert parse_snooze_picktime_callback_data("snooze_picktime:123:2026-07-15:10:30") == (
        123,
        "2026-07-15",
        "10:30",
    )


def test_parse_snooze_picktime_callback_data_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        parse_snooze_picktime_callback_data("snooze_pickdate:123:2026-07-15")


def test_parse_snooze_picktime_callback_data_rejects_invalid_id_or_missing_time():
    with pytest.raises(ValueError):
        parse_snooze_picktime_callback_data("snooze_picktime:not-int:2026-07-15:10:30")

    with pytest.raises(ValueError):
        parse_snooze_picktime_callback_data("snooze_picktime:123:2026-07-15")


def test_snooze_picktime_uses_callback_parser():
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

    assert "parse_snooze_picktime_callback_data" in source

    picktime_start = snooze_source.index('if data.startswith("snooze_picktime:"):')
    cancel_start = snooze_source.index('if data.startswith("snooze_cancel:"):', picktime_start)
    picktime_source = snooze_source[picktime_start:cancel_start]

    assert "parse_snooze_picktime_callback_data(data)" in picktime_source
    assert '_, rid_str, date_str, time_str = data.split(":", 3)' not in picktime_source
    assert "rid = int(rid_str)" not in picktime_source

def test_parse_snooze_pickdate_callback_data_returns_id_and_date():
    assert parse_snooze_pickdate_callback_data("snooze_pickdate:123:2026-07-15") == (123, "2026-07-15")


def test_parse_snooze_pickdate_callback_data_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        parse_snooze_pickdate_callback_data("snooze_cal:123:2026-07")


def test_parse_snooze_pickdate_callback_data_rejects_invalid_id():
    with pytest.raises(ValueError):
        parse_snooze_pickdate_callback_data("snooze_pickdate:not-int:2026-07-15")


def test_snooze_pickdate_uses_callback_parser():
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

    assert "parse_snooze_pickdate_callback_data" in source

    pickdate_start = snooze_source.index('if data.startswith("snooze_pickdate:"):')
    picktime_start = snooze_source.index('if data.startswith("snooze_picktime:"):', pickdate_start)
    pickdate_source = snooze_source[pickdate_start:picktime_start]

    assert "parse_snooze_pickdate_callback_data(data)" in pickdate_source
    assert '_, rid_str, date_str = data.split(":", 2)' not in pickdate_source
    assert "rid = int(rid_str)" not in pickdate_source

def test_parse_snooze_calendar_callback_data_returns_id_year_month():
    assert parse_snooze_calendar_callback_data("snooze_cal:123:2026-07") == (123, 2026, 7)


def test_parse_snooze_calendar_callback_data_rejects_wrong_prefix():
    with pytest.raises(ValueError):
        parse_snooze_calendar_callback_data("snooze:123:1h")


def test_parse_snooze_calendar_callback_data_rejects_invalid_id_or_month():
    with pytest.raises(ValueError):
        parse_snooze_calendar_callback_data("snooze_cal:not-int:2026-07")

    with pytest.raises(ValueError):
        parse_snooze_calendar_callback_data("snooze_cal:123:2026-bad")


def test_snooze_calendar_uses_callback_parser():
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

    assert "parse_snooze_calendar_callback_data" in source

    cal_start = snooze_source.index('if data.startswith("snooze_cal:"):')
    today_start = snooze_source.index('if data.startswith("snooze_caltoday:"):', cal_start)
    cal_source = snooze_source[cal_start:today_start]

    assert "parse_snooze_calendar_callback_data(data)" in cal_source
    assert '_, rid_str, ym = data.split(":", 2)' not in cal_source
    assert "year_str, month_str = ym.split" not in cal_source

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

    assert "handle_done_callback_data(" in done_source
    assert "parse_optional_int_callback_id=parse_optional_int_callback_id" in done_source
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

    assert "handle_snooze_cancel_callback_data(" in cancel_source
    assert "parse_optional_int_callback_id=parse_optional_int_callback_id" in cancel_source
    assert "_, rid_str = data.split" not in cancel_source
    assert "rid = int(rid_str)" not in cancel_source

def test_main_reexports_callback_id_parser():
    assert main.parse_optional_int_callback_id is parse_optional_int_callback_id
