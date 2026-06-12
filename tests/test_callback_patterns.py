import re


def test_delete_callback_pattern():
    p = re.compile(r"^del:\d+$")
    assert p.match("del:1")
    assert p.match("del:999")
    assert not p.match("del:")
    assert not p.match("del:a")
    assert not p.match("undo:abc")


def test_undo_callback_pattern():
    p = re.compile(r"^undo:[A-Za-z0-9_-]{16,}$")
    assert p.match("undo:abcdefghijklmnop")  # 16 chars
    assert p.match("undo:abcDEF123_-xyz987654321")
    assert not p.match("undo:short")
    assert not p.match("undo:")
    assert not p.match("del:1")