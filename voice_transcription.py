"""Voice message transcription flow."""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from voice_errors import VoiceTelegramFileError, VoiceTranscriptionServiceError


_DEP_NAMES = [
    "_format_known_aliases_for_voice_prompt",
    "_gemini_transcribe_audio_with_retries",
    "download_telegram_file_bytes",
    "genai",
    "genai_types",
    "logger",
    "os",
]


VOICE_TELEGRAM_FILE_ATTEMPTS = 3
VOICE_TELEGRAM_FILE_RETRY_DELAYS = (0.5, 1.0)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


async def _retry_telegram_voice_step(*, step_name: str, operation):
    last_error = None

    for attempt in range(1, VOICE_TELEGRAM_FILE_ATTEMPTS + 1):
        start = time.monotonic()
        try:
            result = await operation()
            logger.info(
                "VOICE_TELEGRAM_%s_SUCCESS attempt=%s duration_ms=%s",
                step_name,
                attempt,
                _elapsed_ms(start),
            )
            return result
        except Exception as exc:
            if step_name == "DOWNLOAD" and "пуст" in str(exc).lower():
                raise

            last_error = exc
            logger.warning(
                "VOICE_TELEGRAM_%s_FAILED attempt=%s duration_ms=%s error_type=%s error=%s",
                step_name,
                attempt,
                _elapsed_ms(start),
                type(exc).__name__,
                exc,
            )

            if attempt >= VOICE_TELEGRAM_FILE_ATTEMPTS:
                break

            delay = VOICE_TELEGRAM_FILE_RETRY_DELAYS[min(attempt - 1, len(VOICE_TELEGRAM_FILE_RETRY_DELAYS) - 1)]
            logger.info(
                "VOICE_TELEGRAM_%s_RETRY attempt=%s next_delay_sec=%s",
                step_name,
                attempt + 1,
                delay,
            )
            await asyncio.sleep(delay)

    raise VoiceTelegramFileError(f"Telegram voice {step_name.lower()} failed") from last_error


async def transcribe_voice_message_impl(update, context, deps):
    _apply_deps(deps)
    total_start = time.monotonic()
    message = update.effective_message
    user = update.effective_user
    if user is None:
        raise ValueError("Нет пользователя")

    if message is None or message.voice is None:
        raise ValueError("Нет голосового сообщения")

    token = os.environ.get("GEMINI_API_KEY", "").strip()
    if not token:
        raise RuntimeError("GEMINI_API_KEY не задан")

    if genai is None or genai_types is None:
        raise RuntimeError("Пакет google-genai не установлен")

    tg_file = await _retry_telegram_voice_step(
        step_name="GET_FILE",
        operation=lambda: context.bot.get_file(message.voice.file_id),
    )
    audio_bytes = await _retry_telegram_voice_step(
        step_name="DOWNLOAD",
        operation=lambda: download_telegram_file_bytes(tg_file, suffix=".ogg"),
    )

    logger.info("VOICE_AUDIO_READY bytes=%s", len(audio_bytes))

    client = genai.Client(api_key=token)

    transcription_start = time.monotonic()
    try:
        result = await _gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=audio_bytes,
            aliases_prompt=_format_known_aliases_for_voice_prompt(update.effective_user.id),
        )
    except Exception as exc:
        logger.warning(
            "VOICE_TRANSCRIPTION_SERVICE_FAILED duration_ms=%s error_type=%s error=%s",
            _elapsed_ms(transcription_start),
            type(exc).__name__,
            exc,
        )
        raise VoiceTranscriptionServiceError("Voice transcription service failed") from exc

    logger.info(
        "VOICE_TRANSCRIPTION_TOTAL_SUCCESS duration_ms=%s",
        _elapsed_ms(total_start),
    )
    return result
