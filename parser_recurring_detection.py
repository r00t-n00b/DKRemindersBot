"""Recurring reminder detection helpers."""

import re

from parser_lexicon import RECURRING_FIRST_TOKENS


def looks_like_recurring(raw: str) -> bool:
    s = raw.strip().lower()
    if not s:
        return False

    first = s.split(maxsplit=1)[0]
    if first in RECURRING_FIRST_TOKENS:
        return True

    if re.search(r"\b(?:число|числа)\s+кажд\w*\s+месяц", s):
        return True

    if re.search(r"\bпо\s+(?:будням|выходным|рабочим)", s):
        return True

    if re.search(r"\bраз\s+в\s+(?:две|2)\s+недел", s):
        return True

    if re.search(r"\bon\s+the\s+\d+(?:st|nd|rd|th)\s+of\s+every\s+month", s):
        return True

    if re.search(r"\bon\s+\d+(?:st|nd|rd|th)\s+of\s+every\s+month", s):
        return True

    if re.search(r"\b\d+(?:st|nd|rd|th)\s+of\s+every\s+month", s):
        return True

    return False
