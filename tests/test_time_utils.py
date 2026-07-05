from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from dkreminders_bot.utils.time_utils import BOT_TZ, aware_now, ensure_aware, from_iso, to_iso


def test_aware_now_returns_timezone_aware_datetime():
    now = aware_now()

    assert now.tzinfo is not None
    assert now.tzinfo == BOT_TZ


def test_to_iso_rejects_naive_datetime():
    with pytest.raises(ValueError, match="naive datetime"):
        to_iso(datetime(2026, 1, 2, 3, 4))


def test_to_iso_serializes_aware_datetime():
    dt = datetime(2026, 1, 2, 3, 4, tzinfo=ZoneInfo("Europe/Madrid"))

    assert to_iso(dt) == "2026-01-02T03:04:00+01:00"


def test_from_iso_rejects_naive_string():
    with pytest.raises(ValueError, match="naive datetime"):
        from_iso("2026-01-02T03:04:00")


def test_from_iso_parses_aware_string():
    dt = from_iso("2026-01-02T03:04:00+01:00")

    assert dt.tzinfo is not None
    assert dt.isoformat() == "2026-01-02T03:04:00+01:00"


def test_ensure_aware_adds_default_tz_to_naive_datetime():
    dt = ensure_aware(datetime(2026, 1, 2, 3, 4))

    assert dt.tzinfo == BOT_TZ
    assert dt.isoformat() == "2026-01-02T03:04:00+01:00"


def test_ensure_aware_preserves_existing_tz():
    utc = ZoneInfo("UTC")
    original = datetime(2026, 1, 2, 3, 4, tzinfo=utc)

    assert ensure_aware(original) is original
