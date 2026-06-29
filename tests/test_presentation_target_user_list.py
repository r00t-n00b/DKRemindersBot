from presentation import build_target_user_reminders_list_response


def _callback_data(markup):
    result = []
    rows = getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None) or []
    for row in rows:
        for button in row:
            data = getattr(button, "callback_data", None)
            if data is not None:
                result.append(data)
    return result


def test_target_user_list_response_empty():
    reply, ids, keyboard = build_target_user_reminders_list_response(
        [],
        target_label="@friend",
    )

    assert reply == "Ты не ставил напоминаний пользователю @friend."
    assert ids == []
    assert keyboard is None


def test_target_user_list_response_formats_rows_with_keyboard():
    class DummyInlineKeyboardButton:
        def __init__(self, text, callback_data=None, **kwargs):
            self.text = text
            self.callback_data = callback_data
            self.kwargs = kwargs

    class DummyInlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard
            self.keyboard = inline_keyboard

    def dummy_list_delete_keyboard(count):
        return DummyInlineKeyboardMarkup(
            [[DummyInlineKeyboardButton(f"❌{idx}", callback_data=f"del:{idx}") for idx in range(1, count + 1)]]
        )

    rows = [
        {
            "id": 101,
            "text": "купить молоко",
            "remind_at": "2026-06-22T19:30:00+02:00",
            "template_id": None,
            "pattern_type": None,
            "payload": None,
        },
        {
            "id": 202,
            "text": "пить воду",
            "remind_at": "2026-06-23T10:00:00+02:00",
            "template_id": 5,
            "pattern_type": "daily",
            "payload": {},
        },
    ]

    reply, ids, keyboard = build_target_user_reminders_list_response(
        rows,
        target_label="@friend",
        list_delete_keyboard_builder=dummy_list_delete_keyboard,
    )

    assert ids == [101, 202]
    assert "Напоминания, которые ты поставил пользователю @friend:" in reply
    assert "1. 22.06 19:30 CET - купить молоко" in reply
    assert "2. 23.06 10:00 CET - пить воду  🔁 daily" in reply
    assert set(_callback_data(keyboard)) == {"del:1", "del:2"}
