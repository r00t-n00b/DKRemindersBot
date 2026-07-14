"""Gemini-based normalization for plain text reminder messages."""

import asyncio
import os


class GeminiTextNormalizationTemporaryError(RuntimeError):
    """Gemini text normalization failed because of a temporary/transient issue."""


async def normalize_plain_text_reminder_with_gemini_impl(
    text: str,
    created_by: int,
    *,
    genai,
    logger,
    format_known_aliases_for_voice_prompt,
    is_unsupported_gemini_model_error,
    is_gemini_quota_error,
    is_transient_gemini_error,
) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    token = os.environ.get("GEMINI_API_KEY", "").strip()
    if not token:
        raise RuntimeError("GEMINI_API_KEY не задан")

    if genai is None:
        raise RuntimeError("Пакет google-genai не установлен")

    models_raw = os.environ.get(
        "GEMINI_TEXT_NORMALIZE_MODELS",
        os.environ.get("GEMINI_TRANSCRIBE_MODELS", "gemini-2.5-flash-lite,gemini-2.5-flash"),
    )
    models = [m.strip() for m in models_raw.split(",") if m.strip()]
    if not models:
        models = ["gemini-2.5-flash-lite"]

    aliases_prompt = format_known_aliases_for_voice_prompt(created_by)
    client = genai.Client(api_key=token)
    last_error = None
    had_temporary_failure = False

    prompt = (
        "You are normalizing a Telegram text message into a reminder command.\n"
        "\n"
        "Return only one line in this exact format:\n"
        "<optional target alias> <date/time expression> - <reminder text>\n"
        "\n"
        "If the message is not a reminder request, return exactly:\n"
        "NO_REMINDER\n"
        "\n"
        "Rules:\n"
        "- Return only the normalized reminder command or NO_REMINDER. No quotes. No markdown. No commentary.\n"
        "- Preserve the reminder text meaning.\n"
        "- Remove leading phrases like 'напомни', 'напомни мне', 'поставь напоминание', 'remind me'.\n"
        "- Never change an explicitly written time. If the user says 'в 18', return '18:00'.\n"
        "- Convert Russian month names to English month names.\n"
        "- Convert Russian number words to digits in intervals: 'два часа' -> '2 часа', 'три дня' -> '3 дня'.\n"
        "- Convert fractional Russian intervals to parser-friendly recurring commands: 'каждые полчаса' -> 'every 30 minutes', 'каждые полтора часа' -> 'every 90 minutes'.\n"
        "- Do not calculate actual dates. Keep relative expressions like 'сегодня', 'завтра', 'следующий понедельник', '29 may'.\n"
        "- Support one-off reminders, recurring reminders, private target aliases, and chat aliases.\n"
        "- Use a target alias only if it appears in the known aliases list below.\n"
        "- Do not invent aliases or usernames.\n"
        "- If a person name is not in known aliases, keep it inside reminder text, not as target.\n"
        "- If the user says 'напомни мне сегодня поздравить Саню часов в 6 вечера', return 'сегодня 18:00 - поздравить Саню'.\n"
        "- If the user says 'напомни завтра в 14:55 позвонить доктору', return 'завтра 14:55 - позвонить доктору'.\n"
        "- If the user says 'каждые 3 дня пить лекарство', return 'каждые 3 дня - пить лекарство'.\n"
        "- If the user says 'напоминай каждые два часа пить воды', return 'каждые 2 часа - пить воды'.\n"
        "- If the user says 'напоминай каждые полтора часа пить воды', return 'every 90 minutes - пить воды'.\n"
        "- If the user says 'напоминай каждые полчаса пить воды', return 'every 30 minutes - пить воды'.\n"
        "- If the user says 'every 2 hours stretch', return 'every 2 hours - stretch'.\n"
        "\n"
        f"{aliases_prompt}\n"
        "\n"
        f"User message:\n{raw}\n"
    )

    for model in models:
        try:
            model_timeout = float(
                os.environ.get(
                    "GEMINI_MODEL_CALL_TIMEOUT_SECONDS",
                    os.environ.get("GEMINI_REMINDER_PARSE_TIMEOUT_SECONDS", "10"),
                )
            )
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=[prompt],
                ),
                timeout=model_timeout,
            )
            normalized = (getattr(result, "text", "") or "").strip()
            if normalized:
                logger.info(
                    "GEMINI_TEXT_NORMALIZE_SUCCESS model=%s normalized_kind=%s raw_len=%s normalized_len=%s",
                    model,
                    "no_reminder" if normalized == "NO_REMINDER" else "reminder",
                    len(raw),
                    len(normalized),
                )
                return normalized
            last_error = RuntimeError(f"Gemini model {model} returned empty text normalization")
        except asyncio.TimeoutError as e:
            last_error = e
            had_temporary_failure = True
            logger.warning(
                "GEMINI_TEXT_NORMALIZE_TIMEOUT model=%s timeout=%s raw_len=%s",
                model,
                model_timeout,
                len(raw),
            )
            continue
        except Exception as e:
            last_error = e

            unsupported_model = is_unsupported_gemini_model_error(e)
            quota_error = is_gemini_quota_error(e)
            transient = is_transient_gemini_error(e) and not quota_error

            logger.warning(
                "GEMINI_TEXT_NORMALIZE_FAILED model=%s transient=%s unsupported_model=%s quota_error=%s error_type=%s error=%s",
                model,
                transient,
                unsupported_model,
                quota_error,
                type(e).__name__,
                e,
            )

            if unsupported_model:
                continue

            if quota_error:
                raise RuntimeError(
                    "Gemini quota/billing limit exceeded. "
                    "Проверь лимиты проекта или включи billing для Gemini API."
                ) from e

            if transient:
                had_temporary_failure = True
                continue

            raise

    if had_temporary_failure:
        raise GeminiTextNormalizationTemporaryError(
            "Gemini временно не смог нормализовать текст после fallback. "
            f"Последняя ошибка: {type(last_error).__name__}: {last_error}"
        ) from last_error

    raise RuntimeError(
        "Gemini не смог нормализовать текст после fallback. "
        f"Последняя ошибка: {type(last_error).__name__}: {last_error}"
    )
