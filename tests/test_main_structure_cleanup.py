from pathlib import Path


def test_main_has_no_empty_event_parser_section_after_extraction():
    content = Path("main.py").read_text()

    assert "# ===== Парсинг даты события из текста напоминания =====" not in content
    assert "from event_datetime import (" in content


def test_main_has_no_blank_line_artifacts_around_keyboard_wrapper_boundary():
    content = Path("main.py").read_text()

    assert (
        "return build_created_reminder_actions_keyboard(reminder_id, is_recurring=is_recurring)"
        "\n\n\n\ndef _sync_keyboard_builder_classes"
    ) not in content


def test_main_has_no_blank_line_artifacts_inside_start_command():
    content = Path("main.py").read_text()

    assert '""").strip()\n\n\n    msg = update.effective_message' not in content


def test_main_has_no_command_message_extraction_artifacts():
    content = Path("main.py").read_text()

    assert "safe_reply(message,text)" not in content
    assert "\nfrom typing import Tuple\n\nasync def aliases_command" not in content
    assert "text = HELP_TEXT\n\n\n\n\n    await safe_reply" not in content


def test_main_does_not_import_dedent_after_command_messages_extraction():
    content = Path("main.py").read_text()

    assert "from textwrap import dedent" not in content
    assert "dedent(" not in content


def test_main_has_no_empty_model_section_after_model_extraction():
    content = Path("main.py").read_text()

    assert "# ===== Модель данных =====" not in content
    assert "from models import Reminder" in content


def test_main_does_not_import_calendar_after_keyboard_extraction():
    content = Path("main.py").read_text()

    assert "import calendar" not in content
    assert "calendar." not in content
