import ast
from pathlib import Path

import dkreminders_bot.ui.messages as messages


TARGET_FILES = [
    "dkreminders_bot/callbacks/created_action_callbacks.py",
    "dkreminders_bot/callbacks/created_delete_router.py",
    "dkreminders_bot/callbacks/created_snooze_router.py",
    "dkreminders_bot/callbacks/delete_undo_router.py",
    "dkreminders_bot/callbacks/snooze_custom_flow.py",
    "dkreminders_bot/callbacks/snooze_time_picker.py",
    "dkreminders_bot/callbacks/snooze_cancel_flow.py",
    "dkreminders_bot/callbacks/self_remind_cancel_flow.py",
    "dkreminders_bot/callbacks/self_remind_event_cancel_flow.py",
    "dkreminders_bot/callbacks/self_remind_initial_flow.py",
    "dkreminders_bot/callbacks/self_remind_create_flow.py",
    "dkreminders_bot/callbacks/self_remind_calendar_flow.py",
    "dkreminders_bot/callbacks/self_remind_picktime_flow.py",
]


def test_broad_callback_messages_are_exported():
    expected = [
        "MSG_PICK_DATE",
        "MSG_PICK_TIME",
        "MSG_RETURNED_OPTIONS",
        "MSG_RETURNED_CHOICE",
        "MSG_RETURNED_EVENT_OPTIONS",
        "MSG_PERSONAL_REMINDER_CREATED",
        "MSG_SELF_REMIND_PRIVATE_START",
        "MSG_SELF_REMIND_SENT_TO_PRIVATE",
        "MSG_SELF_REMIND_CANCELLED",
        "MSG_OK_SHORT",
        "MSG_SELF_REMIND_EVENT_DATE_NOT_FOUND_ANSWER",
        "MSG_SELF_REMIND_EVENT_DATE_NOT_FOUND_TEXT",
        "MSG_DELETE_NOT_FOUND_ALERT",
        "MSG_NO_MORE_REMINDERS",
        "MSG_DELETE_CANCELLED",
        "MSG_DELETE_RECURRING_ONE_LABEL",
        "MSG_DELETE_RECURRING_SERIES_LABEL",
        "MSG_UNDO_RESTORING",
        "MSG_UNDO_BUTTON_REMINDER",
        "MSG_UNDO_BUTTON_SERIES",
        "MSG_UNDO_BUTTON_NEXT_RECURRING",
        "MSG_CREATED_DELETE_ANSWER",
        "MSG_RESTORED_NEXT_RECURRING_PREFIX",
        "MSG_RESTORED_SINGLE_PREFIX",
        "msg_created_snoozed",
        "msg_created_snoozed_answer",
        "msg_created_deleted",
        "msg_delete_recurring_prompt",
        "msg_self_remind_mode_prompt",
        "msg_self_remind_regular_prompt",
        "msg_self_remind_event_before_prompt",
    ]

    for name in expected:
        assert name in messages.__all__


def test_broad_callback_dynamic_messages_preserve_current_text():
    assert messages.msg_created_snoozed("02.02 12:00", "test") == (
        "Перенёс напоминание на 02.02 12:00: test"
    )
    assert messages.msg_created_snoozed_answer("02.02 12:00") == "Перенесено на 02.02 12:00"
    assert messages.msg_created_deleted("abc") == "Удалил: abc"
    assert messages.msg_delete_recurring_prompt("preview") == (
        "Это повторяющееся напоминание. Как удалить?\n\npreview"
    )
    assert messages.msg_self_remind_mode_prompt("купить молоко", "Чат") == (
        'Как тебе напомнить о "купить молоко" из чата "Чат"?'
    )
    assert messages.msg_self_remind_regular_prompt("купить молоко", "Чат") == (
        'Когда напомнить тебе о "купить молоко" из чата "Чат"?'
    )
    assert messages.msg_self_remind_event_before_prompt("02.02 12:00") == (
        "Я понял, что событие из напоминания состоится 02.02 12:00.\n"
        "За сколько до этого времени напомнить?"
    )


def test_target_callback_modules_do_not_embed_centralized_literal_strings():
    forbidden_substrings = [
        "Выбери дату",
        "Выбери время",
        "Вернул варианты",
        "Вернул выбор",
        "Вернул варианты до события",
        "Личное напоминание создано",
        "Ок, личное напоминание не создаю.",
        "Не смог понять дату события. Выбери обычное напоминание или время вручную.",
        "Я не смог понять дату события из текста.",
        "Ты можешь поставить себе обычный ремайндер:",
        "Не нашел такое напоминание",
        "Напоминаний больше нет.",
        "Ок, ничего не удалил.",
        "Удалил ближайшее повторяющееся напоминание",
        "Удалил всю серию",
        "Ок, восстанавливаю...",
        "↩️ Вернуть ремайндер",
        "↩️ Вернуть серию",
        "↩️ Вернуть ближайший",
        "Удалено",
        "Перенёс напоминание на",
        "Перенесено на",
        "Это повторяющееся напоминание. Как удалить?",
        "Как тебе напомнить о",
        "Когда напомнить тебе о",
        "За сколько до этого времени напомнить?",
        "Я еще с тобой не знаком. Открой бота в личке",
    ]

    findings = []

    for file_name in TARGET_FILES:
        source = Path(file_name).read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for forbidden in forbidden_substrings:
                    if forbidden in node.value:
                        findings.append((file_name, node.lineno, forbidden, node.value))

    assert findings == []
