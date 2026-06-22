import asyncio
from types import SimpleNamespace


class FakeMessage:
    def __init__(self, text="/defaulttime"):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_default_time_parser_accepts_colon_and_dot(main_module):
    m = main_module

    assert m.parse_default_time_value("09:30") == (9, 30)
    assert m.parse_default_time_value("9.05") == (9, 5)


def test_default_time_parser_rejects_invalid_values(main_module):
    m = main_module

    for raw in ["25:00", "12:99", "abc", "9"]:
        try:
            m.parse_default_time_value(raw)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {raw!r}")


def test_user_default_time_roundtrip(main_module):
    m = main_module

    assert m.get_user_default_time(1000) is None

    m.set_user_default_time(1000, 9, 30)
    assert m.get_user_default_time(1000) == (9, 30)

    m.clear_user_default_time(1000)
    assert m.get_user_default_time(1000) is None


def test_defaulttime_command_sets_time(main_module):
    m = main_module
    message = FakeMessage()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=1000),
    )
    context = SimpleNamespace(args=["09:30"])

    asyncio.run(m.defaulttime_command(update, context))

    assert m.get_user_default_time(1000) == (9, 30)
    assert message.replies[-1][0] == "Ок, время по умолчанию: 09:30."


def test_defaulttime_command_shows_current_time(main_module):
    m = main_module
    m.set_user_default_time(1000, 8, 15)

    message = FakeMessage()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=1000),
    )
    context = SimpleNamespace(args=[])

    asyncio.run(m.defaulttime_command(update, context))

    assert "Текущее время по умолчанию: 08:15" in message.replies[-1][0]


def test_defaulttime_command_resets_time(main_module):
    m = main_module
    m.set_user_default_time(1000, 8, 15)

    message = FakeMessage()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=1000),
    )
    context = SimpleNamespace(args=["reset"])

    asyncio.run(m.defaulttime_command(update, context))

    assert m.get_user_default_time(1000) is None
    assert message.replies[-1][0] == "Ок, сбросил время по умолчанию."


def test_parse_date_without_time_uses_custom_default(main_module, fixed_now):
    m = main_module

    dt, text = m.parse_date_time_smart(
        "25.12 - buy gifts",
        fixed_now,
        default_time=(9, 30),
    )

    assert (dt.hour, dt.minute) == (9, 30)
    assert text == "buy gifts"


def test_parse_tomorrow_without_time_uses_custom_default(main_module, fixed_now):
    m = main_module

    dt, text = m.parse_date_time_smart(
        "tomorrow - buy milk",
        fixed_now,
        default_time=(8, 45),
    )

    assert dt.date() == (fixed_now + m.timedelta(days=1)).date()
    assert (dt.hour, dt.minute) == (8, 45)
    assert text == "buy milk"


def test_parse_explicit_time_ignores_custom_default(main_module, fixed_now):
    m = main_module

    dt, text = m.parse_date_time_smart(
        "tomorrow 18:20 - buy milk",
        fixed_now,
        default_time=(8, 45),
    )

    assert (dt.hour, dt.minute) == (18, 20)
    assert text == "buy milk"


def test_parse_recurring_without_time_uses_custom_default(main_module, fixed_now):
    m = main_module

    first_at, text, pattern_type, payload, hour, minute = m.parse_recurring(
        "every day - standup",
        fixed_now,
        default_time=(8, 15),
    )

    assert text == "standup"
    assert pattern_type == "daily"
    assert (hour, minute) == (8, 15)
    assert (first_at.hour, first_at.minute) == (8, 15)


def test_parse_recurring_explicit_time_ignores_custom_default(main_module, fixed_now):
    m = main_module

    first_at, text, pattern_type, payload, hour, minute = m.parse_recurring(
        "every day 18:20 - standup",
        fixed_now,
        default_time=(8, 15),
    )

    assert text == "standup"
    assert pattern_type == "daily"
    assert (hour, minute) == (18, 20)
    assert (first_at.hour, first_at.minute) == (18, 20)


def test_compute_snooze_tomorrow_uses_custom_default(main_module, fixed_now):
    m = main_module

    dt = m.compute_snooze_target_time(
        "tomorrow",
        fixed_now,
        default_time=(7, 40),
    )

    assert dt.date() == (fixed_now + m.timedelta(days=1)).date()
    assert (dt.hour, dt.minute) == (7, 40)


def test_remind_command_uses_user_default_time_for_date_only(main_module, fixed_now, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)
    monkeypatch.setattr(m, "get_user_default_time", lambda user_id: (9, 30))

    message = FakeMessage("/remind 25.12 - buy gifts")
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(id=12345, type=m.Chat.PRIVATE),
        effective_user=SimpleNamespace(id=1000, username="tester", first_name="Tester", last_name=None),
    )
    context = SimpleNamespace(args=["25.12", "-", "buy", "gifts"], user_data={})

    asyncio.run(m.remind_command(update, context))

    rows = m.get_active_reminders_for_chat(12345)
    assert len(rows) == 1
    remind_at = m.datetime.fromisoformat(rows[0]["remind_at"])
    assert (remind_at.hour, remind_at.minute) == (9, 30)
