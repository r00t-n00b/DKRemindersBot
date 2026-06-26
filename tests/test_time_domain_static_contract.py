from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_DIR_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "tests",
    ".venv",
    "venv",
}

EXCLUDED_FILES = {
    "time_utils.py",
}


def _production_py_files():
    for path in ROOT.rglob("*.py"):
        rel_parts = set(path.relative_to(ROOT).parts)
        if rel_parts & EXCLUDED_DIR_PARTS:
            continue
        if path.name in EXCLUDED_FILES:
            continue
        yield path


def test_production_code_uses_shared_bot_timezone_constant():
    offenders = []

    for path in _production_py_files():
        text = path.read_text()
        if 'ZoneInfo("Europe/Madrid")' in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_production_code_uses_shared_now_provider_instead_of_datetime_now_tz():
    offenders = []

    for path in _production_py_files():
        text = path.read_text()
        if "datetime.now(TZ)" in text and path.name not in {"main.py", "reminder_callback_router.py"}:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_production_code_does_not_call_astimezone_tz_on_bare_variables():
    offenders = []

    bare_astimezone = re.compile(
        r"(?<!ensure_aware\()\b[A-Za-z_][A-Za-z0-9_]*\.astimezone\(TZ\)"
    )

    for path in _production_py_files():
        text = path.read_text()
        if bare_astimezone.search(text):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
