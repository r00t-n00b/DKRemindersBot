"""Pagination callback for /list."""

import json


async def handle_list_page_callback(update, context, deps) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    if not data.startswith("list_page:"):
        return

    try:
        requested_page = int(data.split(":", 1)[1])
    except (TypeError, ValueError):
        return

    all_ids = [
        int(value)
        for value in (context.user_data.get("list_all_ids") or [])
    ]
    if not all_ids:
        return

    page_size = int(context.user_data.get("list_page_size") or 20)
    total_pages = max(1, (len(all_ids) + page_size - 1) // page_size)
    page = max(0, min(requested_page, total_pages - 1))

    start = page * page_size
    page_ids = all_ids[start:start + page_size]
    if not page_ids:
        return

    conn = deps.sqlite3.connect(deps.DB_PATH)
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

    qmarks = ",".join("?" for _ in page_ids)
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
        WHERE r.id IN ({qmarks}) AND r.delivered = 0
        ORDER BY r.remind_at ASC
        """,
        page_ids,
    )
    rows = c.fetchall()
    conn.close()

    existing = {int(row[0]): row for row in rows}
    rows = [existing[rid] for rid in page_ids if rid in existing]

    # Drop reminders which disappeared since /list was opened.
    live_page_ids = {int(row[0]) for row in rows}
    missing_ids = set(page_ids) - live_page_ids
    if missing_ids:
        all_ids = [rid for rid in all_ids if rid not in missing_ids]
        context.user_data["list_all_ids"] = all_ids

        total_pages = max(1, (len(all_ids) + page_size - 1) // page_size)
        page = min(page, total_pages - 1)
        start = page * page_size
        page_ids = all_ids[start:start + page_size]

        if set(page_ids) != live_page_ids:
            qmarks = ",".join("?" for _ in page_ids)
            if page_ids:
                conn = deps.sqlite3.connect(deps.DB_PATH)
                c = conn.cursor()
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
                    WHERE r.id IN ({qmarks}) AND r.delivered = 0
                    ORDER BY r.remind_at ASC
                    """,
                    page_ids,
                )
                fetched = c.fetchall()
                conn.close()
                existing = {int(row[0]): row for row in fetched}
                rows = [existing[rid] for rid in page_ids if rid in existing]
            else:
                rows = []

    if not rows:
        context.user_data["list_ids"] = []
        await query.edit_message_text("Активных напоминаний нет.")
        return

    total_count = len(all_ids)
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    alias = context.user_data.get("list_alias")
    header = (
        f"Активные напоминания для чата '{alias}':"
        if alias
        else "Активные напоминания:"
    )
    if total_pages > 1:
        header += f"\\nСтраница {page + 1}/{total_pages} · всего {total_count}."

    def keyboard_builder(count):
        try:
            return deps.build_list_delete_keyboard(
                count,
                page=page,
                total_pages=total_pages,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            return deps.build_list_delete_keyboard(count)

    reply, ids, keyboard = deps.build_active_reminders_list_response(
        rows,
        header=header,
        now_local=deps.get_now(),
        list_delete_keyboard_builder=keyboard_builder,
    )

    context.user_data["list_ids"] = ids
    context.user_data["list_page"] = page

    await query.edit_message_text(reply, reply_markup=keyboard)
