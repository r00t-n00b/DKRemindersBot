def test_alias_split(main_module):
    alias, rest = main_module.maybe_split_alias_first_token("football 29.11 10:00 - t")
    assert alias == "football"
    assert rest.startswith("29.11 10:00 - t")


def test_alias_not_split_for_keywords(main_module):
    alias, _ = main_module.maybe_split_alias_first_token("tomorrow 10:00 - t")
    assert alias is None

    alias2, _ = main_module.maybe_split_alias_first_token("day after tomorrow 10:00 - t")
    assert alias2 is None

    alias3, _ = main_module.maybe_split_alias_first_token("every day 10:00 - t")
    assert alias3 is None


def test_alias_db_roundtrip(main_module):
    main_module.set_chat_alias("football", 999, "Football chat")
    assert main_module.get_chat_id_by_alias("football") == 999

def test_maybe_split_alias_does_not_eat_on_and_months(main_module):
    m = main_module

    cases = [
        # on + месяц
        ("on January 25 20:30", None, "on January 25 20:30"),
        ("on 25 January 20:30", None, "on 25 January 20:30"),
        ("on 25.01 11:00", None, "on 25.01 11:00"),

        # просто месяц
        ("January 25 20:30", None, "January 25 20:30"),
        ("December 31", None, "December 31"),

        # alias по-прежнему работает
        ("football 25.01 11:00", "football", "25.01 11:00"),
    ]

    for raw, expected_alias, expected_rest in cases:
        alias, rest = m.maybe_split_alias_first_token(raw)
        assert alias == expected_alias
        assert rest == expected_rest