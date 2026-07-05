import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import main
from dkreminders_bot.callbacks.self_remind_initial_flow import (
    SELF_REMIND_PRIVATE_START_MESSAGE,
    handle_self_remind_ask,
    handle_self_remind_cancel_personal,
    handle_self_remind_back,
    handle_self_remind_mode,
)


class Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


class Query:
    def __init__(self, *, user_id=42, message=True):
        self.from_user = SimpleNamespace(id=user_id) if user_id is not None else SimpleNamespace()
        self.message = object() if message else None
        self.edited_texts = []
        self.edited_markups = []
        self.answers = []

    async def edit_message_text(self, text, reply_markup=None):
        self.edited_texts.append(text)
        self.edited_markups.append(reply_markup)

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def parse_required_int_callback_id(data, *, prefix):
    if not data.startswith(prefix):
        raise ValueError("bad prefix")
    return int(data[len(prefix):])


async def title_helper(context, src, query):
    return "Исходный чат"


def test_self_remind_ask_sends_mode_keyboard_to_private_chat():
    bot = Bot()
    query = Query()
    source = SimpleNamespace(text="купить молоко")

    asyncio.run(
        handle_self_remind_ask(
            data="selfremind:ask:123",
            query=query,
            context=SimpleNamespace(bot=bot),
            parse_required_int_callback_id=parse_required_int_callback_id,
            get_user_chat_id_by_user_id=lambda user_id: 999,
            get_reminder=lambda rid: source,
            get_source_chat_title_for_self_remind=title_helper,
            build_self_remind_mode_keyboard=lambda rid: f"mode-kb:{rid}",
            msg_invalid_reminder_id="invalid id",
            msg_user_context_missing="user missing",
            msg_source_reminder_not_found="source missing",
        )
    )

    assert bot.sent == [
        {
            "chat_id": 999,
            "text": 'Как тебе напомнить о "купить молоко" из чата "Исходный чат"?',
            "reply_markup": "mode-kb:123",
        }
    ]
    assert query.answers == [("Отправил варианты в личку", None)]


def test_self_remind_ask_negative_paths():
    for kwargs, expected in [
        ({"data": "selfremind:ask:bad"}, ("invalid id", True)),
        ({"query": Query(user_id=None)}, ("user missing", True)),
        ({"get_user_chat_id_by_user_id": lambda user_id: None}, (SELF_REMIND_PRIVATE_START_MESSAGE, True)),
        ({"get_reminder": lambda rid: None}, ("source missing", True)),
    ]:
        bot = Bot()
        query = kwargs.pop("query", Query())
        asyncio.run(
            handle_self_remind_ask(
                data=kwargs.pop("data", "selfremind:ask:123"),
                query=query,
                context=SimpleNamespace(bot=bot),
                parse_required_int_callback_id=parse_required_int_callback_id,
                get_user_chat_id_by_user_id=kwargs.pop("get_user_chat_id_by_user_id", lambda user_id: 999),
                get_reminder=kwargs.pop("get_reminder", lambda rid: SimpleNamespace(text="text")),
                get_source_chat_title_for_self_remind=title_helper,
                build_self_remind_mode_keyboard=lambda rid: f"mode-kb:{rid}",
                msg_invalid_reminder_id="invalid id",
                msg_user_context_missing="user missing",
                msg_source_reminder_not_found="source missing",
            )
        )
        assert query.answers == [expected]


def test_cancel_personal_edits_message_when_message_exists():
    query = Query(message=True)

    asyncio.run(
        handle_self_remind_cancel_personal(
            data="selfremind:cancel_personal:123",
            query=query,
            parse_required_int_callback_id=parse_required_int_callback_id,
            msg_invalid_reminder_id="invalid id",
        )
    )

    assert query.edited_texts == ["Ок, личное напоминание не создаю."]
    assert query.answers == [("Ок", None)]


def test_cancel_personal_replies_invalid_id():
    query = Query()

    asyncio.run(
        handle_self_remind_cancel_personal(
            data="selfremind:cancel_personal:bad",
            query=query,
            parse_required_int_callback_id=parse_required_int_callback_id,
            msg_invalid_reminder_id="invalid id",
        )
    )

    assert query.edited_texts == []
    assert query.answers == [("invalid id", True)]


def test_self_remind_back_restores_mode_keyboard():
    query = Query()
    source = SimpleNamespace(text="купить молоко")

    asyncio.run(
        handle_self_remind_back(
            data="selfremind:back:123",
            query=query,
            context=SimpleNamespace(bot="bot"),
            parse_required_int_callback_id=parse_required_int_callback_id,
            get_reminder=lambda rid: source,
            get_source_chat_title_for_self_remind=title_helper,
            build_self_remind_mode_keyboard=lambda rid: f"mode-kb:{rid}",
            msg_invalid_reminder_id="invalid id",
            msg_source_reminder_not_found="source missing",
        )
    )

    assert query.edited_texts == ['Как тебе напомнить о "купить молоко" из чата "Исходный чат"?']
    assert query.edited_markups == ["mode-kb:123"]
    assert query.answers == [("Вернул выбор", None)]


def test_self_remind_back_negative_paths():
    assert_negative_back(data="selfremind:back:bad", expected=("invalid id", True))
    assert_negative_back(get_reminder=lambda rid: None, expected=("source missing", True))


def assert_negative_back(**kwargs):
    query = Query()
    asyncio.run(
        handle_self_remind_back(
            data=kwargs.pop("data", "selfremind:back:123"),
            query=query,
            context=SimpleNamespace(bot="bot"),
            parse_required_int_callback_id=parse_required_int_callback_id,
            get_reminder=kwargs.pop("get_reminder", lambda rid: SimpleNamespace(text="text")),
            get_source_chat_title_for_self_remind=title_helper,
            build_self_remind_mode_keyboard=lambda rid: f"mode-kb:{rid}",
            msg_invalid_reminder_id="invalid id",
            msg_source_reminder_not_found="source missing",
        )
    )
    assert query.answers == [kwargs["expected"]]


def run_mode(**overrides):
    query = overrides.pop("query", Query())
    source = overrides.pop("source", SimpleNamespace(text="футбол завтра"))
    event_at = overrides.pop("event_at", datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc))

    asyncio.run(
        handle_self_remind_mode(
            data=overrides.pop("data", "selfremind:mode:123:regular"),
            query=query,
            context=overrides.pop("context", SimpleNamespace(bot="bot")),
            parse_required_int_callback_id=parse_required_int_callback_id,
            get_user_chat_id_by_user_id=overrides.pop("get_user_chat_id_by_user_id", lambda user_id: 999),
            get_reminder=overrides.pop("get_reminder", lambda rid: source),
            get_source_chat_title_for_self_remind=overrides.pop("get_source_chat_title_for_self_remind", title_helper),
            get_self_remind_event_base=overrides.pop("get_self_remind_event_base", lambda src: object()),
            extract_event_datetime_from_text=overrides.pop("extract_event_datetime_from_text", lambda text, base: event_at),
            build_self_remind_choice_keyboard=overrides.pop("build_self_remind_choice_keyboard", lambda rid: f"choice-kb:{rid}"),
            build_self_remind_event_before_keyboard=overrides.pop("build_self_remind_event_before_keyboard", lambda rid: f"event-kb:{rid}"),
            msg_invalid_reminder_id=overrides.pop("msg_invalid_reminder_id", "invalid id"),
            msg_user_context_missing=overrides.pop("msg_user_context_missing", "user missing"),
            msg_source_reminder_not_found=overrides.pop("msg_source_reminder_not_found", "source missing"),
            msg_event_date_not_found=overrides.pop("msg_event_date_not_found", "event missing"),
            msg_unknown_self_remind_mode=overrides.pop("msg_unknown_self_remind_mode", "unknown mode"),
        )
    )
    assert not overrides, f"unused overrides: {overrides}"
    return query


def test_mode_regular_opens_regular_choice_keyboard():
    query = run_mode(data="selfremind:mode:123:regular")

    assert query.edited_texts == ['Когда напомнить тебе о "футбол завтра" из чата "Исходный чат"?']
    assert query.edited_markups == ["choice-kb:123"]
    assert query.answers == [("Выбери время", None)]


def test_mode_event_opens_event_before_keyboard():
    query = run_mode(data="selfremind:mode:123:event")

    assert query.edited_texts == [
        "Я понял, что событие из напоминания состоится 15.07 10:30.\n"
        "За сколько до этого времени напомнить?"
    ]
    assert query.edited_markups == ["event-kb:123"]
    assert query.answers == [("Выбери время", None)]


def test_mode_event_falls_back_when_event_date_not_found():
    query = run_mode(
        data="selfremind:mode:123:event",
        extract_event_datetime_from_text=lambda text, base: None,
    )

    assert query.edited_texts == ["event missing"]
    assert query.edited_markups == ["choice-kb:123"]
    assert query.answers == [("Не смог понять дату события. Выбери обычное напоминание или время вручную.", None)]


def test_mode_negative_paths():
    assert run_mode(data="selfremind:mode:bad:regular").answers == [("invalid id", True)]
    assert run_mode(query=Query(user_id=None)).answers == [("user missing", True)]
    assert run_mode(get_user_chat_id_by_user_id=lambda user_id: None).answers == [(SELF_REMIND_PRIVATE_START_MESSAGE, True)]
    assert run_mode(get_reminder=lambda rid: None).answers == [("source missing", True)]
    assert run_mode(data="selfremind:mode:123:weird").answers == [("unknown mode", True)]


def test_snooze_callback_uses_self_remind_initial_flow_helpers():
    import ast
    from pathlib import Path

    source = Path("dkreminders_bot/callbacks/reminder_callback_router.py").read_text()
    tree = ast.parse(source)

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_reminder_callback"
    ]
    assert len(nodes) == 1

    snooze_source = ast.get_source_segment(source, nodes[0])

    start = snooze_source.index('if data.startswith("selfremind:ask:"):')
    end = snooze_source.index('if data.startswith("selfremind:event_custom:"):', start)
    initial_source = snooze_source[start:end]

    assert "handle_self_remind_ask(" in initial_source
    assert "handle_self_remind_cancel_personal(" in initial_source
    assert "handle_self_remind_back(" in initial_source
    assert "handle_self_remind_mode(" in initial_source
    assert "target_chat_id = get_user_chat_id_by_user_id" not in initial_source
    assert "src = get_reminder(rid)" not in initial_source


def test_main_reexports_self_remind_initial_helpers():
    assert main.handle_self_remind_ask is handle_self_remind_ask
    assert main.handle_self_remind_cancel_personal is handle_self_remind_cancel_personal
    assert main.handle_self_remind_back is handle_self_remind_back
    assert main.handle_self_remind_mode is handle_self_remind_mode
