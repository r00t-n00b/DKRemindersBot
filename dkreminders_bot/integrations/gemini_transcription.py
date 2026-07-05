"""Gemini audio transcription retry/fallback helper."""

import asyncio
import os
import time
from typing import Optional

from dkreminders_bot.integrations.gemini_errors import (
    _is_gemini_quota_error,
    _is_transient_gemini_error,
    _is_unsupported_gemini_model_error,
)


async def gemini_transcribe_audio_with_retries(
    *,
    client,
    audio_bytes: bytes,
    genai_types,
    logger,
    attempts_per_model: Optional[int] = None,
    aliases_prompt: str = "",
) -> str:
    models_raw = os.environ.get(
        "GEMINI_TRANSCRIBE_MODELS",
        "gemini-2.5-flash-lite,gemini-2.5-flash",
    )

    models = [m.strip() for m in models_raw.split(",") if m.strip()]
    if not models:
        models = ["gemini-2.5-flash-lite"]

    last_error: Optional[Exception] = None
    if attempts_per_model is None:
        try:
            attempts_per_model = int(os.environ.get("GEMINI_TRANSCRIBE_ATTEMPTS", "1"))
        except ValueError:
            attempts_per_model = 1

    attempts_per_model = max(1, min(5, attempts_per_model))

    try:
        attempt_timeout_sec = float(os.environ.get("GEMINI_TRANSCRIBE_ATTEMPT_TIMEOUT_SEC", "15"))
    except ValueError:
        attempt_timeout_sec = 15.0
    attempt_timeout_sec = max(3.0, min(60.0, attempt_timeout_sec))

    for model in models:
        for attempt in range(1, attempts_per_model + 1):
            try:
                attempt_start = time.monotonic()
                logger.info(
                    "GEMINI_TRANSCRIPTION_ATTEMPT_START model=%s attempt=%s timeout_sec=%s",
                    model,
                    attempt,
                    attempt_timeout_sec,
                )

                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model,
                        contents=[
                        genai_types.Part.from_bytes(
                            data=audio_bytes,
                            mime_type="audio/ogg",
                        ),
                        (
                            "You are normalizing a Telegram voice reminder.\n"
                            "\n"
                            "Listen to the audio and return only one line in this exact format:\n"
                            "<optional target alias> <date/time expression> - <reminder text>\n"
                            "\n"
                            "The output must be directly usable after '/remind '.\n"
                            "\n"
                            "Rules:\n"
                            "- Return only the normalized reminder command. No quotes. No markdown. No commentary.\n"
                            "- Preserve the reminder text meaning.\n"
                            "- Never change an explicitly spoken time. If the user says 'в 12', return '12:00'.\n"
                            "- If the user says 'в 14:55', return '14:55' exactly.\n"
                            "- Remove leading phrases like 'напомни', 'напомни мне', 'поставь напоминание', 'remind me'.\n"
                            "- Convert spoken Russian numbers to digits where needed.\n"
                            "- Convert Russian month names to English month names.\n"
                            "- Convert Russian number words to digits in intervals: 'два часа' -> '2 часа', 'три дня' -> '3 дня'.\n"
                            "- Convert fractional Russian intervals to parser-friendly units: 'полчаса' -> 'every 30 minutes', 'полтора часа' -> 'every 90 minutes'.\n"
                            "- Do not calculate actual dates. Keep relative expressions like 'завтра', 'следующий понедельник', '29 may'.\n"
                            "- Support one-off reminders, recurring reminders, private target aliases, and chat aliases.\n"
                            "- Use a target alias only if it appears in the known aliases list below.\n"
                            "- Do not invent aliases or usernames.\n"
                            "- If a spoken person name is an inflected form of a known user alias, normalize it to that alias.\n"
                            "- Examples: known alias 'Наташа': 'Наташе', 'Наташу', 'Наташи' -> 'Наташа'.\n"
                            "- Examples: known alias 'Миша': 'Мише', 'Мишу', 'Миши' -> 'Миша'.\n"
                            "- Examples: known alias 'Леша': 'Леше', 'Лёше', 'Лешу', 'Лёшу' -> 'Леша'.\n"
                            "- If the spoken person name is not in known aliases, keep it inside reminder text, not as target.\n"
                            "- If the user says only a time like 'в 11 купить молоко', return '11:00 - купить молоко'.\n"
                            "- If the user says 'завтра в 11 купить молоко', return 'завтра 11:00 - купить молоко'.\n"
                            "- If the user says 'напомни завтра в 14:55 позвонить доктору', return 'завтра 14:55 - позвонить доктору'.\n"
                            "- If the user says 'в следующий понедельник в 22:00 спросить как дела', return 'следующий понедельник 22:00 - спросить как дела'.\n"
                            "- If the user says 'двадцать девятого мая в восемнадцать сорок шесть спросить как дела', return '29 may 18:46 - спросить как дела'.\n"
                            "- If known user alias list contains 'Наташа' and user says 'напомнить Наташе завтра в 12 позвонить', return 'Наташа завтра 12:00 - позвонить'.\n"
                            "- If known user alias list does not contain 'Наташа', return 'завтра 12:00 - позвонить Наташе'.\n"
                            "- If known chat alias list contains 'football' and user says 'напомни football завтра в 12 матч', return 'football завтра 12:00 - матч'.\n"
                            "- For recurring reminders, keep a parser-friendly recurring expression with explicit time.\n"
                            "- If the user says 'каждый понедельник в 11 выпить таблетку', return 'каждый понедельник 11:00 - выпить таблетку'.\n"
                            "- If the user says 'каждый день в 9 пить воду', return 'каждый день 09:00 - пить воду'.\n"
                            "- If the user says 'напоминай каждые два часа пить воды', return 'каждые 2 часа - пить воды'.\n"
                            "- If the user says 'напоминай каждые полтора часа пить воды', return 'every 90 minutes - пить воды'.\n"
                            "- If the user says 'напоминай каждые полчаса пить воды', return 'every 30 minutes - пить воды'.\n"
                            "- If the user says 'every Monday at 11 take a pill', return 'every monday 11:00 - take a pill'.\n"
                            "- If the user says 'every day at 9 drink water', return 'every day 09:00 - drink water'.\n"
                            "\n"
                            f"{aliases_prompt}\n"
                        ),
                    ],
                    ),
                    timeout=attempt_timeout_sec,
                )

                duration_ms = int((time.monotonic() - attempt_start) * 1000)
                text = (getattr(result, "text", "") or "").strip()
                if text:
                    logger.info(
                        "GEMINI_TRANSCRIPTION_SUCCESS model=%s attempt=%s duration_ms=%s",
                        model,
                        attempt,
                        duration_ms,
                    )
                    return text

                last_error = RuntimeError(f"Gemini model {model} returned empty transcription")

            except Exception as e:
                last_error = e

                duration_ms = int((time.monotonic() - attempt_start) * 1000)
                unsupported_model = _is_unsupported_gemini_model_error(e)
                quota_error = _is_gemini_quota_error(e)
                timed_out = isinstance(e, asyncio.TimeoutError)
                transient = (timed_out or _is_transient_gemini_error(e)) and not quota_error

                logger.warning(
                    "GEMINI_TRANSCRIPTION_FAILED model=%s attempt=%s duration_ms=%s transient=%s unsupported_model=%s quota_error=%s timed_out=%s error_type=%s error=%s",
                    model,
                    attempt,
                    duration_ms,
                    transient,
                    unsupported_model,
                    quota_error,
                    timed_out,
                    type(e).__name__,
                    e,
                )

                if unsupported_model:
                    break

                if quota_error:
                    raise RuntimeError(
                        "Gemini quota/billing limit exceeded. "
                        "Проверь лимиты проекта или включи billing для Gemini API."
                    ) from e

                if not transient:
                    raise
            await asyncio.sleep(0.8 * attempt)

    raise RuntimeError(
        "Gemini временно не смог распознать голосовое после retry/fallback. "
        f"Последняя ошибка: {type(last_error).__name__}: {last_error}"
    )
