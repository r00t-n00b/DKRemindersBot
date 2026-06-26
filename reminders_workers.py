"""Background reminder worker flows."""

from messages import msg_nudge_unacked

from typing import Any, Dict, List, Optional, Tuple


_DEP_NAMES = [
    "get_chat_type",
    "Chat",
    "add_reminder",
    "asyncio",
    "build_group_reminder_keyboard",
    "build_snooze_keyboard",
    "claim_due_reminders",
    "compute_next_occurrence",
    "get_due_nudges",
    "get_due_reminders",
    "get_now",
    "get_recurring_template",
    "increment_nudge_count",
    "logger",
    "mark_reminder_delivery_failed",
    "mark_reminder_sent",
    "register_reminder_message",
    "reset_stale_processing_reminders",
]


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


async def _safe_get_chat_type(app, chat_id: int) -> Optional[str]:
    try:
        chat = await app.bot.get_chat(chat_id)
        return getattr(chat, "type", None)
    except Exception:
        return None


async def run_reminders_worker(app, deps) -> None:
    _apply_deps(deps)
    logger.info("Запущен фоновой worker напоминаний")

    while True:
        try:
            now = get_now()
            reset_count = reset_stale_processing_reminders(now)
            if reset_count:
                logger.warning("Reset stale processing reminders: %s", reset_count)

            due = claim_due_reminders(now)

            if due:
                logger.info("Claimed %s напоминаний к отправке", len(due))

            for r in due:
                try:
                    chat_type = await get_chat_type(app, r.chat_id)

                    chat_type_value = getattr(chat_type, "value", chat_type)
                    chat_type_value = str(chat_type_value).lower() if chat_type_value is not None else None

                    reply_markup = (
                        build_group_reminder_keyboard(r.id)
                        if chat_type_value in {"group", "supergroup", "channel"}
                        else build_snooze_keyboard(r.id)
                    )

                    sent_message = await app.bot.send_message(
                        chat_id=r.chat_id,
                        text=r.text,
                        reply_markup=reply_markup,
                    )

                    sent_message_id = getattr(sent_message, "message_id", None)
                    if sent_message_id is not None:
                        register_reminder_message(
                            reminder_id=r.id,
                            chat_id=r.chat_id,
                            message_id=sent_message_id,
                            kind="delivery",
                        )

                    mark_reminder_sent(r.id, sent_at=now)

                    logger.info(
                        "Отправлено напоминание id=%s в чат %s: %s (время %s, template_id=%s)",
                        r.id,
                        r.chat_id,
                        r.text,
                        r.remind_at.isoformat(),
                        r.template_id,
                    )

                    if r.template_id is not None:
                        tpl = get_recurring_template(r.template_id)
                        if tpl and tpl["active"]:
                            next_dt = compute_next_occurrence(
                                tpl["pattern_type"],
                                tpl["payload"],
                                tpl["time_hour"],
                                tpl["time_minute"],
                                r.remind_at,
                            )
                            if next_dt is not None:
                                add_reminder(
                                    chat_id=tpl["chat_id"],
                                    text=tpl["text"],
                                    remind_at=next_dt,
                                    created_by=tpl["created_by"],
                                    template_id=tpl["id"],
                                )
                                logger.info(
                                    "Запланировано следующее повторяющееся напоминание для tpl_id=%s на %s",
                                    tpl["id"],
                                    next_dt.isoformat(),
                                )

                except Exception as exc:
                    mark_reminder_delivery_failed(r.id, str(exc), failed_at=now)
                    logger.exception(
                        "Ошибка при отправке напоминания id=%s",
                        r.id,
                    )

        except Exception:
            logger.exception("Ошибка в worker напоминаний")

        await asyncio.sleep(10)


async def run_reminders_nudge_worker(app, deps) -> None:
    _apply_deps(deps)
    logger.info("Запущен фоновой nudge worker напоминаний")
    while True:
        try:
            now = get_now()

            rows = get_due_nudges(now)
            for r in rows:
                try:
                    # строго: nudges только в личке
                    chat_type = await get_chat_type(app, r["chat_id"])

                    if chat_type != Chat.PRIVATE:
                        continue

                    text = msg_nudge_unacked(r["text"])

                    reply_markup = build_snooze_keyboard(r["id"])

                    sent_message = await app.bot.send_message(
                        chat_id=r["chat_id"],
                        text=text,
                        reply_markup=reply_markup,
                    )

                    sent_message_id = getattr(sent_message, "message_id", None)
                    if sent_message_id is not None:
                        register_reminder_message(
                            reminder_id=int(r["id"]),
                            chat_id=int(r["chat_id"]),
                            message_id=sent_message_id,
                            kind="nudge",
                        )

                    increment_nudge_count(r["id"])
                except Exception:
                    logger.exception("Ошибка при отправке nudge reminder id=%s", r["id"])
        except Exception:
            logger.exception("Ошибка в nudge worker")

        await asyncio.sleep(30)
