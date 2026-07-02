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


async def clear_reminder_message_keyboards_impl(
    bot,
    reminder_id: int,
    deps,
    replacement_text: str | None = None,
) -> None:
    _apply_deps(deps)

    rows = get_reminder_messages_impl(reminder_id, deps)

    for row in rows:
        chat_id = int(row["chat_id"])
        message_id = int(row["message_id"])

        try:
            if replacement_text is not None:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=replacement_text,
                    reply_markup=None,
                )
            else:
                await bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=None,
                )
        except Exception:
            if replacement_text is not None:
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=None,
                    )
                    continue
                except Exception:
                    pass

            logger.exception(
                "Failed to update reminder message reminder_id=%s chat_id=%s message_id=%s",
                reminder_id,
                row.get("chat_id"),
                row.get("message_id"),
            )



async def delete_old_snoozed_reminder_messages_impl(
    bot,
    *,
    current_reminder_id: int,
    chat_id: int,
    text: str,
    created_by: int | None,
    deps,
) -> None:
    """Best-effort delete old already-acked delivery/nudge messages from the same snooze chain.

    Snooze creates a new reminder row. Without this cleanup, every later snooze leaves
    the previous delivered bot message in chat:
      11:00 text (Отложено до 12:00)
      12:00 text (Отложено до 13:00)
      13:00 text (Отложено до 13:20)

    We deliberately only target already acked/sent reminders with the same
    chat/text/creator and exclude the current reminder id.
    """
    _apply_deps(deps)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """
        SELECT
            rm.id AS reminder_message_row_id,
            rm.reminder_id,
            rm.chat_id,
            rm.message_id,
            rm.kind
        FROM reminder_messages rm
        JOIN reminders r ON r.id = rm.reminder_id
        WHERE rm.reminder_id != ?
          AND rm.chat_id = ?
          AND rm.kind IN ('delivery', 'nudge')
          AND r.chat_id = ?
          AND r.text = ?
          AND COALESCE(r.created_by, -1) = COALESCE(?, -1)
          AND r.delivered = 1
          AND r.acked = 1
        ORDER BY rm.id ASC
        """,
        (
            int(current_reminder_id),
            int(chat_id),
            int(chat_id),
            text,
            created_by,
        ),
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()

    for row in rows:
        row_id = int(row["reminder_message_row_id"])
        row_chat_id = int(row["chat_id"])
        message_id = int(row["message_id"])

        try:
            await bot.delete_message(chat_id=row_chat_id, message_id=message_id)
        except Exception:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=row_chat_id,
                    message_id=message_id,
                    reply_markup=None,
                )
            except Exception:
                logger.exception(
                    "Failed to delete/deactivate old snoozed reminder message "
                    "current_reminder_id=%s old_reminder_id=%s chat_id=%s message_id=%s",
                    current_reminder_id,
                    row.get("reminder_id"),
                    row_chat_id,
                    message_id,
                )
                continue

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM reminder_messages WHERE id = ?", (row_id,))
        conn.commit()
        conn.close()
