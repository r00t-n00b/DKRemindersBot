"""Shared parser lexicon for reminder commands.

Keep recurring aliases here so parse_recurring(), /remind routing,
bulk routing and missing-dash validation cannot drift apart.
"""

RECURRING_HOURLY_ALIASES = frozenset({
    "hourly",
    "ежечасно",
})

RECURRING_DAILY_ALIASES = frozenset({
    "everyday",
    "daily",
    "ежедневно",
})

RECURRING_WEEKLY_ALIASES = frozenset({
    "weekly",
    "еженедельно",
})

RECURRING_MONTHLY_ALIASES = frozenset({
    "monthly",
    "ежемесячно",
})

RECURRING_SIMPLE_ALIASES = frozenset().union(
    RECURRING_HOURLY_ALIASES,
    RECURRING_DAILY_ALIASES,
    RECURRING_WEEKLY_ALIASES,
    RECURRING_MONTHLY_ALIASES,
)

RECURRING_FIRST_TOKENS = frozenset({
    "every",
    "yearly",
    "biweekly",
    "fortnightly",
    "weekdays",
    "weekday",
    "workdays",
    "workday",
    "weekends",
    "weekend",
    "каждый",
    "каждую",
    "каждое",
    "каждые",
    "каждого",
}).union(RECURRING_SIMPLE_ALIASES)


def tokens_match_alias(tokens: list[str], aliases) -> bool:
    return len(tokens) == 1 and tokens[0] in aliases


def is_simple_recurring_alias_start(raw: str) -> bool:
    first = (raw or "").strip().lower().split(maxsplit=1)
    return bool(first and first[0] in RECURRING_SIMPLE_ALIASES)


def is_recurring_missing_dash_candidate(raw: str) -> bool:
    first = (raw or "").strip().lower().split(maxsplit=1)
    if not first:
        return False

    token = first[0]
    return token in RECURRING_SIMPLE_ALIASES or token == "every" or token.startswith("кажд")


# Shared date lexicon

WEEKDAY_EN = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

WEEKDAY_RU = {
    "понедельник": 0,
    "понедельника": 0,
    "пн": 0,
    "вторник": 1,
    "вторника": 1,
    "вт": 1,
    "среда": 2,
    "среду": 2,
    "среды": 2,
    "ср": 2,
    "четверг": 3,
    "четверга": 3,
    "чт": 3,
    "пятница": 4,
    "пятницу": 4,
    "пятницы": 4,
    "пт": 4,
    "суббота": 5,
    "субботу": 5,
    "сб": 5,
    "воскресенье": 6,
    "воскресенья": 6,
    "вс": 6,
}

MONTH_EN = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
