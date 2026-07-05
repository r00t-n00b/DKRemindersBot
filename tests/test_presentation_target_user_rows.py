from dkreminders_bot.ui.presentation import build_target_user_presentation_rows


def test_target_user_presentation_rows_enriches_recurring_template_from_loader():
    rows = [
        {
            "id": 101,
            "text": "пить воду",
            "remind_at": "2026-06-23T10:00:00+02:00",
            "template_id": 5,
        }
    ]

    def loader(template_id):
        assert template_id == 5
        return {"pattern_type": "daily", "payload": {"x": 1}}

    assert build_target_user_presentation_rows(rows, recurring_template_loader=loader) == [
        {
            "id": 101,
            "text": "пить воду",
            "remind_at": "2026-06-23T10:00:00+02:00",
            "template_id": 5,
            "pattern_type": "daily",
            "payload": {"x": 1},
        }
    ]


def test_target_user_presentation_rows_keeps_non_recurring_row():
    rows = [
        {
            "id": 101,
            "text": "купить молоко",
            "remind_at": "2026-06-22T19:30:00+02:00",
            "template_id": None,
        }
    ]

    assert build_target_user_presentation_rows(rows) == rows


def test_target_user_presentation_rows_supports_tuple_rows():
    rows = [
        (101, "купить молоко", "2026-06-22T19:30:00+02:00", None),
    ]

    assert build_target_user_presentation_rows(rows) == [
        {
            "id": 101,
            "text": "купить молоко",
            "remind_at": "2026-06-22T19:30:00+02:00",
            "template_id": None,
        }
    ]
