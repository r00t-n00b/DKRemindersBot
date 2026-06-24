"""Voice message transcription flow."""

from typing import Any, Dict, List, Optional, Tuple


_DEP_NAMES = [
    "_format_known_aliases_for_voice_prompt",
    "_gemini_transcribe_audio_with_retries",
    "download_telegram_file_bytes",
    "genai",
    "genai_types",
    "os",
]


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


async def transcribe_voice_message_impl(update, context, deps):
    _apply_deps(deps)
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

    tg_file = await context.bot.get_file(message.voice.file_id)
    audio_bytes = await download_telegram_file_bytes(tg_file, suffix=".ogg")

    client = genai.Client(api_key=token)

    return await _gemini_transcribe_audio_with_retries(
        client=client,
        audio_bytes=audio_bytes,
        aliases_prompt=_format_known_aliases_for_voice_prompt(update.effective_user.id),
    )
