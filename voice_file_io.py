"""Telegram voice file download helpers."""

import os
import tempfile
from typing import Any


async def download_telegram_file_bytes(tg_file: Any, suffix: str = ".ogg") -> bytes:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)

        with open(tmp_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        if not audio_bytes:
            raise RuntimeError("Telegram voice file пустой")

        return audio_bytes
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
