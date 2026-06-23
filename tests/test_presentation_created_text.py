from pathlib import Path

from presentation import format_created_reminder_text


def test_format_created_reminder_text():
    assert (
        format_created_reminder_text("22.06 19:30", "купить молоко")
        == "Ок, напомню 22.06 19:30: купить молоко"
    )


def test_created_reminder_text_is_used_from_presentation():
    main_source = Path("main.py").read_text()

    assert "format_created_reminder_text=format_created_reminder_text" in main_source
    assert "format_created_reminder_text(" in Path("single_oneoff_reminder.py").read_text()
    assert 'f"Ок, напомню {when_str}: {' not in main_source
