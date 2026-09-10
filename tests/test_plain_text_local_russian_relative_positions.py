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


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        (
            "напомни в пятницу попросить Панду пойти в офис через неделю",
            "в пятницу - попросить Панду пойти в офис через неделю",
        ),
        (
            "Напомни 9 сентября понять, надо ли переносить уборку через неделю",
            "9 сентября - понять, надо ли переносить уборку через неделю",
        ),
    ],
)
def test_explicit_leading_date_wins_over_trailing_relative_expression(raw_text, expected):
    assert _normalize(raw_text) == expected


def test_plain_text_half_hour_is_normalized_locally():
    assert _normalize(
        "Напомни через полчаса заказать соль"
    ) == "через полчаса - заказать соль"


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        (
            "напомни через 11.20 зачекинить всех на рейс",
            "через 11 часов 20 минут - зачекинить всех на рейс",
        ),
        (
            "напомни через 11:20 зачекинить всех на рейс",
            "через 11 часов 20 минут - зачекинить всех на рейс",
        ),
        (
            "напомни через 11 часов и 20 минут зачекинить всех на рейс",
            "через 11 часов 20 минут - зачекинить всех на рейс",
        ),
        (
            "напомни через 11 часов 20 минут зачекинить всех на рейс",
            "через 11 часов 20 минут - зачекинить всех на рейс",
        ),
    ],
)
def test_plain_text_compound_relative_hours_minutes(raw_text, expected):
    assert _normalize(raw_text) == expected
