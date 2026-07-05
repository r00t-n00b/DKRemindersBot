from pathlib import Path

from dkreminders_bot.ui.presentation import format_created_recurring_reminder_text


def test_format_created_recurring_reminder_text_without_alias():
    assert (
        format_created_recurring_reminder_text(
            "22.06 10:00",
            "пить воду",
            "daily",
        )
        == "Ок, создал повторяющееся напоминание.\n"
        "Первое напоминание будет 22.06 10:00: пить воду\n"
        "Повтор: daily"
    )


def test_format_created_recurring_reminder_text_with_alias():
    assert (
        format_created_recurring_reminder_text(
            "22.06 10:00",
            "пить воду",
            "daily",
            chat_alias="home",
        )
        == "Ок, создал повторяющееся напоминание в чате 'home'.\n"
        "Первое напоминание будет 22.06 10:00: пить воду\n"
        "Повтор: daily"
    )


def test_format_created_recurring_reminder_text_without_human_suffix():
    assert (
        format_created_recurring_reminder_text(
            "22.06 10:00",
            "пить воду",
            None,
        )
        == "Ок, создал повторяющееся напоминание.\n"
        "Первое напоминание будет 22.06 10:00: пить воду"
    )


def test_recurring_created_text_is_used_from_presentation():
    main_source = Path("main.py").read_text()
    recurring_source = Path("dkreminders_bot/commands/single_recurring_reminder.py").read_text()

    assert '"format_created_recurring_reminder_text"' in Path("dkreminders_bot/commands/remind_command_deps.py").read_text()
    assert "format_created_recurring_reminder_text(" in recurring_source
    assert 'f"Ок, создал повторяющееся напоминание в чате' not in main_source
    assert 'f"Ок, создал повторяющееся напоминание.\\\\n"' not in main_source
    assert 'f"Первое напоминание будет {when_str}: {text}"' not in main_source
