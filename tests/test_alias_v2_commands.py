import asyncio
from types import SimpleNamespace


class DummyMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _mk_private(text, args=None, user_id=123):
    message = DummyMessage(text)
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=456, type="private", title=None),
        effective_message=message,
        effective_user=SimpleNamespace(
            id=user_id,
            username="owner",
            first_name="Owner",
            last_name=None,
        ),
        message=message,
    )
    context = SimpleNamespace(args=args or [], user_data={})
    return update, context, message


def test_aliases_command_shows_only_current_users_aliases(main_module):
    main_module.set_chat_alias("TeamA", 777, "My Group", created_by=123)
    main_module.set_user_alias("Natasha", 42, 4242, "natasha", created_by=123)

    main_module.set_chat_alias("OtherTeam", 888, "Other Group", created_by=999)
    main_module.set_user_alias("OtherUser", 99, 9999, "other", created_by=999)

    update, context, message = _mk_private("/aliases", user_id=123)

    asyncio.run(main_module.aliases_command(update, context))

    assert len(message.replies) == 1
    reply, _ = message.replies[0]

    assert "TeamA" in reply
    assert "My Group" in reply
    assert "Natasha" in reply
    assert "@natasha" in reply or "natasha" in reply

    assert "OtherTeam" not in reply
    assert "OtherUser" not in reply


def test_aliases_command_empty_state(main_module):
    update, context, message = _mk_private("/aliases", user_id=123)

    asyncio.run(main_module.aliases_command(update, context))

    assert len(message.replies) == 1
    reply, _ = message.replies[0]

    assert "алиас" in reply.lower()
    assert "нет" in reply.lower() or "пока" in reply.lower()


def test_unalias_command_deletes_user_and_chat_alias_for_current_user_only(main_module):
    main_module.set_chat_alias("TeamA", 777, "My Group", created_by=123)
    main_module.set_user_alias("TeamA", 42, 4242, "natasha", created_by=123)

    main_module.set_chat_alias("TeamA", 888, "Other Group", created_by=999)
    main_module.set_user_alias("TeamA", 99, 9999, "other", created_by=999)

    update, context, message = _mk_private("/unalias TeamA", args=["TeamA"], user_id=123)

    asyncio.run(main_module.unalias_command(update, context))

    assert main_module.get_chat_id_by_alias("TeamA", created_by=123) is None
    assert main_module.get_user_alias_chat_id("TeamA", created_by=123) is None

    assert main_module.get_chat_id_by_alias("TeamA", created_by=999) == 888
    assert main_module.get_user_alias_chat_id("TeamA", created_by=999) == 9999

    assert len(message.replies) == 1
    reply, _ = message.replies[0]
    assert "TeamA" in reply


def test_unalias_command_unknown_alias_replies_not_found(main_module):
    update, context, message = _mk_private("/unalias Missing", args=["Missing"], user_id=123)

    asyncio.run(main_module.unalias_command(update, context))

    assert len(message.replies) == 1
    reply, _ = message.replies[0]
    assert "Missing" in reply
    assert "не найден" in reply or "нет" in reply.lower()


def test_renamealias_command_renames_both_alias_types_for_current_user_only(main_module):
    main_module.set_chat_alias("TeamA", 777, "My Group", created_by=123)
    main_module.set_user_alias("TeamA", 42, 4242, "natasha", created_by=123)

    main_module.set_chat_alias("TeamA", 888, "Other Group", created_by=999)
    main_module.set_user_alias("TeamA", 99, 9999, "other", created_by=999)

    update, context, message = _mk_private(
        "/renamealias TeamA -> Squad",
        args=["TeamA", "->", "Squad"],
        user_id=123,
    )

    asyncio.run(main_module.renamealias_command(update, context))

    assert main_module.get_chat_id_by_alias("TeamA", created_by=123) is None
    assert main_module.get_user_alias_chat_id("TeamA", created_by=123) is None

    assert main_module.get_chat_id_by_alias("Squad", created_by=123) == 777
    assert main_module.get_user_alias_chat_id("Squad", created_by=123) == 4242

    assert main_module.get_chat_id_by_alias("TeamA", created_by=999) == 888
    assert main_module.get_user_alias_chat_id("TeamA", created_by=999) == 9999

    assert len(message.replies) == 1
    reply, _ = message.replies[0]
    assert "TeamA" in reply
    assert "Squad" in reply


def test_renamealias_command_conflict_replies_error(main_module):
    main_module.set_chat_alias("TeamA", 777, "My Group", created_by=123)
    main_module.set_chat_alias("Squad", 888, "Squad Group", created_by=123)

    update, context, message = _mk_private(
        "/renamealias TeamA -> squad",
        args=["TeamA", "->", "squad"],
        user_id=123,
    )

    asyncio.run(main_module.renamealias_command(update, context))

    assert main_module.get_chat_id_by_alias("TeamA", created_by=123) == 777
    assert main_module.get_chat_id_by_alias("Squad", created_by=123) == 888

    assert len(message.replies) == 1
    reply, _ = message.replies[0]
    assert "уже существует" in reply


def test_linkuser_command_rejects_alias_that_conflicts_with_chat_alias(main_module, monkeypatch):
    main_module.set_chat_alias("Natasha", 777, "My Group", created_by=123)

    called = False

    def fake_get_private_chat_id_by_username(username):
        nonlocal called
        called = True
        return 4242

    monkeypatch.setattr(
        main_module,
        "get_private_chat_id_by_username",
        fake_get_private_chat_id_by_username,
    )

    update, context, message = _mk_private(
        "/linkuser Natasha @natasha",
        args=["Natasha", "@natasha"],
        user_id=123,
    )

    asyncio.run(main_module.linkuser_command(update, context))

    assert called is False
    assert main_module.get_user_alias_chat_id("Natasha", created_by=123) is None

    assert len(message.replies) == 1
    reply, _ = message.replies[0]
    assert "Natasha" in reply
    assert "chat-alias" in reply or "алиас" in reply.lower()
