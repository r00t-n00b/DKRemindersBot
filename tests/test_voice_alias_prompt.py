import main
from voice_alias_prompt import format_known_aliases_for_voice_prompt


class DummyLogger:
    def __init__(self):
        self.exceptions = []

    def exception(self, message):
        self.exceptions.append(message)


def test_format_known_aliases_for_voice_prompt_lists_user_and_chat_aliases_sorted():
    logger = DummyLogger()

    text = format_known_aliases_for_voice_prompt(
        123,
        get_all_user_aliases=lambda created_by: [("Наташа", 1), ("Миша", 2), ("Наташа", 3)],
        get_all_aliases=lambda created_by: [("football", 10, "Football"), ("home", 11, "Home")],
        logger=logger,
    )

    assert "Known aliases. Use these only if the spoken target clearly matches one of them." in text
    assert "Known user aliases:" in text
    assert "- Миша" in text
    assert "- Наташа" in text
    assert text.count("- Наташа") == 1
    assert "Known chat aliases:" in text
    assert "- football" in text
    assert "- home" in text
    assert logger.exceptions == []


def test_format_known_aliases_for_voice_prompt_uses_none_when_lists_are_empty():
    logger = DummyLogger()

    text = format_known_aliases_for_voice_prompt(
        123,
        get_all_user_aliases=lambda created_by: [],
        get_all_aliases=lambda created_by: [],
        logger=logger,
    )

    assert "Known user aliases:\n- none" in text
    assert "Known chat aliases:\n- none" in text


def test_format_known_aliases_for_voice_prompt_logs_and_falls_back_on_errors():
    logger = DummyLogger()

    def fail_user_aliases(created_by):
        raise RuntimeError("user failed")

    def fail_chat_aliases(created_by):
        raise RuntimeError("chat failed")

    text = format_known_aliases_for_voice_prompt(
        123,
        get_all_user_aliases=fail_user_aliases,
        get_all_aliases=fail_chat_aliases,
        logger=logger,
    )

    assert "Known user aliases:\n- none" in text
    assert "Known chat aliases:\n- none" in text
    assert logger.exceptions == [
        "Не смог получить user aliases для voice prompt",
        "Не смог получить chat aliases для voice prompt",
    ]


def test_main_wrapper_keeps_existing_voice_alias_prompt_contract(monkeypatch):
    monkeypatch.setattr(main, "get_all_user_aliases", lambda created_by: [("Наташа", 1)])
    monkeypatch.setattr(main, "get_all_aliases", lambda created_by: [("football", 10, "Football")])

    text = main._format_known_aliases_for_voice_prompt(123)

    assert "- Наташа" in text
    assert "- football" in text


def test_voice_alias_prompt_body_is_no_longer_defined_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "Known aliases. Use these only if the spoken target clearly matches one of them." not in source
    assert "from voice_alias_prompt import format_known_aliases_for_voice_prompt" in source
