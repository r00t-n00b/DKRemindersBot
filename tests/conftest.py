import importlib
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


# ⬇️ ВАЖНО: добавляем корень проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


TZ = ZoneInfo("Europe/Madrid")


@pytest.fixture()
def tz():
    return TZ


@pytest.fixture()
def fixed_now(tz):
    # Фиксированное "сейчас", чтобы тесты не флапали.
    # 2025-11-28 это пятница.
    return datetime(2025, 11, 28, 10, 0, tzinfo=tz)


@pytest.fixture()
def main_module(tmp_path, monkeypatch):
    db_path = tmp_path / "test_reminders.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    import main
    importlib.reload(main)

    main.init_db()
    return main