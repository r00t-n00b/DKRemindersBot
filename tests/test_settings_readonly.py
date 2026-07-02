import asyncio
from types import SimpleNamespace

from timezone_features import build_settings_text, handle_settings_command


class Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_build_settings_text_includes_readonly_summary_sections():
    text = build_settings_text(
        tz_name="Europe/Madrid",
        default_time_text="09:30",
        active_reminders_count=3,
        active_recurring_templates_count=2,
        user_alias_lines=["• wife -> @wife / chat_id=111"],
        chat_alias_lines=["• football -> Football Chat / chat_id=222"],
    )

    assert "Настройки" in text
    assert "Часовой пояс: CET" in text
    assert "Если ты не укажешь время при постановке ремайндера, то я установлю его на 09:30." in text
    assert "Запланированные напоминания: 3" in text
    assert "Активные повторяющиеся напоминания" not in text
    assert "👤 User aliases:" in text
    assert "• wife -> @wife / chat_id=111" in text
    assert "💬 Chat aliases:" in text
    assert "• football -> Football Chat / chat_id=222" in text
    assert "/defaulttime 09:30" in text
    assert "/aliases" in text
    assert "Nudge policy" not in text
    assert "в backlog" not in text


def test_build_settings_text_shows_empty_alias_summary():
    text = build_settings_text(
        tz_name="Europe/Madrid",
        default_time_text=None,
        active_reminders_count=0,
        active_recurring_templates_count=0,
        user_alias_lines=[],
        chat_alias_lines=[],
    )

    assert "Если ты не укажешь время при постановке ремайндера, то я установлю его на 10:00." in text
    assert "Запланированные напоминания: 0" in text
    assert "Тобой не было заведено ни одного алиаса" in text


def test_settings_command_loads_default_time_active_count_and_aliases():
    message = Message()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
    )

    deps = SimpleNamespace(
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        get_user_default_time=lambda user_id: (9, 30),
        count_active_reminders_for_chat=lambda chat_id: 3 if chat_id == 999 else -1,
        get_all_user_aliases=lambda user_id: [("wife", 111)],
        get_user_alias=lambda alias, created_by: {"username": "wife"},
        get_all_aliases=lambda user_id: [("football", 222, "Football Chat")],
    )

    asyncio.run(handle_settings_command(update, SimpleNamespace(), deps))

    assert len(message.replies) == 1
    text, kwargs = message.replies[0]

    assert "Часовой пояс: CET" in text
    assert "Если ты не укажешь время при постановке ремайндера, то я установлю его на 09:30." in text
    assert "Запланированные напоминания: 3" in text
    assert "Активные повторяющиеся напоминания" not in text
    assert "• wife -> @wife / chat_id=111" in text
    assert "• football -> Football Chat / chat_id=222" in text
    assert kwargs["reply_markup"] is not None



def test_settings_command_prompts_for_timezone_when_user_has_no_timezone():
    message = Message()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123),
    )

    deps = SimpleNamespace(
        get_user_timezone_name_raw=lambda user_id: None,
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        get_user_default_time=lambda user_id: None,
        count_active_reminders_for_user=lambda user_id: 0,
        count_active_recurring_templates_for_user=lambda user_id: 0,
        get_all_user_aliases=lambda user_id: [],
        get_all_aliases=lambda user_id: [],
    )

    asyncio.run(handle_settings_command(update, SimpleNamespace(), deps))

    assert len(message.replies) == 1
    text, kwargs = message.replies[0]

    assert "Telegram не передаёт мне твой часовой пояс автоматически" in text
    assert "Часовой пояс: CET" not in text
    assert kwargs["reply_markup"] is not None



def test_settings_command_counts_visible_chat_reminders_not_created_by_user():
    message = Message()
    calls = []

    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
    )

    deps = SimpleNamespace(
        get_user_timezone_name_raw=lambda user_id: "Europe/Madrid",
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        get_user_default_time=lambda user_id: None,
        count_active_reminders_for_user=lambda user_id: 0,
        count_active_recurring_templates_for_user=lambda user_id: 0,
        count_active_reminders_for_chat=lambda chat_id: calls.append(("reminders", chat_id)) or 3,
        get_all_user_aliases=lambda user_id: [],
        get_all_aliases=lambda user_id: [],
    )

    asyncio.run(handle_settings_command(update, SimpleNamespace(), deps))

    text, _ = message.replies[0]

    assert ("reminders", 999) in calls
    assert "Запланированные напоминания: 3" in text
    assert "Активные повторяющиеся напоминания" not in text


class QueryMessage:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class Query:
    def __init__(self, data):
        self.data = data
        self.message = QueryMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.message.edits.append((text, kwargs))


def test_settings_keyboard_has_default_time_button():
    message = Message()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
    )

    deps = SimpleNamespace(
        get_user_timezone_name_raw=lambda user_id: "Europe/Madrid",
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        get_user_default_time=lambda user_id: (10, 30),
        count_active_reminders_for_chat=lambda chat_id: 3,
        get_all_user_aliases=lambda user_id: [],
        get_all_aliases=lambda user_id: [],
    )

    asyncio.run(handle_settings_command(update, SimpleNamespace(), deps))

    _, kwargs = message.replies[0]
    keyboard = kwargs["reply_markup"].inline_keyboard
    buttons = [button for row in keyboard for button in row]

    assert any(button.text == "⏰ Изменить время по умолчанию" for button in buttons)
    assert any(button.callback_data == "settings:defaulttime" for button in buttons)
    assert any(button.text == "🌍 Изменить часовой пояс" for button in buttons)
    assert any(button.callback_data == "settings:timezone" for button in buttons)
    assert not any((button.callback_data or "").startswith("tz:") for button in buttons)


def test_settings_defaulttime_callback_opens_picker():
    from timezone_features import handle_settings_callback

    query = Query("settings:defaulttime")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
    )

    deps = SimpleNamespace(
        get_user_default_time=lambda user_id: (10, 30),
    )

    asyncio.run(handle_settings_callback(update, SimpleNamespace(), deps))

    assert query.answers
    text, kwargs = query.message.edits[0]
    assert "Выбери время" in text
    keyboard = kwargs["reply_markup"].inline_keyboard
    callback_data = [button.callback_data for row in keyboard for button in row]
    assert "settings:defaulttime:set:10:30" in callback_data
    assert "settings:defaulttime:reset" in callback_data
    assert "settings:back" in callback_data


def test_settings_defaulttime_set_saves_and_returns_to_settings():
    from timezone_features import handle_settings_callback

    saved = []

    query = Query("settings:defaulttime:set:9:30")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
    )

    deps = SimpleNamespace(
        set_user_default_time=lambda user_id, hour, minute: saved.append((user_id, hour, minute)),
        get_user_timezone_name_raw=lambda user_id: "Europe/Madrid",
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        get_user_default_time=lambda user_id: (9, 30),
        count_active_reminders_for_chat=lambda chat_id: 3,
        get_all_user_aliases=lambda user_id: [],
        get_all_aliases=lambda user_id: [],
    )

    asyncio.run(handle_settings_callback(update, SimpleNamespace(), deps))

    assert saved == [(123, 9, 30)]
    assert query.answers[0][0] == "Сохранил 09:30"
    text, _ = query.message.edits[0]
    assert "я установлю его на 09:30" in text


def test_settings_defaulttime_reset_clears_and_returns_to_settings():
    from timezone_features import handle_settings_callback

    cleared = []

    query = Query("settings:defaulttime:reset")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
    )

    deps = SimpleNamespace(
        clear_user_default_time=lambda user_id: cleared.append(user_id),
        get_user_timezone_name_raw=lambda user_id: "Europe/Madrid",
        get_user_timezone_name=lambda user_id: "Europe/Madrid",
        get_user_default_time=lambda user_id: None,
        count_active_reminders_for_chat=lambda chat_id: 3,
        get_all_user_aliases=lambda user_id: [],
        get_all_aliases=lambda user_id: [],
    )

    asyncio.run(handle_settings_callback(update, SimpleNamespace(), deps))

    assert cleared == [123]
    assert query.answers[0][0] == "Сбросил на 10:00"
    text, _ = query.message.edits[0]
    assert "я установлю его на 10:00" in text



def test_settings_text_does_not_include_big_timezone_help_block():
    text = build_settings_text(
        tz_name="Europe/Madrid",
        default_time_text="10:30",
        active_reminders_count=3,
        user_alias_lines=[],
        chat_alias_lines=[],
    )

    assert "Часовой пояс: CET" in text
    assert "Часовой пояс можно поменять кнопками ниже" not in text
    assert "Telegram не позволит пошарить геопозицию" not in text
    assert "For mobile only: определить по геопозиции" not in text



def test_settings_timezone_callback_opens_timezone_dialog():
    from timezone_features import handle_settings_callback

    query = Query("settings:timezone")
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
    )

    deps = SimpleNamespace()

    asyncio.run(handle_settings_callback(update, SimpleNamespace(), deps))

    assert query.answers
    text, kwargs = query.message.edits[0]
    assert "Telegram не передаёт мне твой часовой пояс автоматически" in text

    keyboard = kwargs["reply_markup"].inline_keyboard
    callback_data = [button.callback_data for row in keyboard for button in row]

    assert "tz:geo" in callback_data
    assert "tz:preset:cet" in callback_data
    assert "tz:preset:moscow" in callback_data
