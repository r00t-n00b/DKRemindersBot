from pathlib import Path

from presentation import (
    format_completed_reminder_text,
    format_deleted_snapshot_text,
    format_restored_series_text,
    format_restored_single_text,
    format_snoozed_answer_text,
    format_snoozed_reminder_text,
)


def test_format_completed_reminder_text():
    assert format_completed_reminder_text("купить молоко") == "купить молоко (завершено ✅)"


def test_format_snoozed_texts():
    assert (
        format_snoozed_reminder_text("купить молоко", "22.06 19:30")
        == "купить молоко\n\n(Отложено до 22.06 19:30)"
    )
    assert format_snoozed_answer_text("22.06 19:30") == "Отложено до 22.06 19:30"


def test_format_deleted_snapshot_text():
    assert (
        format_deleted_snapshot_text("Удалено", "22.06 19:30 - купить молоко")
        == "Удалено: 22.06 19:30 - купить молоко"
    )


def test_format_restored_texts():
    assert (
        format_restored_series_text("таблетка", "  🔁 daily", 3)
        == "Вернул серию: таблетка  🔁 daily (инстансов: 3)"
    )
    assert (
        format_restored_single_text("Вернул", "22.06 19:30 - купить молоко")
        == "Вернул: 22.06 19:30 - купить молоко"
    )


def test_action_result_texts_are_used_from_presentation():
    main_source = Path("main.py").read_text()

    assert "format_completed_reminder_text=format_completed_reminder_text" in main_source
    assert "format_completed_reminder_text(" in Path("reminder_done_flow.py").read_text()
    assert "format_snoozed_reminder_text=format_snoozed_reminder_text" in main_source
    assert "format_snoozed_reminder_text(" in Path("snooze_apply.py").read_text()
    assert "format_snoozed_answer_text=format_snoozed_answer_text" in main_source
    assert "format_snoozed_answer_text(" in Path("snooze_apply.py").read_text()
    assert "format_deleted_snapshot_text=format_deleted_snapshot_text" in main_source
    assert "format_deleted_snapshot_text(" in Path("delete_undo_router.py").read_text()
    assert "format_restored_series_text=format_restored_series_text" in main_source
    assert "format_restored_series_text(" in Path("delete_undo_router.py").read_text()
    assert "format_restored_single_text=format_restored_single_text" in main_source
    assert "format_restored_single_text(" in Path("delete_undo_router.py").read_text()

    assert 'f"{base_text} (завершено ✅)"' not in main_source
    assert 'f"{deleted_label}: {deleted_text}"' not in main_source
    assert 'f"Вернул серию: {series_text}{suffix} (инстансов: {count})"' not in main_source
    assert 'f"{restored_prefix}: {restored_text}"' not in main_source
    assert 'f"{r.text}\\n\\n(Отложено до {when_str})"' not in main_source
    assert 'f"Отложено до {when_str}"' not in main_source
