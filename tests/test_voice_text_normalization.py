import main
from voice_text_normalization import (
    _normalize_plain_text_relative_reminder_locally,
    _normalize_voice_ru_months,
    _normalize_voice_spoken_numbers,
    _strip_voice_reminder_prefix,
    normalize_gemini_reminder_command_text,
    normalize_voice_reminder_text,
)


def test_strip_voice_reminder_prefix_removes_common_ru_and_en_prefixes():
    assert _strip_voice_reminder_prefix("напомни завтра в 11 купить молоко") == "завтра в 11 купить молоко"
    assert _strip_voice_reminder_prefix("напомнить мне завтра купить молоко") == "завтра купить молоко"
    assert _strip_voice_reminder_prefix("remind me tomorrow buy milk") == "tomorrow buy milk"


def test_normalize_voice_spoken_numbers_and_months():
    text = _normalize_voice_spoken_numbers("двадцать девятого мая в восемнадцать сорок шесть")
    text = _normalize_voice_ru_months(text)

    assert "29 may" in text
    assert "18 46" in text


def test_normalize_voice_reminder_text_handles_relative_date_and_time():
    assert (
        normalize_voice_reminder_text("напомни завтра в 14:55 позвонить доктору")
        == "завтра 14:55 - позвонить доктору"
    )


def test_normalize_voice_reminder_text_handles_weekday_time_and_text():
    assert (
        normalize_voice_reminder_text("в понедельник 22:58 спросить как дела")
        == "в понедельник 22:58 - спросить как дела"
    )


def test_normalize_voice_reminder_text_handles_month_name_time_and_text():
    assert (
        normalize_voice_reminder_text("двадцать девятого мая в восемнадцать сорок шесть спросить как дела")
        == "29 may 18:46 - спросить как дела"
    )


def test_normalize_plain_text_relative_reminder_locally_handles_ru_and_en_intervals():
    assert (
        _normalize_plain_text_relative_reminder_locally("через 5 минут проверить духовку")
        == "in 5 minutes - проверить духовку"
    )
    assert (
        _normalize_plain_text_relative_reminder_locally("in an hour check oven")
        == "in 1 hour - check oven"
    )


def test_normalize_gemini_reminder_command_text_normalizes_fractional_and_word_intervals():
    assert (
        normalize_gemini_reminder_command_text("каждые полчаса - пить воду")
        == "every 30 minutes - пить воду"
    )
    assert (
        normalize_gemini_reminder_command_text("каждые полтора часа - пить воду")
        == "every 90 minutes - пить воду"
    )
    assert (
        normalize_gemini_reminder_command_text("каждые два часа - пить воду")
        == "каждые 2 часа - пить воду"
    )


def test_main_reexports_voice_text_normalization_helpers_for_existing_callers():
    assert main._strip_voice_reminder_prefix is _strip_voice_reminder_prefix
    assert main._normalize_voice_spoken_numbers is _normalize_voice_spoken_numbers
    assert main._normalize_voice_ru_months is _normalize_voice_ru_months
    assert main._normalize_plain_text_relative_reminder_locally is _normalize_plain_text_relative_reminder_locally
    assert main.normalize_gemini_reminder_command_text is normalize_gemini_reminder_command_text
    assert main.normalize_voice_reminder_text is normalize_voice_reminder_text


def test_voice_text_normalization_bodies_are_no_longer_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "def _strip_voice_reminder_prefix(" not in source
    assert "def _normalize_voice_spoken_numbers(" not in source
    assert "def _normalize_voice_ru_months(" not in source
    assert "def _format_english_relative_interval(" not in source
    assert "def _normalize_plain_text_relative_reminder_locally(" not in source
    assert "def normalize_gemini_reminder_command_text(" not in source
    assert "def normalize_voice_reminder_text(" not in source
    assert "from voice_text_normalization import (" in source
