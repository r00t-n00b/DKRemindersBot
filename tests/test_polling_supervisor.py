import logging

import pytest

from dkreminders_bot.utils.polling_supervisor import (
    is_transient_polling_error,
    run_polling_forever,
)


class FakeNetworkError(Exception):
    __module__ = "telegram.error"


class FakeBadToken(Exception):
    __module__ = "telegram.error"


class FakeHttpxConnectError(Exception):
    __module__ = "httpx"


def test_recognizes_telegram_network_error():
    FakeNetworkError.__name__ = "NetworkError"
    assert is_transient_polling_error(FakeNetworkError("network failed"))


def test_recognizes_httpx_connect_error():
    FakeHttpxConnectError.__name__ = "ConnectError"
    assert is_transient_polling_error(
        FakeHttpxConnectError("[Errno -3] Temporary failure in name resolution")
    )


def test_recognizes_nested_dns_failure():
    outer = RuntimeError("startup failed")
    outer.__cause__ = OSError("Temporary failure in name resolution")

    assert is_transient_polling_error(outer)


def test_does_not_retry_unknown_programming_error():
    assert not is_transient_polling_error(ValueError("broken configuration"))


def test_retries_transient_failures_with_bounded_backoff():
    FakeNetworkError.__name__ = "NetworkError"

    attempts = 0
    sleeps = []

    def run():
        nonlocal attempts
        attempts += 1
        if attempts <= 5:
            raise FakeNetworkError("temporary")

    run_polling_forever(
        run,
        logger=logging.getLogger("test"),
        sleep=sleeps.append,
        initial_delay=5,
        max_delay=60,
    )

    assert attempts == 6
    assert sleeps == [5, 10, 20, 40, 60]


def test_non_transient_failure_is_not_hidden():
    def run():
        raise ValueError("real bug")

    with pytest.raises(ValueError, match="real bug"):
        run_polling_forever(
            run,
            logger=logging.getLogger("test"),
            sleep=lambda _: None,
        )
