"""Router for created reminder snooze callback actions.

This module receives dependencies from main.py to avoid importing the
application module back.
"""

from messages import MSG_PICK_TIME, MSG_RETURNED_OPTIONS, msg_created_snoozed, msg_created_snoozed_answer


async def handle_created_snooze_callback(update, context, deps) -> None:
    MSG_INVALID_REMINDER_ID = deps.MSG_INVALID_REMINDER_ID
    MSG_RESCHEDULE_BAD_DATETIME = deps.MSG_RESCHEDULE_BAD_DATETIME
    MSG_RESCHEDULE_PAST_TIME = deps.MSG_RESCHEDULE_PAST_TIME
    MSG_RESCHEDULE_UNKNOWN_ACTION = deps.MSG_RESCHEDULE_UNKNOWN_ACTION
    MSG_UNEXPECTED_CALLBACK_ERROR = deps.MSG_UNEXPECTED_CALLBACK_ERROR
    TZ = deps.TZ
    _answer_created_action_reminder_missing = deps._answer_created_action_reminder_missing
    _ensure_created_action_reminder_exists = deps._ensure_created_action_reminder_exists
    build_created_reminder_actions_keyboard_for_reminder = deps.build_created_reminder_actions_keyboard_for_reminder
    build_created_reschedule_keyboard = deps.build_created_reschedule_keyboard
    build_custom_date_keyboard = deps.build_custom_date_keyboard
    build_custom_time_keyboard = deps.build_custom_time_keyboard
    compute_snooze_target_time = deps.compute_snooze_target_time
    datetime = deps.datetime
    get_now = deps.get_now
    get_reminder = deps.get_reminder
    get_user_default_time = deps.get_user_default_time
    logger = deps.logger
    update_reminder_time = deps.update_reminder_time

    query = update.callback_query
    if query is None:
        return

    data = query.data or ""

    try:
        if data.startswith("created_snooze:"):
            _, rid_str, action = data.split(":", 2)
            rid = int(rid_str)

            r = get_reminder(rid)
            if not r:
                await _answer_created_action_reminder_missing(query)
                return

            try:
                new_dt = compute_snooze_target_time(action, get_now(), default_time=get_user_default_time(getattr(getattr(query, 'from_user', None), 'id', None)))
            except ValueError:
                await query.answer(MSG_RESCHEDULE_UNKNOWN_ACTION, show_alert=True)
                return

            if not update_reminder_time(rid, new_dt):
                await _answer_created_action_reminder_missing(query)
                return

            when_str = new_dt.strftime("%d.%m %H:%M")
            await query.edit_message_text(
                msg_created_snoozed(when_str, r.text),
                reply_markup=build_created_reminder_actions_keyboard_for_reminder(rid),
            )
            await query.answer(msg_created_snoozed_answer(when_str))
            return

        if data.startswith("created_snooze_cal:"):
            _, rid_str, ym = data.split(":", 2)
            rid = int(rid_str)
            if not await _ensure_created_action_reminder_exists(query, rid):
                return

            year_str, month_str = ym.split("-", 1)
            keyboard = build_custom_date_keyboard(
                rid,
                year=int(year_str),
                month=int(month_str),
                callback_prefix="created_snooze",
            )
            await query.edit_message_reply_markup(reply_markup=keyboard)
            await query.answer()
            return

        if data.startswith("created_snooze_caltoday:"):
            _, rid_str = data.split(":", 1)
            rid = int(rid_str)
            if not await _ensure_created_action_reminder_exists(query, rid):
                return

            today = get_now().date()
            keyboard = build_custom_date_keyboard(
                rid,
                year=today.year,
                month=today.month,
                callback_prefix="created_snooze",
            )
            await query.edit_message_reply_markup(reply_markup=keyboard)
            await query.answer()
            return

        if data.startswith("created_snooze_pickdate:"):
            _, rid_str, date_str = data.split(":", 2)
            rid = int(rid_str)
            if not await _ensure_created_action_reminder_exists(query, rid):
                return

            keyboard = build_custom_time_keyboard(
                rid,
                date_str,
                callback_prefix="created_snooze",
            )
            await query.edit_message_reply_markup(reply_markup=keyboard)
            await query.answer(MSG_PICK_TIME)
            return

        if data.startswith("created_snooze_pastdate:"):
            await query.answer(MSG_RESCHEDULE_PAST_TIME, show_alert=True)
            return

        if data.startswith("created_snooze_picktime:"):
            _, rid_str, date_str, time_str = data.split(":", 3)
            rid = int(rid_str)

            r = get_reminder(rid)
            if not r:
                await _answer_created_action_reminder_missing(query)
                return

            try:
                year, month, day = map(int, date_str.split("-"))
                hour, minute = map(int, time_str.split(":"))
                new_dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
            except Exception:
                await query.answer(MSG_RESCHEDULE_BAD_DATETIME, show_alert=True)
                return

            if new_dt <= get_now():
                await query.answer(MSG_RESCHEDULE_PAST_TIME, show_alert=True)
                return

            if not update_reminder_time(rid, new_dt):
                await _answer_created_action_reminder_missing(query)
                return

            when_str = new_dt.strftime("%d.%m %H:%M")
            await query.edit_message_text(
                msg_created_snoozed(when_str, r.text),
                reply_markup=build_created_reminder_actions_keyboard_for_reminder(rid),
            )
            await query.answer(msg_created_snoozed_answer(when_str))
            return

        if data.startswith("created_snooze_cancel:"):
            _, rid_str = data.split(":", 1)
            rid = int(rid_str)
            if not await _ensure_created_action_reminder_exists(query, rid):
                return

            await query.edit_message_reply_markup(reply_markup=build_created_reschedule_keyboard(rid))
            await query.answer(MSG_RETURNED_OPTIONS)
            return

    except ValueError:
        await query.answer(MSG_INVALID_REMINDER_ID, show_alert=True)
        return
    except Exception:
        logger.exception("Ошибка в created_snooze_callback")
        try:
            await query.answer(MSG_UNEXPECTED_CALLBACK_ERROR, show_alert=True)
        except Exception:
            pass
