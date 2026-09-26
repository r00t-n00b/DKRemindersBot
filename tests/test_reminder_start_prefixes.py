from dkreminders_bot.utils.command_text import (
    first_token_looks_like_reminder_start,
    maybe_split_alias_first_token,
)


def test_na_is_valid_reminder_start_prefix():
    assert first_token_looks_like_reminder_start("на") is True


def test_na_sleduyushchey_nedele_is_not_treated_as_alias():
    alias, args = maybe_split_alias_first_token(
        "на следующей неделе забрать коляску"
    )

    assert alias is None
    assert args == "на следующей неделе забрать коляску"


def test_weekdays_are_reminder_starts_not_aliases():
    from dkreminders_bot.utils.command_text import (
        first_token_looks_like_reminder_start,
        maybe_split_alias_first_token,
    )

    for weekday in (
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ):
        assert first_token_looks_like_reminder_start(weekday)

        alias, args = maybe_split_alias_first_token(
            f"{weekday} 11:00 - написать в Меркадо"
        )

        assert alias is None
        assert args == f"{weekday} 11:00 - написать в Меркадо"


def test_weekday_with_preposition_is_not_alias():
    from dkreminders_bot.utils.command_text import maybe_split_alias_first_token

    alias, args = maybe_split_alias_first_token(
        "в понедельник 11:00 - написать в Меркадо"
    )

    assert alias is None
    assert args == "в понедельник 11:00 - написать в Меркадо"


def test_real_alias_still_splits_from_reminder():
    from dkreminders_bot.utils.command_text import maybe_split_alias_first_token

    alias, args = maybe_split_alias_first_token(
        "наташа понедельник 11:00 - написать в Меркадо"
    )

    assert alias == "наташа"
    assert args == "понедельник 11:00 - написать в Меркадо"


def test_weekdays_are_reminder_starts_not_aliases():
    from dkreminders_bot.utils.command_text import (
        first_token_looks_like_reminder_start,
        maybe_split_alias_first_token,
    )

    for weekday in (
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ):
        assert first_token_looks_like_reminder_start(weekday)

        alias, args = maybe_split_alias_first_token(
            f"{weekday} 11:00 - написать в Меркадо"
        )

        assert alias is None
        assert args == f"{weekday} 11:00 - написать в Меркадо"


def test_weekday_with_preposition_is_not_alias():
    from dkreminders_bot.utils.command_text import maybe_split_alias_first_token

    alias, args = maybe_split_alias_first_token(
        "в понедельник 11:00 - написать в Меркадо"
    )

    assert alias is None
    assert args == "в понедельник 11:00 - написать в Меркадо"


def test_real_alias_still_splits_from_reminder():
    from dkreminders_bot.utils.command_text import maybe_split_alias_first_token

    alias, args = maybe_split_alias_first_token(
        "наташа понедельник 11:00 - написать в Меркадо"
    )

    assert alias == "наташа"
    assert args == "понедельник 11:00 - написать в Меркадо"
