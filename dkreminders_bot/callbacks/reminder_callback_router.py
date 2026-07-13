"""Router for reminder callback actions.

This module intentionally receives dependencies from main.py to keep the router
testable and avoid importing the application module back.
"""


async def handle_reminder_callback(update, context, deps):
    MSG_EVENT_DATE_NOT_FOUND = deps.MSG_EVENT_DATE_NOT_FOUND
    MSG_INVALID_REMINDER_ID = deps.MSG_INVALID_REMINDER_ID
    MSG_REMINDER_NOT_FOUND = deps.MSG_REMINDER_NOT_FOUND
    MSG_RESCHEDULE_BAD_DATETIME = deps.MSG_RESCHEDULE_BAD_DATETIME
    MSG_RESCHEDULE_PAST_TIME = deps.MSG_RESCHEDULE_PAST_TIME
    MSG_RESCHEDULE_UNKNOWN_ACTION = deps.MSG_RESCHEDULE_UNKNOWN_ACTION
    MSG_SOURCE_REMINDER_NOT_FOUND = deps.MSG_SOURCE_REMINDER_NOT_FOUND
    MSG_UNEXPECTED_CALLBACK_ERROR = deps.MSG_UNEXPECTED_CALLBACK_ERROR
    MSG_UNKNOWN_SELF_REMIND_MODE = deps.MSG_UNKNOWN_SELF_REMIND_MODE
    MSG_UNKNOWN_TIME_OPTION = deps.MSG_UNKNOWN_TIME_OPTION
    MSG_USER_CONTEXT_MISSING = deps.MSG_USER_CONTEXT_MISSING
    TZ = deps.TZ
    add_reminder = deps.add_reminder
    apply_snooze_to_reminder = deps.apply_snooze_to_reminder
    build_created_reminder_actions_keyboard_for_reminder = deps.build_created_reminder_actions_keyboard_for_reminder
    build_custom_date_keyboard = deps.build_custom_date_keyboard
    build_custom_time_keyboard = deps.build_custom_time_keyboard
    build_self_remind_choice_keyboard = deps.build_self_remind_choice_keyboard
    build_self_remind_event_before_keyboard = deps.build_self_remind_event_before_keyboard
    build_self_remind_mode_keyboard = deps.build_self_remind_mode_keyboard
    build_snooze_keyboard = deps.build_snooze_keyboard
    clear_reminder_message_keyboards = deps.clear_reminder_message_keyboards
    compute_event_before_time = deps.compute_event_before_time
    compute_self_remind_time = deps.compute_self_remind_time
    compute_snooze_target_time = deps.compute_snooze_target_time
    datetime = deps.datetime
    delete_old_snoozed_reminder_messages = deps.delete_old_snoozed_reminder_messages
    delete_other_reminder_messages = deps.delete_other_reminder_messages
    enter_custom_snooze_flow = deps.enter_custom_snooze_flow
    enter_custom_snooze_time_picker = deps.enter_custom_snooze_time_picker
    extract_event_datetime_from_text = deps.extract_event_datetime_from_text
    format_completed_reminder_text = deps.format_completed_reminder_text
    format_created_reminder_text = deps.format_created_reminder_text
    format_self_remind_text = deps.format_self_remind_text
    format_snoozed_answer_text = deps.format_snoozed_answer_text
    format_snoozed_reminder_text = deps.format_snoozed_reminder_text
    get_now = deps.get_now
    get_reminder = deps.get_reminder
    get_self_remind_event_base = deps.get_self_remind_event_base
    get_source_chat_title_for_self_remind = deps.get_source_chat_title_for_self_remind
    get_user_chat_id_by_user_id = deps.get_user_chat_id_by_user_id
    get_user_default_time = deps.get_user_default_time
    handle_custom_snooze_cancel = deps.handle_custom_snooze_cancel
    handle_custom_snooze_picktime = deps.handle_custom_snooze_picktime
    handle_direct_snooze_action = deps.handle_direct_snooze_action
    handle_done_callback = deps.handle_done_callback
    handle_done_callback_data = deps.handle_done_callback_data
    handle_noop_callback = deps.handle_noop_callback
    handle_pastdate_callback = deps.handle_pastdate_callback
    handle_self_remind_ask = deps.handle_self_remind_ask
    handle_self_remind_back = deps.handle_self_remind_back
    handle_self_remind_calendar_month = deps.handle_self_remind_calendar_month
    handle_self_remind_calendar_today = deps.handle_self_remind_calendar_today
    handle_self_remind_cancel = deps.handle_self_remind_cancel
    handle_self_remind_cancel_callback = deps.handle_self_remind_cancel_callback
    handle_self_remind_cancel_personal = deps.handle_self_remind_cancel_personal
    handle_self_remind_event_before = deps.handle_self_remind_event_before
    handle_self_remind_event_cancel = deps.handle_self_remind_event_cancel
    handle_self_remind_event_cancel_callback = deps.handle_self_remind_event_cancel_callback
    handle_self_remind_event_custom = deps.handle_self_remind_event_custom
    handle_self_remind_mode = deps.handle_self_remind_mode
    handle_self_remind_pickdate = deps.handle_self_remind_pickdate
    handle_self_remind_picktime = deps.handle_self_remind_picktime
    handle_self_remind_set = deps.handle_self_remind_set
    handle_snooze_cancel_callback_data = deps.handle_snooze_cancel_callback_data
    handle_snooze_current_month_callback = deps.handle_snooze_current_month_callback
    logger = deps.logger
    mark_reminder_acked = deps.mark_reminder_acked
    normalize_relative_event_date_in_text = deps.normalize_relative_event_date_in_text
    parse_optional_int_callback_id = deps.parse_optional_int_callback_id
    parse_required_int_callback_id = deps.parse_required_int_callback_id
    parse_snooze_action_callback_data = deps.parse_snooze_action_callback_data
    parse_snooze_calendar_callback_data = deps.parse_snooze_calendar_callback_data
    parse_snooze_pickdate_callback_data = deps.parse_snooze_pickdate_callback_data
    parse_snooze_picktime_callback_data = deps.parse_snooze_picktime_callback_data
    show_custom_snooze_calendar = deps.show_custom_snooze_calendar

    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    try:
        if (
            data.startswith("snooze_pastdate:")
            or data.startswith("selfremind_pastdate:")
            or data.startswith("selfremind_event_pastdate:")
        ):
            await handle_pastdate_callback(query=query)
            return

        if data.startswith("selfremind:ask:"):
            await handle_self_remind_ask(
                data=data,
                query=query,
                context=context,
                parse_required_int_callback_id=parse_required_int_callback_id,
                get_user_chat_id_by_user_id=get_user_chat_id_by_user_id,
                get_reminder=get_reminder,
                get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
                build_self_remind_mode_keyboard=build_self_remind_mode_keyboard,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                msg_user_context_missing=MSG_USER_CONTEXT_MISSING,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
            )
            return

        if data.startswith("selfremind:cancel_personal:"):
            await handle_self_remind_cancel_personal(
                data=data,
                query=query,
                parse_required_int_callback_id=parse_required_int_callback_id,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
            )
            return

        if data.startswith("selfremind:back:"):
            await handle_self_remind_back(
                data=data,
                query=query,
                context=context,
                parse_required_int_callback_id=parse_required_int_callback_id,
                get_reminder=get_reminder,
                get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
                build_self_remind_mode_keyboard=build_self_remind_mode_keyboard,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
            )
            return

        if data.startswith("selfremind:mode:"):
            await handle_self_remind_mode(
                data=data,
                query=query,
                context=context,
                parse_required_int_callback_id=parse_required_int_callback_id,
                get_user_chat_id_by_user_id=get_user_chat_id_by_user_id,
                get_reminder=get_reminder,
                get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
                get_self_remind_event_base=get_self_remind_event_base,
                extract_event_datetime_from_text=extract_event_datetime_from_text,
                build_self_remind_choice_keyboard=build_self_remind_choice_keyboard,
                build_self_remind_event_before_keyboard=build_self_remind_event_before_keyboard,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                msg_user_context_missing=MSG_USER_CONTEXT_MISSING,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
                msg_event_date_not_found=MSG_EVENT_DATE_NOT_FOUND,
                msg_unknown_self_remind_mode=MSG_UNKNOWN_SELF_REMIND_MODE,
            )
            return

        if data.startswith("selfremind:event_custom:"):
            await handle_self_remind_event_custom(
                data=data,
                query=query,
                get_reminder=get_reminder,
                build_custom_date_keyboard=build_custom_date_keyboard,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
            )
            return

        if data.startswith("selfremind:event_before:"):
            await handle_self_remind_event_before(
                data=data,
                query=query,
                context=context,
                get_now=get_now,
                get_user_chat_id_by_user_id=get_user_chat_id_by_user_id,
                get_reminder=get_reminder,
                get_self_remind_event_base=get_self_remind_event_base,
                extract_event_datetime_from_text=extract_event_datetime_from_text,
                compute_event_before_time=compute_event_before_time,
                get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
                normalize_relative_event_date_in_text=normalize_relative_event_date_in_text,
                format_self_remind_text=format_self_remind_text,
                add_reminder=add_reminder,
                format_created_reminder_text=format_created_reminder_text,
                build_created_reminder_actions_keyboard_for_reminder=build_created_reminder_actions_keyboard_for_reminder,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                msg_user_context_missing=MSG_USER_CONTEXT_MISSING,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
                msg_event_date_not_found=MSG_EVENT_DATE_NOT_FOUND,
                msg_unknown_time_option=MSG_UNKNOWN_TIME_OPTION,
                msg_reschedule_past_time=MSG_RESCHEDULE_PAST_TIME,
            )
            return

        if data.startswith("selfremind:set:"):
            await handle_self_remind_set(
                data=data,
                query=query,
                context=context,
                get_now=get_now,
                get_user_chat_id_by_user_id=get_user_chat_id_by_user_id,
                get_reminder=get_reminder,
                compute_self_remind_time=compute_self_remind_time,
                get_user_default_time=get_user_default_time,
                get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
                format_self_remind_text=format_self_remind_text,
                add_reminder=add_reminder,
                build_custom_date_keyboard=build_custom_date_keyboard,
                format_created_reminder_text=format_created_reminder_text,
                build_created_reminder_actions_keyboard_for_reminder=build_created_reminder_actions_keyboard_for_reminder,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                msg_user_context_missing=MSG_USER_CONTEXT_MISSING,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
            )
            return

        if data.startswith("selfremind_cal:") or data.startswith("selfremind_event_cal:"):
            await handle_self_remind_calendar_month(
                data=data,
                query=query,
                build_custom_date_keyboard=build_custom_date_keyboard,
            )
            return

        if data.startswith("selfremind_caltoday:") or data.startswith("selfremind_event_caltoday:"):
            await handle_self_remind_calendar_today(
                data=data,
                query=query,
                get_today=lambda: datetime.now(TZ).date(),
                parse_required_int_callback_id=parse_required_int_callback_id,
                build_custom_date_keyboard=build_custom_date_keyboard,
            )
            return

        if data.startswith("selfremind_pickdate:") or data.startswith("selfremind_event_pickdate:"):
            await handle_self_remind_pickdate(
                data=data,
                query=query,
                parse_required_int_callback_id=parse_required_int_callback_id,
                build_custom_time_keyboard=build_custom_time_keyboard,
            )
            return

        if data.startswith("selfremind_picktime:") or data.startswith("selfremind_event_picktime:"):
            await handle_self_remind_picktime(
                data=data,
                query=query,
                context=context,
                tz=TZ,
                get_now=get_now,
                get_user_chat_id_by_user_id=get_user_chat_id_by_user_id,
                get_reminder=get_reminder,
                get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
                add_reminder=add_reminder,
                build_created_reminder_actions_keyboard_for_reminder=build_created_reminder_actions_keyboard_for_reminder,
                format_self_remind_text=format_self_remind_text,
                format_created_reminder_text=format_created_reminder_text,
                msg_user_context_missing=MSG_USER_CONTEXT_MISSING,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
                msg_reschedule_bad_datetime=MSG_RESCHEDULE_BAD_DATETIME,
                msg_reschedule_past_time=MSG_RESCHEDULE_PAST_TIME,
            )
            return

        if data.startswith("selfremind_event_cancel:"):
            await handle_self_remind_event_cancel_callback(
                data=data,
                query=query,
                parse_required_int_callback_id=parse_required_int_callback_id,
                handle_self_remind_event_cancel=handle_self_remind_event_cancel,
                get_reminder=get_reminder,
                get_self_remind_event_base=get_self_remind_event_base,
                extract_event_datetime_from_text=extract_event_datetime_from_text,
                build_self_remind_choice_keyboard=build_self_remind_choice_keyboard,
                build_self_remind_event_before_keyboard=build_self_remind_event_before_keyboard,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
            )
            return

        if data.startswith("selfremind_cancel:"):
            await handle_self_remind_cancel_callback(
                data=data,
                query=query,
                context=context,
                parse_required_int_callback_id=parse_required_int_callback_id,
                handle_self_remind_cancel=handle_self_remind_cancel,
                get_reminder=get_reminder,
                get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
                build_self_remind_choice_keyboard=build_self_remind_choice_keyboard,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                msg_source_reminder_not_found=MSG_SOURCE_REMINDER_NOT_FOUND,
            )
            return

        if data.startswith("done:"):
            await handle_done_callback_data(
                data=data,
                query=query,
                context=context,
                parse_optional_int_callback_id=parse_optional_int_callback_id,
                handle_done_callback=handle_done_callback,
                mark_reminder_acked=mark_reminder_acked,
                clear_reminder_message_keyboards=clear_reminder_message_keyboards,
                get_reminder=get_reminder,
                format_completed_reminder_text=format_completed_reminder_text,
                delete_old_snoozed_reminder_messages=delete_old_snoozed_reminder_messages,
                delete_other_reminder_messages=delete_other_reminder_messages,
            )
            return

        if data.startswith("snooze:"):
            rid, action = parse_snooze_action_callback_data(data)

            await handle_direct_snooze_action(
                reminder_id=rid,
                action=action,
                query=query,
                context=context,
                get_now=get_now,
                get_user_default_time=get_user_default_time,
                get_reminder=get_reminder,
                compute_snooze_target_time=compute_snooze_target_time,
                enter_custom_snooze_flow=enter_custom_snooze_flow,
                apply_snooze_to_reminder=apply_snooze_to_reminder,
                delete_old_snoozed_reminder_messages=delete_old_snoozed_reminder_messages,
                delete_other_reminder_messages=delete_other_reminder_messages,
                mark_reminder_acked=mark_reminder_acked,
                clear_reminder_message_keyboards=clear_reminder_message_keyboards,
                add_reminder=add_reminder,
                build_custom_date_keyboard=build_custom_date_keyboard,
                format_snoozed_reminder_text=format_snoozed_reminder_text,
                format_snoozed_answer_text=format_snoozed_answer_text,
                msg_reminder_not_found=MSG_REMINDER_NOT_FOUND,
                msg_reschedule_unknown_action=MSG_RESCHEDULE_UNKNOWN_ACTION,
            )
            return

        if data.startswith("snooze_cal:"):
            rid, year, month = parse_snooze_calendar_callback_data(data)

            await show_custom_snooze_calendar(
                reminder_id=rid,
                query=query,
                year=year,
                month=month,
                build_custom_date_keyboard=build_custom_date_keyboard,
            )
            return

        if data.startswith("snooze_caltoday:"):
            await handle_snooze_current_month_callback(
                data=data,
                query=query,
                get_today=lambda: datetime.now(TZ).date(),
                parse_required_int_callback_id=parse_required_int_callback_id,
                show_custom_snooze_calendar=show_custom_snooze_calendar,
                build_custom_date_keyboard=build_custom_date_keyboard,
            )
            return

        if data.startswith("snooze_pickdate:"):
            rid, date_str = parse_snooze_pickdate_callback_data(data)

            await enter_custom_snooze_time_picker(
                reminder_id=rid,
                date_str=date_str,
                query=query,
                mark_reminder_acked=mark_reminder_acked,
                build_custom_time_keyboard=build_custom_time_keyboard,
            )
            return

        if data.startswith("snooze_picktime:"):
            rid, date_str, time_str = parse_snooze_picktime_callback_data(data)

            await handle_custom_snooze_picktime(
                reminder_id=rid,
                date_str=date_str,
                time_str=time_str,
                query=query,
                context=context,
                tz=TZ,
                get_now=get_now,
                get_reminder=get_reminder,
                mark_reminder_acked=mark_reminder_acked,
                clear_reminder_message_keyboards=clear_reminder_message_keyboards,
                add_reminder=add_reminder,
                apply_snooze_to_reminder=apply_snooze_to_reminder,
                delete_old_snoozed_reminder_messages=delete_old_snoozed_reminder_messages,
                delete_other_reminder_messages=delete_other_reminder_messages,
                format_snoozed_reminder_text=format_snoozed_reminder_text,
                format_snoozed_answer_text=format_snoozed_answer_text,
                msg_reminder_not_found=MSG_REMINDER_NOT_FOUND,
                msg_reschedule_bad_datetime=MSG_RESCHEDULE_BAD_DATETIME,
                msg_reschedule_past_time=MSG_RESCHEDULE_PAST_TIME,
            )
            return

        if data.startswith("snooze_cancel:"):
            await handle_snooze_cancel_callback_data(
                data=data,
                query=query,
                parse_optional_int_callback_id=parse_optional_int_callback_id,
                handle_custom_snooze_cancel=handle_custom_snooze_cancel,
                mark_reminder_acked=mark_reminder_acked,
                build_snooze_keyboard=build_snooze_keyboard,
                msg_invalid_reminder_id=MSG_INVALID_REMINDER_ID,
                get_reminder=get_reminder,
            )
            return

        if data == "noop":
            await handle_noop_callback(query=query)
            return

    except Exception:
        logger.exception("Ошибка в snooze_callback")
        try:
            await query.answer(MSG_UNEXPECTED_CALLBACK_ERROR, show_alert=True)
        except Exception:
            pass
