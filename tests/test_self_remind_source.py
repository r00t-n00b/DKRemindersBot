import pytest

import main
from self_remind_source import (
    format_self_remind_text,
    get_query_source_chat_title,
    get_source_chat_title_for_self_remind,
)


class Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_format_self_remind_text():
    assert format_self_remind_text("Group Chat", "buy milk") == 'Из чата "Group Chat": buy milk'


def test_get_query_source_chat_title_prefers_chat_title():
    query = Obj(message=Obj(chat=Obj(title="Group Title", full_name="Full Name")))

    assert get_query_source_chat_title(query) == "Group Title"


def test_get_query_source_chat_title_falls_back_to_full_name():
    query = Obj(message=Obj(chat=Obj(title=None, full_name="Full Name")))

    assert get_query_source_chat_title(query) == "Full Name"


def test_get_query_source_chat_title_falls_back_to_default_without_message():
    query = Obj(message=None)

    assert get_query_source_chat_title(query) == "этого чата"


class FakeBot:
    async def get_chat(self, chat_id):
        assert chat_id == 123
        return Obj(title=None, full_name=None, username="source_user")


class FailingBot:
    async def get_chat(self, chat_id):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_get_source_chat_title_for_self_remind_uses_bot_chat():
    context = Obj(bot=FakeBot())
    src = Obj(chat_id=123)
    query = Obj(message=Obj(chat=Obj(title="Fallback Title")))

    assert await get_source_chat_title_for_self_remind(context, src, query) == "source_user"


@pytest.mark.asyncio
async def test_get_source_chat_title_for_self_remind_falls_back_to_query_title_on_error():
    context = Obj(bot=FailingBot())
    src = Obj(chat_id=123)
    query = Obj(message=Obj(chat=Obj(title="Fallback Title")))

    assert await get_source_chat_title_for_self_remind(context, src, query) == "Fallback Title"


def test_main_reexports_self_remind_source_helpers_for_existing_callers():
    assert main.format_self_remind_text is format_self_remind_text
    assert main.get_query_source_chat_title is get_query_source_chat_title
    assert main.get_source_chat_title_for_self_remind is get_source_chat_title_for_self_remind
