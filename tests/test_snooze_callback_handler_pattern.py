import re


def test_snooze_callback_handler_pattern_includes_calendar_prefixes(main_module):
    pattern = main_module.build_snooze_callback_pattern()

    assert "snooze_page:" not in pattern

    assert "snooze_cal:" in pattern
    assert "snooze_caltoday:" in pattern

    assert "snooze_pickdate:" in pattern
    assert "snooze_picktime:" in pattern
    assert "snooze_cancel:" in pattern
    assert "snooze:" in pattern

    assert "selfremind:ask:" in pattern
    assert "selfremind:set:" in pattern
    assert "selfremind:back:" in pattern
    assert "selfremind:cancel_personal:" in pattern

    assert re.compile(pattern)