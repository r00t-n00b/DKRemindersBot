import re
from pathlib import Path

import dkreminders_bot.callbacks.callback_contracts as c


def test_callback_contract_patterns_compile():
    pattern_values = [
        value
        for name, value in vars(c).items()
        if name.endswith("_PATTERN")
    ]

    assert pattern_values
    for pattern in pattern_values:
        re.compile(pattern)


def test_main_uses_callback_contract_pattern_constants():
    text = Path("main.py").read_text()

    forbidden_literals = [
        'pattern=r"^noop$"',
        'pattern=r"^undo:"',
        'pattern=r"^done:"',
        'pattern=r"^del_(one|series|cancel):"',
        'pattern=r"^selfremind:"',
        'pattern=r"^created_snooze(:|_cal:|_caltoday:|_pastdate:|_pickdate:|_picktime:|_cancel:)"',
        'pattern=r"^created_snooze_custom:\\\\d+$"',
        'pattern=r"^created_complete:"',
        'pattern=r"^created_delete:"',
        'pattern=r"^snooze:"',
        'pattern=r"^snooze_custom:\\\\d+$"',
        'pattern=r"^snooze_(cal|caltoday|pastdate|pickdate|picktime|cancel):"',
    ]

    for literal in forbidden_literals:
        assert literal not in text

    required_constants = [
        "NOOP_PATTERN",
        "UNDO_PATTERN",
        "DONE_PATTERN",
        "DELETE_CHOICE_PATTERN",
        "SELFREMIND_PATTERN",
        "CREATED_SNOOZE_PATTERN",
        "CREATED_SNOOZE_CUSTOM_PATTERN",
        "CREATED_COMPLETE_PATTERN",
        "CREATED_DELETE_PATTERN",
        "SNOOZE_PATTERN",
        "SNOOZE_CUSTOM_PATTERN",
        "SNOOZE_CALENDAR_PATTERN",
    ]

    for name in required_constants:
        assert name in text


def test_snooze_pattern_still_does_not_shadow_created_snooze():
    assert re.compile(c.SNOOZE_PATTERN).match("snooze:123:1h")
    assert not re.compile(c.SNOOZE_PATTERN).match("created_snooze:123:1h")
