from pathlib import Path

import main
from remind_arg_utils import strip_first_token_from_first_line


def test_strip_first_token_from_single_line():
    assert (
        strip_first_token_from_first_line("me tomorrow 10:00 - milk", "me")
        == "tomorrow 10:00 - milk"
    )


def test_strip_first_token_from_multiline_preserves_rest_lines():
    assert (
        strip_first_token_from_first_line("home first reminder\nsecond reminder", "home")
        == "first reminder\nsecond reminder"
    )


def test_strip_first_token_returns_rest_lines_when_first_line_only_token():
    assert (
        strip_first_token_from_first_line("home\nsecond reminder", "home")
        == "second reminder"
    )


def test_main_uses_extracted_first_token_helper():
    source = Path("main.py").read_text()

    assert "from remind_arg_utils import strip_first_token_from_first_line" in source
    assert "strip_first_token_from_first_line(raw_args, first_token)" in source
    assert "rest_first_line = first_line[len(first_token):].lstrip()" not in source


def test_main_reexports_strip_first_token_helper_for_existing_callers():
    assert main.strip_first_token_from_first_line is strip_first_token_from_first_line
