from pathlib import Path

import main
from dkreminders_bot.ui.command_messages import HELP_TEXT, START_TEXT


def test_start_text_contains_existing_core_examples():
    assert "👋 Привет. Я бот для напоминаний." in START_TEXT
    assert "напомни завтра в 11 купить молоко" in START_TEXT
    assert "/remind every day 10:00 - пить воду" in START_TEXT
    assert "Если в дате нет времени, использую 10:00." in START_TEXT


def test_help_text_contains_existing_core_sections_and_examples():
    assert "📌 Reminders - справка" in HELP_TEXT
    assert "🟢 САМЫЙ ПРОСТОЙ СПОСОБ" in HELP_TEXT
    assert "/remind every 90 minutes - попить воды" in HELP_TEXT
    assert "Доступны кнопки:" in HELP_TEXT
    assert "Mark complete" in HELP_TEXT


def test_main_reexports_command_texts_for_handlers():
    assert main.START_TEXT is START_TEXT
    assert main.HELP_TEXT is HELP_TEXT


def test_start_and_help_texts_are_no_longer_embedded_in_main_source():
    source = Path("main.py").read_text()

    assert "👋 Привет. Я бот для напоминаний." not in source
    assert "📌 Reminders - справка" not in source
    assert "text = START_TEXT" in source
    assert "text = HELP_TEXT" in source
