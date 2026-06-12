from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def test_strip_leading_token_in_group_strips_alias_like_token(main_module):
    raw = "TeamA 02.02 12:00 - hi"

    stripped, did_strip = main_module._strip_leading_token_in_group(raw)

    assert did_strip is True
    assert stripped == "02.02 12:00 - hi"


def test_strip_leading_token_in_group_strips_username_like_token(main_module):
    raw = "@someone 02.02 12:00 - hi"

    stripped, did_strip = main_module._strip_leading_token_in_group(raw)

    assert did_strip is True
    assert stripped == "02.02 12:00 - hi"


def test_rest_starts_like_datetime_true(main_module):
    assert main_module._rest_starts_like_datetime("02.02 12:00 - hi") is True