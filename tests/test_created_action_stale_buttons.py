import asyncio
from types import SimpleNamespace

from dkreminders_bot.callbacks.created_action_callbacks import ensure_created_action_reminder_exists_impl
from dkreminders_bot.callbacks.created_delete_router import handle_created_delete_callback
from dkreminders_bot.callbacks.created_snooze_router import handle_created_snooze_callback


class Query:
    def __init__(self, data=""):
        self.data = data
        self.answers = []
        self.edited_texts = []
        self.edited_markups = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edited_markups.append(reply_markup)

    async def edit_message_text(self, text, reply_markup=None):
        self.edited_texts.append((text, reply_markup))


def test_created_action_guard_rejects_processed_reminder():
    query = Query()
    deps = SimpleNamespace(
        MSG_INVALID_REMINDER_ID="invalid",
        MSG_REMINDER_NOT_FOUND="missing",
        MSG_RESCHEDULE_OPEN_FAILED_TEXT="failed",
        build_created_reminder_actions_keyboard_for_reminder=lambda rid: f"actions:{rid}",
        build_created_reschedule_keyboard=lambda rid: f"reschedule:{rid}",
        build_custom_date_keyboard=lambda rid, callback_prefix="x": f"date:{rid}",
        get_reminder=lambda rid: SimpleNamespace(id=rid, delivered=1, acked=1),
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        answer_created_action_reminder_missing=lambda query: None,
    )

    ok = asyncio.run(ensure_created_action_reminder_exists_impl(query, 123, deps))

    assert ok is False
    assert query.answers == [("Это напоминание уже обработано", True)]
    assert query.edited_markups == [None]


def test_created_snooze_direct_rejects_processed_reminder_without_updating_time():
    calls = []
    query = Query("created_snooze:123:20m")
    update = SimpleNamespace(callback_query=query)

    deps = SimpleNamespace(
        MSG_INVALID_REMINDER_ID="invalid",
        MSG_RESCHEDULE_BAD_DATETIME="bad datetime",
        MSG_RESCHEDULE_PAST_TIME="past",
        MSG_RESCHEDULE_UNKNOWN_ACTION="unknown",
        MSG_UNEXPECTED_CALLBACK_ERROR="unexpected",
        TZ=None,
        _answer_created_action_reminder_missing=lambda query: None,
        _ensure_created_action_reminder_exists=lambda query, rid: True,
        build_created_reminder_actions_keyboard_for_reminder=lambda rid: f"actions:{rid}",
        build_created_reschedule_keyboard=lambda rid: f"reschedule:{rid}",
        build_custom_date_keyboard=lambda *args, **kwargs: "date",
        build_custom_time_keyboard=lambda *args, **kwargs: "time",
        compute_snooze_target_time=lambda *args, **kwargs: calls.append(("compute", args, kwargs)) or "new-dt",
        datetime=None,
        get_now=lambda: "now",
        get_reminder=lambda rid: SimpleNamespace(id=rid, text="milk", delivered=1, acked=1),
        get_user_default_time=lambda user_id: None,
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
        update_reminder_time=lambda rid, new_dt: calls.append(("update", rid, new_dt)) or True,
    )

    asyncio.run(handle_created_snooze_callback(update, SimpleNamespace(), deps))

    assert calls == []
    assert query.answers == [("Это напоминание уже обработано", True)]
    assert query.edited_markups == [None]


def test_created_delete_rejects_processed_reminder_without_deleting():
    calls = []
    query = Query("created_del:123")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})

    deps = SimpleNamespace(
        InlineKeyboardButton=lambda *args, **kwargs: None,
        InlineKeyboardMarkup=lambda *args, **kwargs: None,
        MSG_DELETE_FAILED_SHORT="delete failed",
        MSG_DELETE_FAILED_TEXT="delete failed text",
        MSG_REMINDER_ALREADY_DELETED_ALERT="already deleted",
        MSG_REMINDER_ALREADY_DELETED_TEXT="already deleted text",
        build_recurring_delete_choice_keyboard=lambda rid, tpl_id: f"choice:{rid}:{tpl_id}",
        cb_undo=lambda token: f"undo:{token}",
        delete_single_reminder_with_snapshot=lambda rid, chat_id: calls.append(("delete", rid, chat_id)) or {},
        dict=dict,
        format_deleted_human=lambda *args, **kwargs: "deleted human",
        get_reminder_row=lambda rid: {
            "id": rid,
            "chat_id": 555,
            "text": "milk",
            "remind_at": "2026-01-01T10:00:00+00:00",
            "template_id": None,
            "delivered": 1,
            "acked": 1,
        },
        make_undo_token=lambda: "token",
    )

    asyncio.run(handle_created_delete_callback(update, context, deps))

    assert calls == []
    assert query.answers == [("Это напоминание уже обработано", True)]
    assert query.edited_markups == [None]
