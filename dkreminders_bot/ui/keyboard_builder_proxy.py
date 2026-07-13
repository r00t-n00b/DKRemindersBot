"""Proxy wrappers around keyboard builder functions.

The concrete Telegram classes are injected from main at runtime/test time.
"""

from __future__ import annotations

from typing import Optional


_DEP_NAMES = (
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "get_reminder",
    "get_user_default_time",
    "keyboard_builders",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        if name == "get_user_default_time" and not hasattr(deps, name):
            globals()[name] = lambda user_id: None
        else:
            globals()[name] = getattr(deps, name)


def _default_time_for_reminder_id(reminder_id: int):
    reminder = get_reminder(reminder_id)
    if reminder is None:
        return None
    return get_user_default_time(getattr(reminder, "created_by", None))


def _call_builder_with_optional_default_time(builder, reminder_id: int, default_time):
    try:
        return builder(reminder_id, default_time=default_time)
    except TypeError as exc:
        # Backward-compatible for old tests/fakes that still expose
        # build_xxx_keyboard(reminder_id) without default_time.
        if "default_time" in str(exc) or "unexpected keyword argument" in str(exc):
            return builder(reminder_id)
        raise


def build_created_reminder_actions_keyboard_for_reminder_impl(reminder_id: int, *, deps) -> Optional[InlineKeyboardMarkup]:
    _apply_deps(deps)
    reminder = get_reminder(reminder_id)
    if reminder is None:
        return None
    is_recurring = bool(getattr(reminder, 'template_id', None))
    return build_created_reminder_actions_keyboard_impl(reminder_id, is_recurring=is_recurring, deps=deps)


def _sync_keyboard_builder_classes_impl(*, deps) -> None:
    _apply_deps(deps)
    keyboard_builders.InlineKeyboardButton = InlineKeyboardButton
    keyboard_builders.InlineKeyboardMarkup = InlineKeyboardMarkup


def build_list_delete_keyboard_impl(reminder_id: int, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return keyboard_builders.build_list_delete_keyboard(reminder_id)


def build_recurring_delete_choice_keyboard_impl(reminder_id: int, template_id: int, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return keyboard_builders.build_recurring_delete_choice_keyboard(reminder_id, template_id)


def build_created_reminder_actions_keyboard_impl(reminder_id: int, is_recurring: bool=False, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return keyboard_builders.build_created_reminder_actions_keyboard(reminder_id, is_recurring=is_recurring)


def build_created_reschedule_keyboard_impl(reminder_id: int, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return _call_builder_with_optional_default_time(
        keyboard_builders.build_created_reschedule_keyboard,
        reminder_id,
        _default_time_for_reminder_id(reminder_id),
    )


def build_snooze_keyboard_impl(reminder_id: int, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return _call_builder_with_optional_default_time(
        keyboard_builders.build_snooze_keyboard,
        reminder_id,
        _default_time_for_reminder_id(reminder_id),
    )


def build_group_reminder_keyboard_impl(reminder_id: int, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return keyboard_builders.build_group_reminder_keyboard(reminder_id)


def build_self_remind_mode_keyboard_impl(reminder_id: int, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return keyboard_builders.build_self_remind_mode_keyboard(reminder_id)


def build_self_remind_choice_keyboard_impl(reminder_id: int, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return _call_builder_with_optional_default_time(
        keyboard_builders.build_self_remind_choice_keyboard,
        reminder_id,
        _default_time_for_reminder_id(reminder_id),
    )


def build_self_remind_event_before_keyboard_impl(reminder_id: int, *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return keyboard_builders.build_self_remind_event_before_keyboard(reminder_id)


def build_custom_date_keyboard_impl(reminder_id: int, year: Optional[int]=None, month: Optional[int]=None, callback_prefix: str='snooze', *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return keyboard_builders.build_custom_date_keyboard(reminder_id, year=year, month=month, callback_prefix=callback_prefix)


def build_custom_time_keyboard_impl(reminder_id: int, date_str: str, callback_prefix: str='snooze', *, deps):
    _apply_deps(deps)
    _sync_keyboard_builder_classes_impl(deps=deps)
    return keyboard_builders.build_custom_time_keyboard(reminder_id, date_str, callback_prefix=callback_prefix)
