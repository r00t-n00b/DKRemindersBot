import main
from dkreminders_bot.parsing.parser_time_tokens import TIME_TOKEN_RE, VAGUE_TIME_WORDS, _extract_time_from_tokens


def test_time_token_re_accepts_colon_and_dot_time():
    assert TIME_TOKEN_RE.fullmatch("10:30")
    assert TIME_TOKEN_RE.fullmatch("9.05")


def test_time_token_re_rejects_date_like_token():
    assert not TIME_TOKEN_RE.fullmatch("10.3")


def test_extract_time_from_tokens_extracts_valid_time():
    tokens, hour, minute = _extract_time_from_tokens(["tomorrow", "9:05"], 10, 0)

    assert tokens == ["tomorrow"]
    assert (hour, minute) == (9, 5)


def test_extract_time_from_tokens_leaves_invalid_time_like_date():
    tokens, hour, minute = _extract_time_from_tokens(["29.11"], 10, 0)

    assert tokens == ["29.11"]
    assert (hour, minute) == (10, 0)


def test_extract_time_from_tokens_extracts_vague_time_word():
    tokens, hour, minute = _extract_time_from_tokens(["завтра", "утром"], 10, 0)

    assert tokens == ["завтра"]
    assert (hour, minute) == VAGUE_TIME_WORDS["утром"]


def test_main_reexports_time_token_helpers_for_existing_callers():
    assert main.TIME_TOKEN_RE is TIME_TOKEN_RE
    assert main.VAGUE_TIME_WORDS is VAGUE_TIME_WORDS
    assert main._extract_time_from_tokens is _extract_time_from_tokens
