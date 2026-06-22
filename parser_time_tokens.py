"""Token-level time extraction helpers for reminder parsers."""

import re
from typing import List, Tuple


TIME_TOKEN_RE = re.compile(r"^\d{1,2}[:.]\d{2}$")


VAGUE_TIME_WORDS = {
    "утром": (10, 0),
    "morning": (10, 0),
    "вечером": (18, 0),
    "evening": (18, 0),
}


def _extract_time_from_tokens(
    tokens: List[str],
    default_hour: int = 11,
    default_minute: int = 0,
) -> Tuple[List[str], int, int]:
    if tokens:
        last_token = tokens[-1].strip(" ,.!?:;").lower()
        if last_token in VAGUE_TIME_WORDS:
            hour, minute = VAGUE_TIME_WORDS[last_token]
            return tokens[:-1], hour, minute

    if tokens and TIME_TOKEN_RE.fullmatch(tokens[-1]):
        raw = tokens[-1]
        sep = ":" if ":" in raw else "."
        h_s, m_s = raw.split(sep, 1)

        # Важно: если это невалидное "время" (например 29.11), не падаем,
        # а считаем, что времени нет, и оставляем токен как есть.
        try:
            hour = int(h_s)
            minute = int(m_s)
        except ValueError:
            return tokens, default_hour, default_minute

        if 0 <= hour < 24 and 0 <= minute < 60:
            core = tokens[:-1]
            return core, hour, minute

        return tokens, default_hour, default_minute

    return tokens, default_hour, default_minute
