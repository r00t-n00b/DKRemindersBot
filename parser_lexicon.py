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
