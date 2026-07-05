import asyncio
import os

import pytest

import main
from dkreminders_bot.integrations.voice_file_io import download_telegram_file_bytes


class FakeTelegramFile:
    def __init__(self, data: bytes):
        self.data = data
        self.downloaded_to = None

    async def download_to_drive(self, path):
        self.downloaded_to = path
        with open(path, "wb") as f:
            f.write(self.data)


def test_download_telegram_file_bytes_returns_bytes_and_removes_temp_file():
    async def run():
        tg_file = FakeTelegramFile(b"voice-bytes")

        data = await download_telegram_file_bytes(tg_file)

        assert data == b"voice-bytes"
        assert tg_file.downloaded_to is not None
        assert not os.path.exists(tg_file.downloaded_to)

    asyncio.run(run())


def test_download_telegram_file_bytes_rejects_empty_file_and_removes_temp_file():
    async def run():
        tg_file = FakeTelegramFile(b"")

        with pytest.raises(RuntimeError, match="Telegram voice file пустой"):
            await download_telegram_file_bytes(tg_file)

        assert tg_file.downloaded_to is not None
        assert not os.path.exists(tg_file.downloaded_to)

    asyncio.run(run())


def test_main_uses_voice_file_io_helper_instead_of_tempfile_directly():
    from pathlib import Path

    main_source = Path("main.py").read_text()
    transcription_source = Path("dkreminders_bot/integrations/voice_transcription.py").read_text()

    assert main.download_telegram_file_bytes is download_telegram_file_bytes
    assert "download_telegram_file_bytes(tg_file, suffix=\".ogg\")" in transcription_source
    assert "download_telegram_file_bytes(tg_file, suffix=\".ogg\")" not in main_source
    assert "import tempfile" not in main_source
    assert "tempfile." not in main_source
