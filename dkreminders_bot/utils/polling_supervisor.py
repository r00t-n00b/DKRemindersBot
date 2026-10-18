"""Keep Telegram polling alive across transient startup/network failures."""

from __future__ import annotations

import time
from typing import Callable


def is_transient_polling_error(exc: BaseException) -> bool:
    """Return True only for errors that are reasonable to retry indefinitely."""
    for current in _exception_chain(exc):
        module = type(current).__module__
        name = type(current).__name__

        if module.startswith("telegram") and name in {
            "NetworkError",
            "TimedOut",
        }:
            return True

        if module.startswith("httpx") and name in {
            "ConnectError",
            "ConnectTimeout",
            "ReadTimeout",
            "WriteTimeout",
            "PoolTimeout",
            "RemoteProtocolError",
        }:
            return True

        if isinstance(current, (ConnectionError, TimeoutError)):
            return True

        message = str(current).lower()
        if any(
            marker in message
            for marker in (
                "temporary failure in name resolution",
                "name or service not known",
                "nodename nor servname provided",
                "connection reset by peer",
                "connection refused",
                "network is unreachable",
            )
        ):
            return True

    return False


def _exception_chain(exc: BaseException):
    seen = set()
    current = exc

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def run_polling_forever(
    run_polling: Callable[[], None],
    *,
    logger,
    sleep: Callable[[float], None] = time.sleep,
    initial_delay: float = 5.0,
    max_delay: float = 60.0,
) -> None:
    """Restart polling after transient network failures with bounded backoff."""
    delay = initial_delay

    while True:
        try:
            run_polling()
            return
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            if not is_transient_polling_error(exc):
                raise

            logger.warning(
                "POLLING_TRANSIENT_FAILURE error_type=%s error=%s; retrying in %.0fs",
                type(exc).__name__,
                exc,
                delay,
            )

            sleep(delay)
            delay = min(delay * 2, max_delay)
