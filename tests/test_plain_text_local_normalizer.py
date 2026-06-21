from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def test_plain_text_local_normalizer_handles_russian_month_name_without_gemini(main_module, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_now",
        lambda: datetime(2026, 6, 15, 13, 26, tzinfo=TZ),
    )

    normalized = main_module._normalize_plain_text_reminder_locally(
        "напомни 1 октября пересчитать стоимость начинки квартиры и поменять в страховке"
    )

    assert normalized == (
        "1 октября - пересчитать стоимость начинки квартиры и поменять в страховке"
    )


def test_plain_text_local_normalizer_handles_russian_month_name_with_time(main_module, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_now",
        lambda: datetime(2026, 6, 15, 13, 26, tzinfo=TZ),
    )

    normalized = main_module._normalize_plain_text_reminder_locally(
        "напомни 1 октября в 12:30 пересчитать страховку"
    )

    assert normalized == "1 октября в 12:30 - пересчитать страховку"


def test_plain_text_local_normalizer_returns_none_for_unclear_text(main_module, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_now",
        lambda: datetime(2026, 6, 15, 13, 26, tzinfo=TZ),
    )

    assert main_module._normalize_plain_text_reminder_locally(
        "напомни когда-нибудь пересчитать страховку"
    ) is None


def test_plain_text_local_normalizer_leaves_tomorrow_for_gemini(main_module, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_now",
        lambda: datetime(2026, 6, 15, 13, 26, tzinfo=TZ),
    )

    assert main_module._normalize_plain_text_reminder_locally(
        "напомни завтра поздравить Саню"
    ) is None


def test_plain_text_local_normalizer_leaves_tomorrow_with_time_for_existing_flow(main_module, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_now",
        lambda: datetime(2026, 6, 15, 13, 26, tzinfo=TZ),
    )

    assert main_module._normalize_plain_text_reminder_locally(
        "напомни завтра в 18:00 купить молоко"
    ) == "завтра 18:00 - купить молоко"

    assert main_module._normalize_plain_text_reminder_locally(
        "напомни сегодня в 18:00 купить молоко"
    ) == "сегодня 18:00 - купить молоко"

    assert main_module._normalize_plain_text_reminder_locally(
        "напомни послезавтра в 9:00 проверить документы"
    ) == "послезавтра 9:00 - проверить документы"
