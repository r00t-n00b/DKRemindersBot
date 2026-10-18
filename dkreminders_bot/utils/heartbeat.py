"""External liveness heartbeat for the long-running bot process."""

from __future__ import annotations

import asyncio
import urllib.request
from typing import Callable, Optional


def send_heartbeat(
    url: str,
    *,
    timeout: float = 10.0,
    urlopen: Callable = urllib.request.urlopen,
) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DKRemindersBot/heartbeat"},
        method="GET",
    )

    with urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if not 200 <= status < 300:
            raise RuntimeError(f"heartbeat returned HTTP {status}")


async def heartbeat_worker(
    url: Optional[str],
    *,
    logger,
    interval: float = 60.0,
    timeout: float = 10.0,
    sender: Callable = send_heartbeat,
) -> None:
    if not url:
        logger.info("External heartbeat disabled: HEARTBEAT_URL is not set")
        return

    logger.info("External heartbeat enabled")

    while True:
        try:
            await asyncio.to_thread(sender, url, timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "HEARTBEAT_SEND_FAILED error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )

        await asyncio.sleep(interval)
