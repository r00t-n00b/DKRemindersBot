"""Delete and undo callback flows.

This module receives dependencies from main.py to avoid importing the
application module back.
"""

from typing import Any, Dict, List, Optional


_DEP_NAMES = [
    "CTX",
    "DB_PATH",
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "MSG_DELETE_FAILED_SHORT",
    "MSG_DELETE_SERIES_FAILED",
    "MSG_REMINDER_ALREADY_DELETED_ALERT",
    "MSG_UNDO_EXPIRED",
    "MSG_UNDO_RESTORE_FAILED",
    "Update",
    "build_active_reminders_list_response",
    "build_created_reminder_actions_keyboard",
    "build_created_reminder_actions_keyboard_for_reminder",
    "build_list_delete_keyboard",
    "build_recurring_delete_choice_keyboard",
    "cb_undo",
    "datetime",
    "delete_recurring_one_instance_and_reschedule",
    "delete_recurring_series_with_snapshot",
    "delete_single_reminder_with_snapshot",
    "dict",
    "format_deleted_human",
    "format_deleted_snapshot_text",
    "format_recurring_human",
    "format_restored_series_text",
    "format_restored_single_text",
    "get_now",
    "get_recurring_template_row",
    "get_reminder_row",
    "list",
    "logger",
    "make_undo_token",
    "restore_deleted_snapshot",
    "sqlite3",
]


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _build_active_list_response_for_ids(ids, deps):
    _apply_deps(deps)
    if not ids:
        return "Напоминаний больше нет.", None, ids

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    qmarks = ",".join("?" for _ in ids)
    c.execute(
        f"""
        SELECT
            r.id,
            r.text,
            r.remind_at,
            r.template_id,
            rt.pattern_type,
            rt.payload
        FROM reminders r
        LEFT JOIN recurring_templates rt ON rt.id = r.template_id
        WHERE r.id IN ({qmarks})
        ORDER BY r.remind_at ASC
        """,
        ids,
    )
    rows = c.fetchall()
    conn.close()

    reply, rebuilt_ids, keyboard = build_active_reminders_list_response(
        rows,
        header="Активные напоминания:",
        now_local=get_now(),
        list_delete_keyboard_builder=build_list_delete_keyboard,
)
    return reply, keyboard, rebuilt_ids


async def _edit_stored_list_message_after_delete(context, ids, deps):
    _apply_deps(deps)
    ref = context.user_data.get("list_message_ref") or {}
    chat_id = ref.get("chat_id")
    message_id = ref.get("message_id")

    if chat_id is None or message_id is None:
        return

    reply, keyboard, rebuilt_ids = _build_active_list_response_for_ids(ids, deps)
    context.user_data["list_ids"] = rebuilt_ids

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=reply,
        reply_markup=keyboard,
    )


async def handle_delete_callback(update, context, deps) -> None:
    _apply_deps(deps)
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    if not data.startswith("del:"):
        return

    try:
        idx = int(data.split(":", 1)[1])
    except ValueError:
        return

    ids: List[int] = context.user_data.get("list_ids") or []
    if idx < 1 or idx > len(ids):
        await query.answer("Не нашел такое напоминание", show_alert=True)
        return

    rid = int(ids[idx - 1])

    target_chat_id = context.user_data.get("list_chat_id")
    if target_chat_id is None:
        chat = query.message.chat if query.message else None
        if chat is None:
            return
        target_chat_id = chat.id

    r = get_reminder_row(rid)
    if not r:
        await query.answer(MSG_REMINDER_ALREADY_DELETED_ALERT, show_alert=True)
        return

    # Если recurring - спрашиваем режим удаления
    tpl_id = r.get("template_id")
    if tpl_id is not None:
        tpl = get_recurring_template_row(int(tpl_id)) or {}
        tpl_pattern_type = tpl.get("pattern_type")
        tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}
        human = format_recurring_human(tpl_pattern_type, tpl_payload)

        dt = datetime.fromisoformat(str(r["remind_at"]))
        ts = dt.strftime("%d.%m %H:%M")
        title = str(r.get("text") or "")
        suffix = f"  🔁 {human}" if human else "  🔁"
        preview = f"{ts} - {title}{suffix}"

        kb = build_recurring_delete_choice_keyboard(rid, int(tpl_id))

        context.user_data["delete_choice_source"] = "list"
        if query.message:
            context.user_data["list_message_ref"] = {
                "chat_id": query.message.chat.id,
                "message_id": query.message.message_id,
            }
            await query.message.reply_text(
                "Это повторяющееся напоминание. Как удалить?\n\n" + preview,
                reply_markup=kb,
            )
        return

    # НЕ recurring - удаляем сразу + undo
    snapshot = delete_single_reminder_with_snapshot(rid, int(target_chat_id))
    if not snapshot:
        await query.answer(MSG_REMINDER_ALREADY_DELETED_ALERT, show_alert=True)
        return

    ids.pop(idx - 1)
    context.user_data["list_ids"] = ids

    if query.message:
        reply, keyboard, ids = _build_active_list_response_for_ids(ids, deps)
        context.user_data["list_ids"] = ids
        await query.edit_message_text(reply, reply_markup=keyboard)

    tpl = snapshot.get("template") or {}
    tpl_pattern_type = tpl.get("pattern_type")
    tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}

    deleted_text = format_deleted_human(
        snapshot["reminder"]["remind_at"],
        snapshot["reminder"]["text"],
        tpl_pattern_type,
        tpl_payload,
    )

    token = make_undo_token()
    context.user_data["undo_tokens"] = context.user_data.get("undo_tokens") or {}
    context.user_data["undo_tokens"][token] = snapshot

    undo_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("↩️ Вернуть ремайндер", callback_data=cb_undo(token))]]
    )

    if query.message:
        await query.message.reply_text(f"Удалил: {deleted_text}", reply_markup=undo_kb)


async def handle_delete_choose_callback(update, context, deps) -> None:
    _apply_deps(deps)
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    if not (data.startswith("del_one:") or data.startswith("del_series:") or data.startswith("del_cancel:")):
        return

    if data.startswith("del_cancel:"):
        try:
            rid = int(data.split(":", 1)[1])
        except ValueError:
            return

        source = context.user_data.pop("delete_choice_source", None)
        if source == "created":
            await query.edit_message_reply_markup(
                reply_markup=build_created_reminder_actions_keyboard(rid, is_recurring=True)
            )
        else:
            await query.edit_message_text("Ок, ничего не удалил.", reply_markup=None)
        return

    # Чат, для которого показывается список (может быть НЕ равен query.message.chat.id в личке)
    target_chat_id = context.user_data.get("list_chat_id")
    if target_chat_id is None:
        chat = query.message.chat if query.message else None
        if chat is None:
            return
        target_chat_id = chat.id

    ids: List[int] = context.user_data.get("list_ids") or []

    snapshot: Optional[Dict[str, Any]] = None
    deleted_label = ""

    if data.startswith("del_one:"):
        try:
            rid = int(data.split(":", 1)[1])
        except ValueError:
            return

        # ВАЖНО: для recurring "удалить ближайший" = удалить инстанс + пересоздать следующий
        snapshot = delete_recurring_one_instance_and_reschedule(rid, int(target_chat_id))
        if not snapshot:
            await query.answer(MSG_DELETE_FAILED_SHORT, show_alert=True)
            return

        # убираем rid из текущего списка (если он там есть)
        ids = [x for x in ids if int(x) != int(rid)]
        context.user_data["list_ids"] = ids

        deleted_label = "Удалил ближайшее повторяющееся напоминание"

    elif data.startswith("del_series:"):
        try:
            tpl_id = int(data.split(":", 1)[1])
        except ValueError:
            return

        snapshot = delete_recurring_series_with_snapshot(tpl_id, int(target_chat_id))
        if not snapshot:
            await query.answer(MSG_DELETE_SERIES_FAILED, show_alert=True)
            return

        removed_ids = {int(r["id"]) for r in (snapshot.get("reminders") or []) if r.get("id") is not None}
        ids = [x for x in ids if int(x) not in removed_ids]
        context.user_data["list_ids"] = ids

        deleted_label = "Удалил всю серию"

    source = context.user_data.pop("delete_choice_source", None)
    if source == "list":
        await _edit_stored_list_message_after_delete(context, ids, deps)

    if not snapshot:
        return

    # Сообщение "удалено" + Undo
    tpl = (snapshot or {}).get("template") or {}
    tpl_pattern_type = tpl.get("pattern_type")
    tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}

    if snapshot.get("kind") == "series":
        reminders = snapshot.get("reminders") or []
        if reminders:
            deleted_text = format_deleted_human(
                reminders[0]["remind_at"],
                tpl.get("text") or reminders[0].get("text") or "",
                tpl_pattern_type,
                tpl_payload,
            )
        else:
            deleted_text = str(tpl.get("text") or "серия")
            human = format_recurring_human(tpl_pattern_type, tpl_payload)
            if human:
                deleted_text = f"{deleted_text}  🔁 {human}"
        btn_text = "↩️ Вернуть серию"
    else:
        deleted_text = format_deleted_human(
            snapshot["reminder"]["remind_at"],
            snapshot["reminder"]["text"],
            tpl_pattern_type,
            tpl_payload,
        )
        btn_text = "↩️ Вернуть ближайший"

    token = make_undo_token()
    context.user_data["undo_tokens"] = context.user_data.get("undo_tokens") or {}
    context.user_data["undo_tokens"][token] = snapshot

    undo_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(btn_text, callback_data=cb_undo(token))]]
    )

    if query.message:
        await query.edit_message_text(format_deleted_snapshot_text(deleted_label, deleted_text), reply_markup=undo_kb)


async def handle_undo_callback(update, context, deps) -> None:
    _apply_deps(deps)
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    logger.info("UNDO pressed: data=%s", data)

    if not data.startswith("undo:"):
        await query.answer()
        return

    await query.answer("Ок, восстанавливаю...")

    token = data.split(":", 1)[1].strip()
    store = context.user_data.get("undo_tokens") or {}
    snapshot = store.get(token)
    if not snapshot:
        await query.answer(MSG_UNDO_EXPIRED, show_alert=True)
        return

    # одноразовый undo
    del store[token]
    context.user_data["undo_tokens"] = store

    restored = restore_deleted_snapshot(snapshot)
    if not restored:
        await query.answer(MSG_UNDO_RESTORE_FAILED, show_alert=True)
        return

    tpl = snapshot.get("template") or {}
    tpl_pattern_type = tpl.get("pattern_type")
    tpl_payload = tpl.get("payload") if isinstance(tpl.get("payload"), dict) else {}

    if snapshot.get("kind") == "series":
        # restored = List[int]
        human = format_recurring_human(tpl_pattern_type, tpl_payload)
        series_text = str(tpl.get("text") or "серия")
        suffix = f"  🔁 {human}" if human else "  🔁"
        count = len(restored) if isinstance(restored, list) else 0

        restored_id = None
        if isinstance(restored, list) and restored:
            try:
                restored_id = int(restored[0])
            except (TypeError, ValueError):
                restored_id = None

        reply_markup = None
        if restored_id is not None:
            reply_markup = build_created_reminder_actions_keyboard_for_reminder(restored_id)

        await query.edit_message_text(
            format_restored_series_text(series_text, suffix, count),
            reply_markup=reply_markup,
        )
        return

    # single
    restored_text = format_deleted_human(
        snapshot["reminder"]["remind_at"],
        snapshot["reminder"]["text"],
        tpl_pattern_type,
        tpl_payload,
    )

    restored_id = None
    try:
        restored_id = int(restored)
    except (TypeError, ValueError):
        restored_id = None

    reply_markup = None
    if restored_id is not None:
        reply_markup = build_created_reminder_actions_keyboard_for_reminder(restored_id)

    if tpl:
        restored_prefix = "Вернул ближайшее повторяющееся напоминание"
    else:
        restored_prefix = "Вернул"

    await query.edit_message_text(format_restored_single_text(restored_prefix, restored_text), reply_markup=reply_markup)
