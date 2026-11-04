"""Validation and elapsed-time rules for configurable reminder nudges."""

import json
import re
from datetime import datetime

DEFAULT_GAPS = [20, 60, 240, 720]
MAX_GAPS = 20
MAX_INTERVAL_MINUTES = 525600


def validate_gaps(values):
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_GAPS:
        raise ValueError("Укажи от 1 до 20 промежутков")
    if any(type(v) is not int or not 1 <= v <= MAX_INTERVAL_MINUTES for v in values):
        raise ValueError("Промежуток должен быть от минуты до 365 дней")
    return list(values)


def decode_gaps(value, *, allow_empty=False):
    values = json.loads(value) if isinstance(value, str) else value
    if allow_empty and values == []:
        return []
    return validate_gaps(values)


def parse_interval(text):
    text = (text or "").lower().strip().replace(",", ".")
    text = re.sub(r"\s+и\s+", " ", text)
    pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(минут(?:а|ы|у)?|мин\.?|minutes?|mins?|м|час(?:а|ов)?|ч\.?|hours?|hrs?|h|день|дня|дней|дн\.?|д|days?|d)\s*")
    total, end, found = 0, 0, False
    for match in pattern.finditer(text):
        if text[end:match.start()].strip():
            raise ValueError("Например: 45 мин, 1 ч 30 мин или 2 дня")
        unit = match[2]
        factor = 60 if re.match(r"^(час|ч|hour|hr|h)", unit) else 1440 if re.match(r"^(д|day|d)", unit) else 1
        total += float(match[1]) * factor
        end, found = match.end(), True
    if not found or text[end:].strip() or not float(total).is_integer():
        raise ValueError("Например: 45 мин, 1 ч 30 мин или 2 дня")
    return validate_gaps([int(total)])[0]


def nudge_due(row, settings, now):
    if row.get("acked") or not row.get("delivered") or row.get("nudge_exhausted") or not settings["enabled"]:
        return False
    try:
        sent = datetime.fromisoformat(row["sent_at"])
        if sent.tzinfo is None or now.tzinfo is None:
            return False
        resume = settings.get("resume_after")
        if resume and sent.timestamp() <= datetime.fromisoformat(resume).timestamp():
            return False
        gaps = decode_gaps(row["nudge_policy_json"], allow_empty=True) if row.get("nudge_policy_json") is not None else DEFAULT_GAPS
        count = int(row.get("nudge_count") or 0)
        if not 0 <= count < len(gaps):
            return False
        if row.get("last_nudge_at"):
            last = datetime.fromisoformat(row["last_nudge_at"])
            if last.tzinfo is None:
                return False
            baseline = last.timestamp()
        else:
            # Legacy rows did not record the actual time of their last nudge.
            baseline = sent.timestamp() + sum(gaps[:count]) * 60
        return now.timestamp() >= baseline + gaps[count] * 60
    except (ValueError, TypeError, KeyError, OverflowError):
        return False
