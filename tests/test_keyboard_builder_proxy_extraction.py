from types import SimpleNamespace

import dkreminders_bot.ui.keyboard_builder_proxy as keyboard_builder_proxy


TARGETS = [
    "build_created_reminder_actions_keyboard_for_reminder",
    "_sync_keyboard_builder_classes",
    "build_list_delete_keyboard",
    "build_recurring_delete_choice_keyboard",
    "build_created_reminder_actions_keyboard",
    "build_created_reschedule_keyboard",
    "build_snooze_keyboard",
    "build_group_reminder_keyboard",
    "build_self_remind_mode_keyboard",
    "build_self_remind_choice_keyboard",
    "build_self_remind_event_before_keyboard",
    "build_custom_date_keyboard",
    "build_custom_time_keyboard",
]


class FakeButton:
    pass


class FakeMarkup:
    pass


class FakeKeyboardBuilders:
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None

    def build_list_delete_keyboard(self, reminder_id):
        return ("list_delete", reminder_id)

    def build_recurring_delete_choice_keyboard(self, reminder_id, template_id):
        return ("recurring_delete_choice", reminder_id, template_id)

    def build_created_reminder_actions_keyboard(self, reminder_id, is_recurring=False):
        return ("created_actions", reminder_id, is_recurring)

    def build_created_reschedule_keyboard(self, reminder_id):
        return ("created_reschedule", reminder_id)

    def build_snooze_keyboard(self, reminder_id):
        return ("snooze", reminder_id)

    def build_group_reminder_keyboard(self, reminder_id):
        return ("group", reminder_id)

    def build_self_remind_mode_keyboard(self, reminder_id):
        return ("self_mode", reminder_id)

    def build_self_remind_choice_keyboard(self, reminder_id):
        return ("self_choice", reminder_id)

    def build_self_remind_event_before_keyboard(self, reminder_id):
        return ("self_event_before", reminder_id)

    def build_custom_date_keyboard(self, reminder_id, year=None, month=None, callback_prefix="snooze"):
        return ("custom_date", reminder_id, year, month, callback_prefix)

    def build_custom_time_keyboard(self, reminder_id, date_str, callback_prefix="snooze"):
        return ("custom_time", reminder_id, date_str, callback_prefix)


def _deps(reminder=None):
    builders = FakeKeyboardBuilders()
    return SimpleNamespace(
        InlineKeyboardButton=FakeButton,
        InlineKeyboardMarkup=FakeMarkup,
        keyboard_builders=builders,
        get_reminder=lambda reminder_id: reminder,
    )


def test_keyboard_builder_proxy_wrappers_in_main_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    for name in TARGETS:
        matches = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]

        assert len(matches) == 1

        node = matches[0]
        node_source = ast.get_source_segment(source, node)

        if name == "build_created_reminder_actions_keyboard_for_reminder":
            assert "get_reminder(reminder_id)" in node_source
            assert "build_created_reminder_actions_keyboard(" in node_source
            assert "build_created_reminder_actions_keyboard_for_reminder_impl" not in node_source
        else:
            assert f"{name}_impl(" in node_source
            assert "deps=_build_keyboard_builder_proxy_deps()" in node_source

        assert node.end_lineno - node.lineno + 1 <= 3


def test_keyboard_builder_proxy_module_contains_impls_and_no_main_import():
    source = open("dkreminders_bot/ui/keyboard_builder_proxy.py").read()

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_keyboard_builder_proxy_syncs_classes():
    deps = _deps()

    keyboard_builder_proxy._sync_keyboard_builder_classes_impl(deps=deps)

    assert deps.keyboard_builders.InlineKeyboardButton is FakeButton
    assert deps.keyboard_builders.InlineKeyboardMarkup is FakeMarkup


def test_keyboard_builder_proxy_simple_builders_delegate():
    deps = _deps()

    assert keyboard_builder_proxy.build_list_delete_keyboard_impl(1, deps=deps) == ("list_delete", 1)
    assert keyboard_builder_proxy.build_recurring_delete_choice_keyboard_impl(1, 2, deps=deps) == ("recurring_delete_choice", 1, 2)
    assert keyboard_builder_proxy.build_created_reminder_actions_keyboard_impl(1, True, deps=deps) == ("created_actions", 1, True)
    assert keyboard_builder_proxy.build_created_reschedule_keyboard_impl(1, deps=deps) == ("created_reschedule", 1)
    assert keyboard_builder_proxy.build_snooze_keyboard_impl(1, deps=deps) == ("snooze", 1)
    assert keyboard_builder_proxy.build_group_reminder_keyboard_impl(1, deps=deps) == ("group", 1)
    assert keyboard_builder_proxy.build_self_remind_mode_keyboard_impl(1, deps=deps) == ("self_mode", 1)
    assert keyboard_builder_proxy.build_self_remind_choice_keyboard_impl(1, deps=deps) == ("self_choice", 1)
    assert keyboard_builder_proxy.build_self_remind_event_before_keyboard_impl(1, deps=deps) == ("self_event_before", 1)


def test_keyboard_builder_proxy_custom_builders_delegate_with_prefixes():
    deps = _deps()

    assert keyboard_builder_proxy.build_custom_date_keyboard_impl(
        1,
        year=2026,
        month=6,
        callback_prefix="created_snooze",
        deps=deps,
    ) == ("custom_date", 1, 2026, 6, "created_snooze")

    assert keyboard_builder_proxy.build_custom_time_keyboard_impl(
        1,
        "2026-06-24",
        callback_prefix="created_snooze",
        deps=deps,
    ) == ("custom_time", 1, "2026-06-24", "created_snooze")


def test_keyboard_builder_proxy_created_actions_for_reminder_handles_missing_and_recurring():
    assert keyboard_builder_proxy.build_created_reminder_actions_keyboard_for_reminder_impl(
        1,
        deps=_deps(reminder=None),
    ) is None

    one_off = SimpleNamespace(template_id=None)
    recurring = SimpleNamespace(template_id=123)

    assert keyboard_builder_proxy.build_created_reminder_actions_keyboard_for_reminder_impl(
        1,
        deps=_deps(reminder=one_off),
    ) == ("created_actions", 1, False)

    assert keyboard_builder_proxy.build_created_reminder_actions_keyboard_for_reminder_impl(
        1,
        deps=_deps(reminder=recurring),
    ) == ("created_actions", 1, True)
