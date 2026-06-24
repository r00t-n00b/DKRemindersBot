"""Storage/helpers for Telegram messages associated with reminders."""


def _apply_deps(deps) -> None:
    globals()["DB_PATH"] = deps.DB_PATH
    globals()["get_now"] = deps.get_now
    globals()["logger"] = deps.logger
    globals()["sqlite3"] = deps.sqlite3


def register_reminder_message_impl(
    reminder_id: int,
    chat_id: int,
    message_id: int,
    kind: str,
    deps,
) -> None:
    _apply_deps(deps)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT OR IGNORE INTO reminder_messages
            (reminder_id, chat_id, message_id, kind, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(reminder_id),
            int(chat_id),
            int(message_id),
            kind,
            get_now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_reminder_messages_impl(reminder_id: int, deps) -> list[dict]:
    _apply_deps(deps)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """
        SELECT reminder_id, chat_id, message_id, kind, created_at
        FROM reminder_messages
        WHERE reminder_id = ?
        ORDER BY id ASC
        """,
        (int(reminder_id),),
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


async def clear_reminder_message_keyboards_impl(bot, reminder_id: int, deps) -> None:
    _apply_deps(deps)

    rows = get_reminder_messages_impl(reminder_id, deps)

    for row in rows:
        try:
            await bot.edit_message_reply_markup(
                chat_id=int(row["chat_id"]),
                message_id=int(row["message_id"]),
                reply_markup=None,
            )
        except Exception:
            logger.exception(
                "Failed to clear reminder message keyboard reminder_id=%s chat_id=%s message_id=%s",
                reminder_id,
                row.get("chat_id"),
                row.get("message_id"),
            )
