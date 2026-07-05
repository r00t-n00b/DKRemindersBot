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
    max_messages: int = 10,
) -> None:
    """Best-effort cleanup for old messages from the same snooze chain.

    Important production rules:
    - If Telegram says the message cannot be deleted anymore, drop local tracking
      and do not try fallback edit; otherwise the same impossible message will be
      retried forever.
    - If Telegram returns RetryAfter/flood control, stop the loop immediately.
    - Limit one cleanup pass so a burst of old Done clicks cannot flood Telegram.
    """
    _apply_deps(deps)

    def _exc_name(exc: Exception) -> str:
        return exc.__class__.__name__

    def _exc_text(exc: Exception) -> str:
        return str(exc).lower()

    def _is_retry_after(exc: Exception) -> bool:
        return _exc_name(exc) == "RetryAfter" or "retry after" in _exc_text(exc) or "flood control" in _exc_text(exc)

    def _is_permanent_delete_failure(exc: Exception) -> bool:
        msg = _exc_text(exc)
        return (
            "can't be deleted" in msg
            or "cannot be deleted" in msg
            or "message to delete not found" in msg
            or "message not found" in msg
        )

    def _is_permanent_edit_failure(exc: Exception) -> bool:
        msg = _exc_text(exc)
        return (
            "message is not modified" in msg
            or "message to edit not found" in msg
            or "message can't be edited" in msg
            or "message cannot be edited" in msg
            or "message not found" in msg
        )

    def _drop_message_tracking(row_id: int) -> None:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM reminder_messages WHERE id = ?", (int(row_id),))
        conn.commit()
        conn.close()

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
        LIMIT ?
        """,
        (
            int(current_reminder_id),
            int(chat_id),
            int(chat_id),
            text,
            created_by,
            int(max_messages),
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
            _drop_message_tracking(row_id)
            continue
        except Exception as delete_exc:
            if _is_retry_after(delete_exc):
                logger.warning(
                    "Stop old snoozed cleanup because Telegram returned RetryAfter "
                    "current_reminder_id=%s chat_id=%s message_id=%s error=%s",
                    current_reminder_id,
                    row_chat_id,
                    message_id,
                    delete_exc,
                )
                break

            if _is_permanent_delete_failure(delete_exc):
                logger.info(
                    "Drop old snoozed message tracking after permanent delete failure "
                    "current_reminder_id=%s old_reminder_id=%s chat_id=%s message_id=%s error=%s",
                    current_reminder_id,
                    row.get("reminder_id"),
                    row_chat_id,
                    message_id,
                    delete_exc,
                )
                _drop_message_tracking(row_id)
                continue

        try:
            await bot.edit_message_reply_markup(
                chat_id=row_chat_id,
                message_id=message_id,
                reply_markup=None,
            )
            _drop_message_tracking(row_id)
        except Exception as edit_exc:
            if _is_retry_after(edit_exc):
                logger.warning(
                    "Stop old snoozed cleanup because Telegram returned RetryAfter on fallback edit "
                    "current_reminder_id=%s chat_id=%s message_id=%s error=%s",
                    current_reminder_id,
                    row_chat_id,
                    message_id,
                    edit_exc,
                )
                break

            if _is_permanent_edit_failure(edit_exc):
                logger.info(
                    "Drop old snoozed message tracking after permanent edit failure "
                    "current_reminder_id=%s old_reminder_id=%s chat_id=%s message_id=%s error=%s",
                    current_reminder_id,
                    row.get("reminder_id"),
                    row_chat_id,
                    message_id,
                    edit_exc,
                )
                _drop_message_tracking(row_id)
                continue

            logger.warning(
                "Failed to delete/deactivate old snoozed reminder message "
                "current_reminder_id=%s old_reminder_id=%s chat_id=%s message_id=%s error=%s",
                current_reminder_id,
                row.get("reminder_id"),
                row_chat_id,
                message_id,
                edit_exc,
            )



async def delete_other_reminder_messages_impl(
    bot,
    *,
    reminder_id: int,
    keep_chat_id: int,
    keep_message_id: int,
    deps,
) -> None:
    """Delete/deactivate sibling Telegram messages for the same reminder.

    When a reminder has both delivery and nudge messages, snoozing one message
    should not leave identical snoozed copies in the chat.
    """
    _apply_deps(deps)

    def _drop_message_tracking(row_id: int) -> None:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM reminder_messages WHERE id = ?", (int(row_id),))
        conn.commit()
        conn.close()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, message_id
        FROM reminder_messages
        WHERE reminder_id = ?
          AND NOT (chat_id = ? AND message_id = ?)
        ORDER BY id ASC
        """,
        (int(reminder_id), int(keep_chat_id), int(keep_message_id)),
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()

    for row in rows:
        row_id = int(row["id"])
        chat_id = int(row["chat_id"])
        message_id = int(row["message_id"])

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            _drop_message_tracking(row_id)
            continue
        except Exception:
            pass

        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None,
            )
            _drop_message_tracking(row_id)
        except Exception:
            logger.warning(
                "Failed to delete/deactivate sibling reminder message "
                "reminder_id=%s chat_id=%s message_id=%s",
                reminder_id,
                chat_id,
                message_id,
            )



async def delete_reminder_messages_by_kind_impl(
    bot,
    *,
    reminder_id: int,
    kind: str,
    deps,
) -> None:
    """Delete/deactivate tracked Telegram messages for one reminder and kind."""
    _apply_deps(deps)

    def _drop_message_tracking(row_id: int) -> None:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM reminder_messages WHERE id = ?", (int(row_id),))
        conn.commit()
        conn.close()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, message_id
        FROM reminder_messages
        WHERE reminder_id = ?
          AND kind = ?
        ORDER BY id ASC
        """,
        (int(reminder_id), str(kind)),
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()

    for row in rows:
        row_id = int(row["id"])
        chat_id = int(row["chat_id"])
        message_id = int(row["message_id"])

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            _drop_message_tracking(row_id)
            continue
        except Exception:
            pass

        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None,
            )
            _drop_message_tracking(row_id)
        except Exception:
            logger.warning(
                "Failed to delete/deactivate reminder message by kind "
                "reminder_id=%s kind=%s chat_id=%s message_id=%s",
                reminder_id,
                kind,
                chat_id,
                message_id,
            )
