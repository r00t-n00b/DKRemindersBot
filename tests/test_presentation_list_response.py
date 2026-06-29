from datetime import datetime

from presentation import build_active_reminders_list_response


def _callback_data(markup):
    result = []
    rows = getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None) or []
    for row in rows:
        for button in row:
            data = getattr(button, "callback_data", None)
            if data is not None:
                result.append(data)
    return result


def test_active_list_response_empty():
    reply, ids, keyboard = build_active_reminders_list_response([], header="Активные напоминания:", now_local=datetime(2026, 6, 22, 12, 0))

    assert reply == "Активных напоминаний нет."
    assert ids == []
    assert keyboard is None


def test_active_list_response_formats_plain_and_recurring_rows(monkeypatch):
    import presentation

    class DummyInlineKeyboardButton:
        def __init__(self, text, callback_data=None, **kwargs):
            self.text = text
            self.callback_data = callback_data
            self.kwargs = kwargs

    class DummyInlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard
            self.keyboard = inline_keyboard

    import keyboards
    monkeypatch.setattr(keyboards, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(keyboards, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)

    rows = [
        (101, "plain reminder", "2026-06-22T19:30:00+02:00", None, None, None),
        (202, "daily reminder", "2026-06-23T10:00:00+02:00", 5, "daily", {}),
    ]

    reply, ids, keyboard = build_active_reminders_list_response(rows, header="Активные напоминания:", now_local=datetime(2026, 6, 22, 12, 0))

    assert ids == [101, 202]
    assert "Активные напоминания:" in reply
    assert "Сегодня\n1. 19:30 CET - plain reminder" in reply
    assert "Завтра\n2. 10:00 CET - daily reminder  🔁 daily" in reply

    assert keyboard is not None
    assert set(_callback_data(keyboard)) == {"del:1", "del:2"}


def test_active_list_shows_timezone_next_to_time():
    rows = [
        {
            "id": 1,
            "text": "тест timezone",
            "remind_at": "2026-06-29T16:28:00+02:00",
            "template_id": None,
            "timezone_name": "Europe/Madrid",
        }
    ]

    reply, ids, _keyboard = build_active_reminders_list_response(
        rows,
        "Активные напоминания:",
        now_local=datetime.fromisoformat("2026-06-29T12:00:00+02:00"),
        list_delete_keyboard_builder=lambda count: None,
    )

    assert "16:28 CET - тест timezone" in reply
    assert "Europe/Madrid" not in reply
    assert ids == [1]
