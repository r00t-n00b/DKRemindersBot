"""Callback data prefixes and handler regex contracts.

Keep callback families centralized here so button builders and handler
registration do not drift apart.
"""

# Raw prefixes used in callback_data.
NOOP = "noop"
UNDO = "undo"
DONE = "done"

SNOOZE = "snooze"
SNOOZE_CAL = "snooze_cal"
SNOOZE_CALTODAY = "snooze_caltoday"
SNOOZE_PASTDATE = "snooze_pastdate"
SNOOZE_PICKDATE = "snooze_pickdate"
SNOOZE_PICKTIME = "snooze_picktime"
SNOOZE_CANCEL = "snooze_cancel"

CREATED_COMPLETE = "created_complete"
CREATED_DELETE = "created_delete"
CREATED_SNOOZE = "created_snooze"
CREATED_SNOOZE_CUSTOM = "created_snooze_custom"
CREATED_SNOOZE_CAL = "created_snooze_cal"
CREATED_SNOOZE_CALTODAY = "created_snooze_caltoday"
CREATED_SNOOZE_PASTDATE = "created_snooze_pastdate"
CREATED_SNOOZE_PICKDATE = "created_snooze_pickdate"
CREATED_SNOOZE_PICKTIME = "created_snooze_picktime"
CREATED_SNOOZE_CANCEL = "created_snooze_cancel"

SELFREMIND = "selfremind"

DELETE_ONE = "del_one"
DELETE_SERIES = "del_series"
DELETE_CANCEL = "del_cancel"


# Regex contracts used by CallbackQueryHandler.
NOOP_PATTERN = r"^noop$"
UNDO_PATTERN = r"^undo:"
DONE_PATTERN = r"^done:"

DELETE_CHOICE_PATTERN = r"^del_(one|series|cancel):"

SELFREMIND_PATTERN = r"^selfremind:"
SELFREMIND_EVENT_CUSTOM_PATTERN = r"^selfremind:event_custom:\d+$"

CREATED_SNOOZE_PATTERN = (
    r"^created_snooze(:|_cal:|_caltoday:|_pastdate:|_pickdate:|_picktime:|_cancel:)"
)
CREATED_SNOOZE_CUSTOM_PATTERN = r"^created_snooze_custom:\d+$"

CREATED_COMPLETE_PATTERN = r"^created_complete:"
CREATED_DELETE_PATTERN = r"^created_delete:"

SNOOZE_PATTERN = (
    r"^("
    r"snooze:"
    r"|snooze_cal:"
    r"|snooze_caltoday:"
    r"|snooze_pastdate:"
    r"|snooze_pickdate:"
    r"|snooze_picktime:"
    r"|snooze_cancel:"
    r"|noop$"
    r"|done:"
    r"|selfremind:ask:"
    r"|selfremind:back:"
    r"|selfremind:set:"
    r"|selfremind:mode:"
    r"|selfremind:cancel_personal:"
    r"|selfremind:event_before:"
    r"|selfremind:event_custom:"
    r"|selfremind:"
    r"|selfremind_cal:"
    r"|selfremind_caltoday:"
    r"|selfremind_pickdate:"
    r"|selfremind_picktime:"
    r"|selfremind_cancel:"
    r")"
)
SNOOZE_CUSTOM_PATTERN = r"^snooze_custom:\d+$"
SNOOZE_CALENDAR_PATTERN = r"^snooze_(cal|caltoday|pastdate|pickdate|picktime|cancel):"
