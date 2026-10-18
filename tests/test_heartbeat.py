import asyncio
import logging

import pytest

from dkreminders_bot.utils.heartbeat import heartbeat_worker, send_heartbeat


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_send_heartbeat_uses_timeout_and_user_agent():
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["user_agent"] = request.get_header("User-agent")
        return FakeResponse(200)

    send_heartbeat(
        "https://example.test/heartbeat",
        timeout=7,
        urlopen=fake_urlopen,
    )

    assert seen == {
        "url": "https://example.test/heartbeat",
        "timeout": 7,
        "user_agent": "DKRemindersBot/heartbeat",
    }


def test_send_heartbeat_rejects_http_error():
    def fake_urlopen(request, timeout):
        return FakeResponse(500)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        send_heartbeat(
            "https://example.test/heartbeat",
            urlopen=fake_urlopen,
        )


@pytest.mark.asyncio
async def test_heartbeat_disabled_without_url():
    await heartbeat_worker(
        None,
        logger=logging.getLogger("test"),
        interval=0,
    )


@pytest.mark.asyncio
async def test_heartbeat_failure_does_not_kill_worker(monkeypatch):
    calls = 0
    sleep_calls = 0

    def sender(url, *, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("monitor temporarily unavailable")

    async def fake_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(
        "dkreminders_bot.utils.heartbeat.asyncio.sleep",
        fake_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await heartbeat_worker(
            "https://example.test/heartbeat",
            logger=logging.getLogger("test"),
            interval=60,
            sender=sender,
        )

    assert calls == 2
