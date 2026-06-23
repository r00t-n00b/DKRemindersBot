from datetime import datetime, timezone

import main
from plain_text_local_normalization import normalize_plain_text_reminder_locally


def fake_now():
    return datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def test_plain_text_local_normalizer_accepts_explicit_relative_date_and_time():
    result = normalize_plain_text_reminder_locally(
        "напомни завтра в 14:55 позвонить доктору",
        split_expr_and_text=main._split_expr_and_text,
        parse_date_time_smart=main.parse_date_time_smart,
        get_now=fake_now,
    )

    assert result == "завтра 14:55 - позвонить доктору"


def test_plain_text_local_normalizer_accepts_month_name_date_without_time():
    result = normalize_plain_text_reminder_locally(
        "напомни 1 октября пересчитать страховку",
        split_expr_and_text=main._split_expr_and_text,
        parse_date_time_smart=main.parse_date_time_smart,
        get_now=fake_now,
    )

    assert result == "1 октября - пересчитать страховку"


def test_plain_text_local_normalizer_rejects_broad_relative_phrase_without_time():
    result = normalize_plain_text_reminder_locally(
        "напомни завтра поздравить Саню",
        split_expr_and_text=main._split_expr_and_text,
        parse_date_time_smart=main.parse_date_time_smart,
        get_now=fake_now,
    )

    assert result is None


def test_plain_text_local_normalizer_rejects_empty_or_unparseable_text():
    assert (
        normalize_plain_text_reminder_locally(
            "",
            split_expr_and_text=main._split_expr_and_text,
            parse_date_time_smart=main.parse_date_time_smart,
            get_now=fake_now,
        )
        is None
    )

    assert (
        normalize_plain_text_reminder_locally(
            "просто обычное сообщение",
            split_expr_and_text=main._split_expr_and_text,
            parse_date_time_smart=main.parse_date_time_smart,
            get_now=fake_now,
        )
        is None
    )


def test_main_wrapper_keeps_plain_text_local_normalizer_contract(monkeypatch):
    monkeypatch.setattr(main, "get_now", fake_now)

    assert (
        main._normalize_plain_text_reminder_locally("напомни 1 октября пересчитать страховку")
        == "1 октября - пересчитать страховку"
    )


def test_plain_text_local_normalizer_body_is_no_longer_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "Fast local path for plain text reminders before Gemini" not in source
    assert "напомни 1 октября пересчитать страховку" not in source
    assert "from plain_text_local_normalization import normalize_plain_text_reminder_locally" in source


def test_plain_text_local_normalizer_uses_injected_split_expr_dependency():
    calls = []

    def fake_split_expr_and_text(candidate):
        calls.append(candidate)
        return "1 октября", "пересчитать страховку"

    def fake_parse_date_time_smart(raw, now):
        assert raw == "1 октября пересчитать страховку"

    result = normalize_plain_text_reminder_locally(
        "напомни 1 октября пересчитать страховку",
        split_expr_and_text=fake_split_expr_and_text,
        parse_date_time_smart=fake_parse_date_time_smart,
        get_now=fake_now,
    )

    assert result == "1 октября - пересчитать страховку"
    assert calls == ["1 октября пересчитать страховку"]
