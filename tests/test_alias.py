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