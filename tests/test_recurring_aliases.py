from datetime import timedelta
from types import SimpleNamespace


def test_recurring_hourly_aliases(main_module, fixed_now):
    for raw in [
        "hourly - water",
        "ежечасно - вода",
    ]:
        first_dt, text, ptype, payload, h, m = main_module.parse_recurring(raw, fixed_now)

        assert ptype == "interval"
        assert payload == {"value": 1, "unit": "hours"}
        assert (h, m) == (10, 0)
        assert first_dt == fixed_now.replace(second=0, microsecond=0) + timedelta(hours=1)
        assert text in {"water", "вода"}


def test_recurring_daily_aliases(main_module, fixed_now):
    for raw in [
        "daily - water",
        "ежедневно - вода",
    ]:
        first_dt, text, ptype, payload, h, m = main_module.parse_recurring(raw, fixed_now)

        assert ptype == "daily"
        assert payload == {}
        assert (h, m) == (10, 0)
        assert first_dt.strftime("%d.%m %H:%M") == "29.11 10:00"
        assert text in {"water", "вода"}


def test_recurring_weekly_aliases(main_module, fixed_now):
    for raw in [
        "weekly - water",
        "еженедельно - вода",
    ]:
        first_dt, text, ptype, payload, h, m = main_module.parse_recurring(raw, fixed_now)

        assert ptype == "weekly"
        assert payload == {"weekday": fixed_now.weekday()}
        assert (h, m) == (10, 0)
        assert first_dt.strftime("%d.%m %H:%M") == "05.12 10:00"
        assert text in {"water", "вода"}


def test_recurring_monthly_aliases(main_module, fixed_now):
    for raw in [
        "monthly - water",
        "ежемесячно - вода",
    ]:
        first_dt, text, ptype, payload, h, m = main_module.parse_recurring(raw, fixed_now)

        assert ptype == "monthly"
        assert payload == {"day": fixed_now.day}
        assert (h, m) == (10, 0)
        assert first_dt.strftime("%d.%m %H:%M") == "28.12 10:00"
        assert text in {"water", "вода"}


class FakePrivateChat:
    PRIVATE = "private"

    def __init__(self, chat_id=12345):
        self.id = chat_id
        self.type = "private"


class FakeUser:
    def __init__(self, user_id=1000):
        self.id = user_id
        self.username = "tester"
        self.first_name = "Tester"


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_remind_command_routes_recurring_aliases_to_recurring_parser(main_module, monkeypatch):
    m = main_module

    created_templates = []
    created_reminders = []

    monkeypatch.setattr(m, "get_now", lambda: m.datetime(2026, 6, 21, 23, 15, tzinfo=m.TZ))
    monkeypatch.setattr(m, "create_recurring_template", lambda **kwargs: created_templates.append(kwargs) or 501)
    monkeypatch.setattr(m, "add_reminder", lambda **kwargs: created_reminders.append(kwargs) or 901)
    monkeypatch.setattr(m, "build_created_reminder_actions_keyboard", lambda *args, **kwargs: None)

    cases = [
        ("/remind hourly - smoke hourly", "smoke hourly", "interval", {"value": 1, "unit": "hours"}),
        ("/remind daily - smoke daily", "smoke daily", "daily", {}),
        ("/remind weekly - smoke weekly", "smoke weekly", "weekly", {"weekday": 6}),
        ("/remind monthly - smoke monthly", "smoke monthly", "monthly", {"day": 21}),
        ("/remind ежечасно - smoke hourly ru", "smoke hourly ru", "interval", {"value": 1, "unit": "hours"}),
        ("/remind ежедневно - smoke daily ru", "smoke daily ru", "daily", {}),
        ("/remind еженедельно - smoke weekly ru", "smoke weekly ru", "weekly", {"weekday": 6}),
        ("/remind ежемесячно - smoke monthly ru", "smoke monthly ru", "monthly", {"day": 21}),
    ]

    for raw, expected_text, expected_pattern, expected_payload in cases:
        message = FakeMessage(raw)
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=FakePrivateChat(12345),
            effective_user=FakeUser(1000),
        )
        context = SimpleNamespace(args=raw.split()[1:], user_data={})

        m.asyncio.run(m.remind_command(update, context))

        assert message.replies
        assert "Ок, создал повторяющееся напоминание." in message.replies[-1][0]
        assert "Не смог понять дату и текст" not in message.replies[-1][0]

        tpl = created_templates[-1]
        assert tpl["text"] == expected_text
        assert tpl["pattern_type"] == expected_pattern
        assert tpl["payload"] == expected_payload

        reminder = created_reminders[-1]
        assert reminder["text"] == expected_text
        assert reminder["template_id"] == 501


def test_recurring_aliases_without_dash_show_recurring_hint(main_module):
    m = main_module

    for raw in [
        "/remind hourly smoke hourly",
        "/remind daily smoke daily",
        "/remind weekly smoke weekly",
        "/remind monthly smoke monthly",
        "/remind ежечасно smoke hourly ru",
        "/remind ежедневно smoke daily ru",
        "/remind еженедельно smoke weekly ru",
        "/remind ежемесячно smoke monthly ru",
    ]:
        message = FakeMessage(raw)
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=FakePrivateChat(12345),
            effective_user=FakeUser(1000),
        )
        context = SimpleNamespace(args=raw.split()[1:], user_data={})

        m.asyncio.run(m.remind_command(update, context))

        assert message.replies
        assert message.replies[-1][0] == m.msg_recurring_missing_dash(is_private=True)
