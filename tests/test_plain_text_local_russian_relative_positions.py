from datetime import datetime

import pytest

from dkreminders_bot.commands.plain_text_local_normalization import (
    normalize_plain_text_reminder_locally,
)
from dkreminders_bot.parsing.parser_date_time_smart import parse_date_time_smart
from dkreminders_bot.parsing.parser_split import _split_expr_and_text
from dkreminders_bot.utils.time_utils import BOT_TZ


def _normalize(raw_text: str):
    return normalize_plain_text_reminder_locally(
        raw_text,
        split_expr_and_text=_split_expr_and_text,
        parse_date_time_smart=parse_date_time_smart,
        get_now=lambda: datetime(2026, 7, 14, 11, 38, tzinfo=BOT_TZ),
    )


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        (
            "Напомни через неделю трансфернуть всех кто ценный",
            "через неделю - трансфернуть всех кто ценный",
        ),
        (
            "напомни добить трейды через час",
            "через час - добить трейды",
        ),
        (
            "напомни в воскресенье подумать, что делать с рейд днем и др маргариты",
            "в воскресенье - подумать, что делать с рейд днем и др маргариты",
        ),
        (
            "напомни воскресенье подумать, что делать с рейд днем и др маргариты",
            "в воскресенье - подумать, что делать с рейд днем и др маргариты",
        ),
        (
            "remind me next Sunday plan raids",
            "next sunday - plan raids",
        ),
    ],
)
def test_plain_text_russian_relative_without_dash_is_local(raw_text, expected):
    assert _normalize(raw_text) == expected
