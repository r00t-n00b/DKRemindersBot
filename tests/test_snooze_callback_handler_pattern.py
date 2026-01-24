import re


def test_snooze_callback_handler_pattern_includes_snooze_page():
    with open("main.py", "r", encoding="utf-8") as f:
        src = f.read()

    # Ищем строку с pattern у snooze_callback handler-а
    m = re.search(
        r"CallbackQueryHandler\(\s*snooze_callback\s*,\s*pattern=r\"([^\"]+)\"\s*\)",
        src,
        re.DOTALL,
    )
    assert m, "Не нашел CallbackQueryHandler(snooze_callback, pattern=...) в main.py"

    pattern = m.group(1)
    assert "snooze_page:" in pattern