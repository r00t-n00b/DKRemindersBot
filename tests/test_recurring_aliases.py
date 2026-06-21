from datetime import timedelta


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
