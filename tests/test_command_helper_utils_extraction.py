import dkreminders_bot.utils.command_helper_utils as command_helper_utils


TARGETS = [
    "parse_renamealias_args",
    "_rest_starts_like_datetime",
    "_strip_leading_token_in_group",
    "_format_bulk_result",
]


def test_command_helper_utils_wrappers_in_main_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    for name in TARGETS:
        matches = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]

        assert len(matches) == 1

        node = matches[0]
        node_source = ast.get_source_segment(source, node)

        assert f"{name}_impl(" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_command_helper_utils_module_contains_impls_and_no_main_import():
    source = open("dkreminders_bot/utils/command_helper_utils.py").read()

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_parse_renamealias_args_arrow_and_space_forms():
    assert command_helper_utils.parse_renamealias_args_impl(["old", "->", "new"]) == ("old", "new")
    assert command_helper_utils.parse_renamealias_args_impl(["old", "->", "new", "alias"]) == ("old", "new alias")
    assert command_helper_utils.parse_renamealias_args_impl(["old", "new", "alias"]) == ("old", "new alias")

    assert command_helper_utils.parse_renamealias_args_impl([]) == (None, None)
    assert command_helper_utils.parse_renamealias_args_impl(["old"]) == (None, None)
    assert command_helper_utils.parse_renamealias_args_impl(["old", "->"]) == (None, None)
    assert command_helper_utils.parse_renamealias_args_impl(["->", "new"]) == (None, None)


def test_rest_starts_like_datetime_recognizes_supported_prefixes():
    positives = [
        "02.02 hello",
        "02/02 hello",
        "02-02 hello",
        "23:40 hello",
        "23.40 hello",
        "today 10:00 hello",
        "tomorrow hello",
        "day after tomorrow hello",
        "сегодня 10",
        "завтра 10",
        "послезавтра 10",
        "in 2 hours",
        "через 2 часа",
    ]

    for value in positives:
        assert command_helper_utils._rest_starts_like_datetime_impl(value) is True

    negatives = [
        "",
        "football tomorrow",
        "natasha hello",
        "abc 02.02",
    ]

    for value in negatives:
        assert command_helper_utils._rest_starts_like_datetime_impl(value) is False


def test_strip_leading_token_in_group_only_for_datetime_rest():
    assert command_helper_utils._strip_leading_token_in_group_impl("team 02.02 hello") == ("02.02 hello", True)
    assert command_helper_utils._strip_leading_token_in_group_impl("@user tomorrow hello") == ("tomorrow hello", True)

    assert command_helper_utils._strip_leading_token_in_group_impl("team hello") == ("team hello", False)
    assert command_helper_utils._strip_leading_token_in_group_impl("oneword") == ("oneword", False)
    assert command_helper_utils._strip_leading_token_in_group_impl("team 02.02 hello\nsecond") == ("team 02.02 hello\nsecond", False)


def test_format_bulk_result_success_and_errors():
    assert command_helper_utils._format_bulk_result_impl(
        created=3,
        failed=0,
        error_lines=[],
    ) == "Готово. Создано напоминаний: 3."

    text = command_helper_utils._format_bulk_result_impl(
        created=2,
        failed=6,
        error_lines=[
            (1, "bad1", "err1"),
            (2, "bad2", "err2"),
            (3, "bad3", "err3"),
            (4, "bad4", "err4"),
            (5, "bad5", "err5"),
            (6, "bad6", "err6"),
        ],
    )

    assert "Готово. Создано напоминаний: 2." in text
    assert "Не удалось разобрать строк: 6." in text
    assert "Проблемные строки (до 5):" in text
    assert "1) 'bad1': err1" in text
    assert "5) 'bad5': err5" in text
    assert "6) 'bad6': err6" not in text
