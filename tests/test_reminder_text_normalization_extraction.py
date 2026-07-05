import main
import dkreminders_bot.workers.reminder_text_normalization as reminder_text_normalization


def test_main_normalize_reminder_text_fallback_delegates_to_impl(monkeypatch):
    calls = []

    def fake_impl(text, deps):
        calls.append((text, deps))
        return "normalized"

    monkeypatch.setattr(main, "normalize_reminder_text_fallback_impl", fake_impl)

    result = main._normalize_reminder_text_fallback("raw text")

    assert result == "normalized"
    assert len(calls) == 1
    assert calls[0][0] == "raw text"


def test_normalize_reminder_text_fallback_wrapper_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    wrappers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_normalize_reminder_text_fallback"
    ]

    assert len(wrappers) == 1

    wrapper = wrappers[0]
    wrapper_source = ast.get_source_segment(source, wrapper)

    assert "normalize_reminder_text_fallback_impl(text, _build_reminder_text_normalization_deps())" in wrapper_source
    assert wrapper.end_lineno - wrapper.lineno + 1 <= 2


def test_reminder_text_normalization_module_contains_impl_and_no_main_import():
    source = open("dkreminders_bot/workers/reminder_text_normalization.py").read()

    assert "def normalize_reminder_text_fallback_impl(" in source
    assert "_apply_deps(deps)" in source
    assert "import main" not in source
    assert "from main import" not in source


def test_reminder_text_normalization_module_exports_impl():
    assert hasattr(reminder_text_normalization, "normalize_reminder_text_fallback_impl")
