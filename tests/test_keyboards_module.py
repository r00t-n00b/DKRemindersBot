class DummyInlineKeyboardButton:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.kwargs = kwargs


class DummyInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard
        self.keyboard = inline_keyboard


def _patch_keyboard_classes(keyboards):
    keyboards.InlineKeyboardButton = DummyInlineKeyboardButton
    keyboards.InlineKeyboardMarkup = DummyInlineKeyboardMarkup


def _callback_data(markup):
    result = []
    for row in getattr(markup, "inline_keyboard", []) or []:
        for button in row:
            data = getattr(button, "callback_data", None)
            if data is not None:
                result.append(data)
    return result


def test_simple_keyboard_builders_are_exposed_via_main_proxy(main_module):
    import keyboards

    assert hasattr(keyboards, "build_created_reminder_actions_keyboard")
    assert hasattr(keyboards, "build_created_reschedule_keyboard")
    assert hasattr(keyboards, "build_group_reminder_keyboard")
    assert hasattr(keyboards, "build_snooze_keyboard")
    assert hasattr(keyboards, "build_self_remind_mode_keyboard")
    assert hasattr(keyboards, "build_self_remind_choice_keyboard")
    assert hasattr(keyboards, "build_self_remind_event_before_keyboard")

    assert callable(main_module.build_created_reminder_actions_keyboard)
    assert callable(main_module.build_created_reschedule_keyboard)
    assert callable(main_module.build_group_reminder_keyboard)
    assert callable(main_module.build_snooze_keyboard)
    assert callable(main_module.build_self_remind_mode_keyboard)
    assert callable(main_module.build_self_remind_choice_keyboard)
    assert callable(main_module.build_self_remind_event_before_keyboard)

    if hasattr(keyboards, "build_list_delete_keyboard"):
        assert callable(main_module.build_list_delete_keyboard)

    if hasattr(keyboards, "build_recurring_delete_choice_keyboard"):
        assert callable(main_module.build_recurring_delete_choice_keyboard)


def test_simple_keyboard_builders_generate_expected_callback_data(main_module):
    import keyboards
    _patch_keyboard_classes(keyboards)

    generated = []

    if hasattr(keyboards, "build_list_delete_keyboard"):
        generated.extend(_callback_data(keyboards.build_list_delete_keyboard(7)))

    if hasattr(keyboards, "build_recurring_delete_choice_keyboard"):
        generated.extend(_callback_data(keyboards.build_recurring_delete_choice_keyboard(7, 9)))

    generated.extend(_callback_data(keyboards.build_created_reminder_actions_keyboard(7, is_recurring=False)))
    generated.extend(_callback_data(keyboards.build_created_reminder_actions_keyboard(7, is_recurring=True)))
    generated.extend(_callback_data(keyboards.build_created_reschedule_keyboard(7)))
    generated.extend(_callback_data(keyboards.build_snooze_keyboard(7)))
    generated.extend(_callback_data(keyboards.build_group_reminder_keyboard(7)))
    generated.extend(_callback_data(keyboards.build_self_remind_mode_keyboard(7)))
    generated.extend(_callback_data(keyboards.build_self_remind_choice_keyboard(7)))
    generated.extend(_callback_data(keyboards.build_self_remind_event_before_keyboard(7)))

    expected = {
        "created_del:7",
        "created_resched:7",
        "created_snooze:7:20m",
        "created_snooze:7:1h",
        "created_snooze:7:3h",
        "created_snooze:7:tomorrow",
        "created_snooze:7:nextmon",
        "created_snooze_custom:7",
        "created_back:7",
        "snooze:7:20m",
        "snooze:7:1h",
        "snooze:7:3h",
        "snooze:7:tomorrow",
        "snooze:7:nextmon",
        "snooze:7:custom",
        "done:7",
        "selfremind:ask:7",
        "selfremind:mode:7:regular",
        "selfremind:mode:7:event",
        "selfremind:cancel_personal:7",
        "selfremind:set:7:20m",
        "selfremind:set:7:1h",
        "selfremind:set:7:3h",
        "selfremind:set:7:tomorrow11",
        "selfremind:set:7:nextmon",
        "selfremind:set:7:custom",
        "selfremind:back:7",
        "selfremind:event_before:7:1d",
        "selfremind:event_before:7:10h",
        "selfremind:event_before:7:3h",
        "selfremind:event_before:7:1h",
        "selfremind:event_before:7:20m",
        "selfremind:event_custom:7",
    }

    optional_expected = {
        "del:7",
        "del_one:7",
        "del_series:9",
        "del_cancel:7",
    }

    actual = set(generated)

    assert expected.issubset(actual)

    if hasattr(keyboards, "build_list_delete_keyboard") or hasattr(keyboards, "build_recurring_delete_choice_keyboard"):
        assert optional_expected.intersection(actual)
