import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


class DummyMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _mk_private_remind(text, args=None, user_id=123, chat_id=456):
    message = DummyMessage(text)
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id, type="private", title=None),
        effective_message=message,
        effective_user=SimpleNamespace(
            id=user_id,
            username="owner",
            first_name="Owner",
            last_name=None,
        ),
        message=message,
    )
    context = SimpleNamespace(args=args if args is not None else text.split()[1:], user_data={})
    return update, context, message


def _reply_text(message):
    assert message.replies
    return "\n".join(text for text, _kwargs in message.replies)


def test_remind_me_without_rest_replies_help(main_module):
    update, context, message = _mk_private_remind("/remind me", args=["me"])

    asyncio.run(main_module.remind_command(update, context))

    reply = _reply_text(message)

    assert "После me нужно указать дату и текст" in reply
    assert "/remind me on Tuesday - алкоголь под КС" in reply


def test_remind_username_not_started_replies_clear_error(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "get_user_chat_id_by_username", lambda username: None)

    update, context, message = _mk_private_remind(
        "/remind @someone tomorrow 10:00 - привет",
        args=["@someone", "tomorrow", "10:00", "-", "привет"],
    )

    asyncio.run(main_module.remind_command(update, context))

    reply = _reply_text(message)

    assert "@someone" in reply
    assert "не нажимал(а) Start" in reply
    assert "нажмет Start" in reply


def test_remind_username_without_rest_replies_help(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "get_user_chat_id_by_username", lambda username: 777)

    update, context, message = _mk_private_remind(
        "/remind @someone",
        args=["@someone"],
    )

    asyncio.run(main_module.remind_command(update, context))

    reply = _reply_text(message)

    assert "После @someone нужно указать дату и текст" in reply
    assert "/remind @someone tomorrow 10:00 - привет" in reply


def test_remind_user_alias_without_rest_replies_help(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "get_user_alias_chat_id_for_user", lambda alias, user_id: 777)
    monkeypatch.setattr(main_module, "get_chat_id_by_alias_for_user", lambda alias, user_id: None)

    update, context, message = _mk_private_remind(
        "/remind Natasha",
        args=["Natasha"],
    )

    asyncio.run(main_module.remind_command(update, context))

    reply = _reply_text(message)

    assert "После alias нужно указать дату и текст" in reply
    assert "/remind Natasha 28.11 12:00 - завтра футбол" in reply


def test_remind_chat_alias_without_rest_replies_help(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "get_user_alias_chat_id_for_user", lambda alias, user_id: None)
    monkeypatch.setattr(main_module, "get_chat_id_by_alias_for_user", lambda alias, user_id: -100777)

    update, context, message = _mk_private_remind(
        "/remind football",
        args=["football"],
    )

    asyncio.run(main_module.remind_command(update, context))

    reply = _reply_text(message)

    assert "После alias нужно указать дату и текст" in reply
    assert "/remind football 28.11 12:00 - завтра футбол" in reply


def test_remind_unknown_alias_with_parseable_rest_replies_explicit_alias_error(main_module, monkeypatch):
    def fake_parse_date_time_smart(raw, now):
        assert raw == "tomorrow 10:00 - привет"
        return datetime(2026, 6, 13, 10, 0, tzinfo=TZ), "привет"

    monkeypatch.setattr(main_module, "get_user_alias_chat_id_for_user", lambda alias, user_id: None)
    monkeypatch.setattr(main_module, "get_chat_id_by_alias_for_user", lambda alias, user_id: None)
    monkeypatch.setattr(main_module, "parse_date_time_smart", fake_parse_date_time_smart)

    update, context, message = _mk_private_remind(
        "/remind MissingAlias tomorrow 10:00 - привет",
        args=["MissingAlias", "tomorrow", "10:00", "-", "привет"],
    )

    asyncio.run(main_module.remind_command(update, context))

    reply = _reply_text(message)

    assert 'Алиаса "MissingAlias" не существует' in reply
    assert "Используй команду без него" in reply
    assert "/linkuser" in reply
    assert "/linkchat" in reply
    assert "/help" in reply


def test_remind_date_like_first_token_is_not_treated_as_alias(main_module, monkeypatch):
    alias_lookups = []

    def fake_user_alias(alias, user_id):
        alias_lookups.append(("user", alias, user_id))
        return None

    def fake_chat_alias(alias, user_id):
        alias_lookups.append(("chat", alias, user_id))
        return None

    def fake_parse_date_time_smart(raw, now):
        assert raw == "tomorrow 10:00 - привет"
        return datetime(2026, 6, 13, 10, 0, tzinfo=TZ), "привет"

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append(
            {
                "chat_id": chat_id,
                "text": text,
                "remind_at": remind_at,
                "created_by": created_by,
                "template_id": template_id,
            }
        )
        return 999

    monkeypatch.setattr(main_module, "get_user_alias_chat_id_for_user", fake_user_alias)
    monkeypatch.setattr(main_module, "get_chat_id_by_alias_for_user", fake_chat_alias)
    monkeypatch.setattr(main_module, "parse_date_time_smart", fake_parse_date_time_smart)
    monkeypatch.setattr(main_module, "add_reminder", fake_add_reminder)

    update, context, message = _mk_private_remind(
        "/remind tomorrow 10:00 - привет",
        args=["tomorrow", "10:00", "-", "привет"],
        chat_id=456,
        user_id=123,
    )

    asyncio.run(main_module.remind_command(update, context))

    assert alias_lookups == []
    assert created == [
        {
            "chat_id": 456,
            "text": "привет",
            "remind_at": datetime(2026, 6, 13, 10, 0, tzinfo=TZ),
            "created_by": 123,
            "template_id": None,
        }
    ]

    reply = _reply_text(message)
    assert "Ок, напомню" in reply
