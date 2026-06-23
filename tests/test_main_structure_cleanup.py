from pathlib import Path


def test_main_has_no_empty_event_parser_section_after_extraction():
    content = Path("main.py").read_text()

    assert "# ===== Парсинг даты события из текста напоминания =====" not in content
    assert "from event_datetime import (" in content
