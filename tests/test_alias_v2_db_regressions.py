import pytest


def test_chat_alias_lookup_is_case_insensitive_and_owner_scoped(main_module):
    main_module.set_chat_alias("TeamA", 777, "My Group", created_by=1)

    assert main_module.get_chat_id_by_alias("TeamA", created_by=1) == 777
    assert main_module.get_chat_id_by_alias("teama", created_by=1) == 777
    assert main_module.get_chat_id_by_alias("TEAMA", created_by=1) == 777

    assert main_module.get_chat_id_by_alias("TeamA", created_by=2) is None


def test_chat_alias_case_insensitive_update_does_not_duplicate(main_module):
    main_module.set_chat_alias("TeamA", 777, "Old title", created_by=1)
    main_module.set_chat_alias("teama", 888, "New title", created_by=1)

    rows = main_module.get_all_aliases(created_by=1)

    assert len(rows) == 1
    assert main_module.get_chat_id_by_alias("TEAMA", created_by=1) == 888


def test_user_alias_lookup_is_case_insensitive_and_owner_scoped(main_module):
    main_module.set_user_alias(
        alias="Natasha",
        user_id=42,
        chat_id=4242,
        username="natasha",
        created_by=1,
    )

    row = main_module.get_user_alias("natasha", created_by=1)

    assert row is not None
    assert row["alias"] == "Natasha"
    assert row["user_id"] == 42
    assert row["chat_id"] == 4242
    assert row["username"] == "natasha"

    assert main_module.get_user_alias_chat_id("NATASHA", created_by=1) == 4242
    assert main_module.get_user_alias("Natasha", created_by=2) is None
    assert main_module.get_user_alias_chat_id("Natasha", created_by=2) is None


def test_user_alias_case_insensitive_update_does_not_duplicate(main_module):
    main_module.set_user_alias(
        alias="Natasha",
        user_id=42,
        chat_id=4242,
        username="old",
        created_by=1,
    )
    main_module.set_user_alias(
        alias="natasha",
        user_id=43,
        chat_id=4343,
        username="new",
        created_by=1,
    )

    rows = main_module.get_all_user_aliases(created_by=1)

    assert len(rows) == 1
    assert main_module.get_user_alias_chat_id("NATASHA", created_by=1) == 4343

    row = main_module.get_user_alias("natasha", created_by=1)
    assert row["user_id"] == 43
    assert row["username"] == "new"


def test_delete_aliases_are_case_insensitive_and_owner_scoped(main_module):
    main_module.set_chat_alias("TeamA", 777, "My Group", created_by=1)
    main_module.set_user_alias("Natasha", 42, 4242, "natasha", created_by=1)

    assert main_module.delete_chat_alias("teama", created_by=2) is False
    assert main_module.delete_user_alias("natasha", created_by=2) is False

    assert main_module.get_chat_id_by_alias("TeamA", created_by=1) == 777
    assert main_module.get_user_alias_chat_id("Natasha", created_by=1) == 4242

    assert main_module.delete_chat_alias("teama", created_by=1) is True
    assert main_module.delete_user_alias("natasha", created_by=1) is True

    assert main_module.get_chat_id_by_alias("TeamA", created_by=1) is None
    assert main_module.get_user_alias_chat_id("Natasha", created_by=1) is None


def test_rename_aliases_are_case_insensitive_and_owner_scoped(main_module):
    main_module.set_chat_alias("TeamA", 777, "My Group", created_by=1)
    main_module.set_user_alias("Natasha", 42, 4242, "natasha", created_by=1)

    assert main_module.rename_chat_alias("teama", "Football", created_by=2) is False
    assert main_module.rename_user_alias("natasha", "Nata", created_by=2) is False

    assert main_module.rename_chat_alias("teama", "Football", created_by=1) is True
    assert main_module.rename_user_alias("natasha", "Nata", created_by=1) is True

    assert main_module.get_chat_id_by_alias("TeamA", created_by=1) is None
    assert main_module.get_chat_id_by_alias("football", created_by=1) == 777

    assert main_module.get_user_alias_chat_id("Natasha", created_by=1) is None
    assert main_module.get_user_alias_chat_id("nata", created_by=1) == 4242


def test_rename_alias_conflict_is_case_insensitive_per_owner(main_module):
    main_module.set_chat_alias("TeamA", 777, "My Group", created_by=1)
    main_module.set_chat_alias("Football", 888, "Football Group", created_by=1)

    main_module.set_user_alias("Natasha", 42, 4242, "natasha", created_by=1)
    main_module.set_user_alias("Nata", 43, 4343, "nata", created_by=1)

    with pytest.raises(ValueError):
        main_module.rename_chat_alias("teama", "football", created_by=1)

    with pytest.raises(ValueError):
        main_module.rename_user_alias("natasha", "nata", created_by=1)

    assert main_module.get_chat_id_by_alias("TeamA", created_by=1) == 777
    assert main_module.get_user_alias_chat_id("Natasha", created_by=1) == 4242
