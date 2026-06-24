"""Created reminder action callbacks shared by reschedule/snooze flows."""


def _apply_deps(deps) -> None:
    globals()["MSG_INVALID_REMINDER_ID"] = deps.MSG_INVALID_REMINDER_ID
    globals()["MSG_REMINDER_NOT_FOUND"] = deps.MSG_REMINDER_NOT_FOUND
    globals()["MSG_RESCHEDULE_OPEN_FAILED_TEXT"] = deps.MSG_RESCHEDULE_OPEN_FAILED_TEXT
    globals()["build_created_reminder_actions_keyboard_for_reminder"] = deps.build_created_reminder_actions_keyboard_for_reminder
    globals()["build_created_reschedule_keyboard"] = deps.build_created_reschedule_keyboard
    globals()["build_custom_date_keyboard"] = deps.build_custom_date_keyboard
    globals()["get_reminder"] = deps.get_reminder
    globals()["logger"] = deps.logger


async def answer_created_action_reminder_missing_impl(query, deps) -> None:
    _apply_deps(deps)

    await query.answer(MSG_REMINDER_NOT_FOUND, show_alert=True)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("Failed to clear created-action keyboard for missing reminder")


async def ensure_created_action_reminder_exists_impl(query, reminder_id: int, deps) -> bool:
    _apply_deps(deps)

    if get_reminder(reminder_id) is not None:
        return True
    await deps.answer_created_action_reminder_missing(query)
    return False


async def handle_created_reschedule_callback(update, context, deps) -> None:
    _apply_deps(deps)

    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_RESCHEDULE_OPEN_FAILED_TEXT, show_alert=True)
        await query.edit_message_text(MSG_RESCHEDULE_OPEN_FAILED_TEXT, reply_markup=None)
        return

    if not await deps.ensure_created_action_reminder_exists(query, reminder_id):
        return

    await query.answer()
    await query.edit_message_reply_markup(reply_markup=build_created_reschedule_keyboard(reminder_id))


async def handle_created_snooze_custom_callback(update, context, deps) -> None:
    _apply_deps(deps)

    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
        return

    if not await deps.ensure_created_action_reminder_exists(query, reminder_id):
        return

    keyboard = build_custom_date_keyboard(reminder_id, callback_prefix="created_snooze")

    await query.edit_message_reply_markup(reply_markup=keyboard)
    await query.answer("Выбери дату")
    return


async def handle_created_snooze_cancel_callback(update, context, deps) -> None:
    _apply_deps(deps)

    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
        return

    if not await deps.ensure_created_action_reminder_exists(query, reminder_id):
        return

    await query.edit_message_reply_markup(reply_markup=build_created_reschedule_keyboard(reminder_id))
    await query.answer("Вернул варианты")
    return


async def handle_created_back_callback(update, context, deps) -> None:
    _apply_deps(deps)

    query = update.callback_query

    try:
        reminder_id = int(query.data.split(":", 1)[1])
    except Exception:
        await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if not await deps.ensure_created_action_reminder_exists(query, reminder_id):
        return

    await query.answer()
    await query.edit_message_reply_markup(
        reply_markup=build_created_reminder_actions_keyboard_for_reminder(reminder_id)
    )
