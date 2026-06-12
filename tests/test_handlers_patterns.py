import re


def _assert_any_prefix(pattern: str, prefixes: list[str]) -> None:
    rx = re.compile(pattern)
    missing = []
    for p in prefixes:
        if rx.match(p):
            continue
        missing.append(p)
    assert not missing, f"Handler pattern does not match prefixes: {missing}"


def test_snooze_handler_pattern_matches_all_callback_prefixes(main_module):
    pattern = main_module.build_snooze_callback_pattern()

    prefixes = [
        "snooze:1:20m",
        "snooze:1:1h",
        "snooze:1:3h",
        "snooze:1:tomorrow",
        "snooze:1:next_monday",
        "snooze:1:custom",
        "snooze_cal:1:2026-01-01:next",
        "snooze_cal:1:2026-01-01:prev",
        "snooze_caltoday:1",
        "snooze_pastdate:1:2026-01-01",
        "snooze_pickdate:1:2026-01-15",
        "snooze_picktime:1:2026-01-15:11:00",
        "snooze_cancel:1",
        "noop",
        "done:1",
    ]

    _assert_any_prefix(pattern, prefixes)


def test_self_remind_handler_pattern_matches_all_callback_prefixes(main_module):
    pattern = main_module.build_snooze_callback_pattern()

    prefixes = [
        "selfremind:ask:1",
        "selfremind:mode:1:regular",
        "selfremind:mode:1:event",
        "selfremind:set:1:20m",
        "selfremind:set:1:1h",
        "selfremind:set:1:3h",
        "selfremind:set:1:tomorrow",
        "selfremind:set:1:next_monday",
        "selfremind:event_before:1:1h",
        "selfremind:event_before:1:3h",
        "selfremind:event_before:1:10h",
        "selfremind:event_before:1:1d",
        "selfremind:back:1",
        "selfremind:cancel_personal:1",
        "selfremind_cal:1:2026-01-01:next",
        "selfremind_caltoday:1",
        "selfremind_pickdate:1:2026-01-15",
        "selfremind_picktime:1:2026-01-15:11:00",
        "selfremind_cancel:1",
    ]

    _assert_any_prefix(pattern, prefixes)
