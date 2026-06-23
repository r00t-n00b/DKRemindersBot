import asyncio

import main
from reply_utils import safe_reply


class SyncMessage:
    def __init__(self):
        self.calls = []

    def reply_text(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return "ok"


class AsyncMessage:
    def __init__(self):
        self.calls = []

    async def reply_text(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return "ok"


class NoReplyText:
    pass


def test_safe_reply_calls_sync_reply_text():
    async def run():
        message = SyncMessage()

        await safe_reply(message, "hello", parse_mode="HTML")

        assert message.calls == [("hello", {"parse_mode": "HTML"})]

    asyncio.run(run())


def test_safe_reply_awaits_async_reply_text():
    async def run():
        message = AsyncMessage()

        await safe_reply(message, "hello", disable_web_page_preview=True)

        assert message.calls == [("hello", {"disable_web_page_preview": True})]

    asyncio.run(run())


def test_safe_reply_ignores_missing_message_or_reply_text():
    async def run():
        await safe_reply(None, "hello")
        await safe_reply(NoReplyText(), "hello")

    asyncio.run(run())


def test_main_reexports_safe_reply_for_existing_callers():
    assert main.safe_reply is safe_reply
