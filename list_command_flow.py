"""Flow for the /list command.

The flow receives dependencies from main.py to keep this module independent
from application wiring and easy to test.
"""

from messages import msg_list_alias_not_found_known, msg_list_alias_not_found_no_aliases, msg_list_user_not_started


async def handle_list_command_flow(update, context, deps) -> None:
    Chat = deps.Chat
    DB_PATH = deps.DB_PATH
    sqlite3 = deps.sqlite3

    build_active_reminders_list_response = deps.build_active_reminders_list_response
    build_list_delete_keyboard = deps.build_list_delete_keyboard
    build_target_user_presentation_rows = deps.build_target_user_presentation_rows
    build_target_user_reminders_list_response = deps.build_target_user_reminders_list_response
    format_empty_active_reminders_list_text = deps.format_empty_active_reminders_list_text
    get_active_reminders_created_by_for_chat = deps.get_active_reminders_created_by_for_chat
    get_all_aliases = deps.get_all_aliases
    get_chat_id_by_alias_for_user = deps.get_chat_id_by_alias_for_user
    get_now = deps.get_now
    get_private_chat_id_by_username = deps.get_private_chat_id_by_username
    get_recurring_template = deps.get_recurring_template
    get_user_alias_chat_id_for_user = deps.get_user_alias_chat_id_for_user
    safe_reply = deps.safe_reply

    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    target_chat_id = chat.id
    used_alias = None

    # ===== НОВЫЙ РЕЖИМ: /list @username (только в личке) =====
    if chat.type == Chat.PRIVATE and context.args:
        first_arg = context.args[0].strip()

        if first_arg.startswith("@"):
            owner_chat_id = get_private_chat_id_by_username(first_arg)

            if owner_chat_id is None:
                await safe_reply(
                    message,
                    msg_list_user_not_started(first_arg)
                )
                return

            rows = get_active_reminders_created_by_for_chat(
                chat_id=owner_chat_id,
                created_by=user.id,
            )

            presentation_rows = build_target_user_presentation_rows(
                rows,
                recurring_template_loader=get_recurring_template,
            )

            reply, ids, keyboard = build_target_user_reminders_list_response(
                presentation_rows,
                target_label=first_arg,
                list_delete_keyboard_builder=build_list_delete_keyboard,
            )

            if not ids:
                await safe_reply(message, reply)
                return

            context.user_data["list_ids"] = ids
            context.user_data["list_chat_id"] = owner_chat_id

            await safe_reply(
                message,
                reply,
                reply_markup=keyboard,
            )
            return

    # ===== /list alias: сначала user-alias, потом chat-alias =====
    if chat.type == Chat.PRIVATE and context.args:
        alias = context.args[0].strip()
        if alias:
            user_alias_chat_id = get_user_alias_chat_id_for_user(alias, user.id)
            if user_alias_chat_id is not None:
                rows = get_active_reminders_created_by_for_chat(
                    chat_id=user_alias_chat_id,
                    created_by=user.id,
                )

                presentation_rows = build_target_user_presentation_rows(
                    rows,
                    recurring_template_loader=get_recurring_template,
                )

                reply, ids, keyboard = build_target_user_reminders_list_response(
                    presentation_rows,
                    target_label=alias,
                    list_delete_keyboard_builder=build_list_delete_keyboard,
                )

                if not ids:
                    await safe_reply(message, reply)
                    return

                context.user_data["list_ids"] = ids
                context.user_data["list_chat_id"] = user_alias_chat_id

                await safe_reply(
                    message,
                    reply,
                    reply_markup=keyboard,
                )
                return

            alias_chat_id = get_chat_id_by_alias_for_user(alias, user.id)
            if alias_chat_id is None:
                aliases = get_all_aliases(user.id)
                if not aliases:
                    await safe_reply(
                        message,
                        msg_list_alias_not_found_no_aliases(alias)
                    )
                else:
                    known = ", ".join(a for a, _, _ in aliases)
                    await safe_reply(
                        message,
                        msg_list_alias_not_found_known(alias, known)
                    )
                return

            target_chat_id = alias_chat_id
            used_alias = alias

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("PRAGMA table_info(reminders)", ())
    reminder_cols = {row[1] for row in c.fetchall()}
    c.execute("PRAGMA table_info(recurring_templates)", ())
    template_cols = {row[1] for row in c.fetchall()}
    if "timezone_name" in reminder_cols and "timezone_name" in template_cols:
        timezone_select = "COALESCE(r.timezone_name, rt.timezone_name) AS timezone_name"
    elif "timezone_name" in reminder_cols:
        timezone_select = "r.timezone_name AS timezone_name"
    elif "timezone_name" in template_cols:
        timezone_select = "rt.timezone_name AS timezone_name"
    else:
        timezone_select = "NULL AS timezone_name"

    c.execute(
        f"""
        SELECT
            r.id,
            r.text,
            r.remind_at,
            r.template_id,
            rt.pattern_type,
            rt.payload,
            {timezone_select}
        FROM reminders r
        LEFT JOIN recurring_templates rt ON rt.id = r.template_id
        WHERE r.chat_id = ? AND r.delivered = 0
        ORDER BY r.remind_at ASC
        """,
        (target_chat_id,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        await safe_reply(
            message,
            format_empty_active_reminders_list_text(chat_alias=used_alias),
        )
        return

    header = f"Активные напоминания для чата '{used_alias}':" if used_alias else "Активные напоминания:"
    reply, ids, keyboard = build_active_reminders_list_response(
        rows,
        header=header,
        now_local=get_now(),
        list_delete_keyboard_builder=build_list_delete_keyboard,
    )

    context.user_data["list_ids"] = ids
    context.user_data["list_chat_id"] = target_chat_id

    await safe_reply(message, reply, reply_markup=keyboard)
