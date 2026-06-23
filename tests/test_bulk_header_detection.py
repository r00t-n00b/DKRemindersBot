from bulk_header_detection import (
    bulk_line_looks_like_reminder_start,
    drop_optional_bulk_header,
)


def fake_looks_like_recurring(line):
    return line.lower().startswith(("каждый ", "every "))


def test_bulk_line_looks_like_reminder_start_for_date_time_and_relative_forms():
    assert bulk_line_looks_like_reminder_start("28.11 12:00 - футбол", looks_like_recurring=fake_looks_like_recurring)
    assert bulk_line_looks_like_reminder_start("12:00 - футбол", looks_like_recurring=fake_looks_like_recurring)
    assert bulk_line_looks_like_reminder_start("tomorrow 12:00 футбол", looks_like_recurring=fake_looks_like_recurring)
    assert bulk_line_looks_like_reminder_start("in 2 hours check oven", looks_like_recurring=fake_looks_like_recurring)
    assert bulk_line_looks_like_reminder_start("March 1 12:00 pay rent", looks_like_recurring=fake_looks_like_recurring)
    assert bulk_line_looks_like_reminder_start("On March 1 pay rent", looks_like_recurring=fake_looks_like_recurring)


def test_bulk_line_looks_like_reminder_start_for_recurring_form():
    assert bulk_line_looks_like_reminder_start("каждый день 10:00 - вода", looks_like_recurring=fake_looks_like_recurring)
    assert bulk_line_looks_like_reminder_start("every day 10:00 - water", looks_like_recurring=fake_looks_like_recurring)


def test_bulk_line_looks_like_reminder_start_rejects_header_text():
    assert not bulk_line_looks_like_reminder_start("Каталония", looks_like_recurring=fake_looks_like_recurring)
    assert not bulk_line_looks_like_reminder_start("Shopping list", looks_like_recurring=fake_looks_like_recurring)
    assert not bulk_line_looks_like_reminder_start("", looks_like_recurring=fake_looks_like_recurring)


def test_drop_optional_bulk_header_drops_header_when_multiple_lines():
    assert drop_optional_bulk_header(
        ["Каталония", "28.11 12:00 - футбол", "29.11 13:00 - матч"],
        looks_like_recurring=fake_looks_like_recurring,
    ) == ["28.11 12:00 - футбол", "29.11 13:00 - матч"]


def test_drop_optional_bulk_header_keeps_first_line_when_it_looks_like_reminder():
    assert drop_optional_bulk_header(
        ["28.11 12:00 - футбол", "29.11 13:00 - матч"],
        looks_like_recurring=fake_looks_like_recurring,
    ) == ["28.11 12:00 - футбол", "29.11 13:00 - матч"]


def test_drop_optional_bulk_header_keeps_single_line():
    assert drop_optional_bulk_header(
        ["Каталония"],
        looks_like_recurring=fake_looks_like_recurring,
    ) == ["Каталония"]


def test_bulk_header_detection_body_is_no_longer_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "is_reminder_like = False" not in source
    assert "month-name формата" not in source
    assert "drop_optional_bulk_header(" in source
    assert "from bulk_header_detection import drop_optional_bulk_header" in source
