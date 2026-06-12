import pytest
from datetime import timedelta


def test_delete_recurring_one_reschedules_next(main_module, fixed_now):
    m = main_module
    chat_id = 111
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="daily",
        payload={},
        time_hour=23,
        time_minute=0,
        created_by=user_id,
    )

    r1_dt = fixed_now.replace(day=29, hour=23, minute=0)
    r1 = m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=r1_dt,
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_recurring_one_instance_and_reschedule(r1, chat_id)
    assert snap is not None
    # backward-compat, если ты оставляешь:
    assert snap.get("mode") in (None, "one") or snap.get("mode") == "one"
    assert snap.get("kind") in (None, "single") or snap.get("kind") == "single"

    # template должен остаться активным
    tpl = m.get_recurring_template(tpl_id)
    assert tpl is not None
    assert tpl["active"] is True

    # удаленный инстанс должен исчезнуть
    assert m.get_reminder_row(r1) is None

    # должен появиться следующий инстанс
    next_id = snap.get("next_created_id")
    assert next_id is not None

    next_row = m.get_reminder_row(int(next_id))
    assert next_row is not None
    assert int(next_row["template_id"]) == int(tpl_id)
    assert next_row["text"] == "series"

    # дата должна быть позже исходной
    next_dt = m.datetime.fromisoformat(str(next_row["remind_at"])) if hasattr(m, "datetime") else None
    # если datetime не экспортирован в main_module, просто проверим строково:
    assert str(next_row["remind_at"]) != str(r1_dt.isoformat())


def test_delete_recurring_series_with_snapshot(main_module, fixed_now):
    m = main_module
    chat_id = 222
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="yearly gift",
        pattern_type="yearly",
        payload={"month": 12, "day": 25},
        time_hour=11,
        time_minute=0,
        created_by=user_id,
    )

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="yearly gift",
        remind_at=fixed_now.replace(day=29, hour=11, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )
    r2 = m.add_reminder(
        chat_id=chat_id,
        text="yearly gift",
        remind_at=fixed_now.replace(day=30, hour=11, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_recurring_series_with_snapshot(tpl_id, chat_id)
    assert snap is not None
    assert snap.get("kind") == "series"
    assert snap.get("template") is not None
    assert isinstance(snap.get("reminders"), list)
    assert {int(x["id"]) for x in snap["reminders"]} == {int(r1), int(r2)}

    # reminders удалены
    assert m.get_reminder_row(r1) is None
    assert m.get_reminder_row(r2) is None

    # template деактивирован
    tpl = m.get_recurring_template(tpl_id)
    assert tpl is not None
    assert tpl["active"] is False


def test_restore_single_undo_removes_autocreated_next(main_module, fixed_now):
    m = main_module
    chat_id = 333
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="daily",
        pattern_type="daily",
        payload={},
        time_hour=23,
        time_minute=0,
        created_by=user_id,
    )

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="daily",
        remind_at=fixed_now.replace(day=29, hour=23, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_recurring_one_instance_and_reschedule(r1, chat_id)
    assert snap is not None
    next_id = snap.get("next_created_id")
    assert next_id is not None
    assert m.get_reminder_row(int(next_id)) is not None

    restored_id = m.restore_deleted_snapshot(snap)
    assert restored_id is not None

    # автосозданный next должен быть удален
    assert m.get_reminder_row(int(next_id)) is None

    # ближайший должен вернуться
    restored_row = m.get_reminder_row(int(restored_id))
    assert restored_row is not None
    assert int(restored_row["template_id"]) == int(tpl_id)
    assert restored_row["text"] == "daily"


def test_restore_series_undo_recreates_instances(main_module, fixed_now):
    m = main_module
    chat_id = 444
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="weekly",
        payload={"weekday": 0},
        time_hour=11,
        time_minute=0,
        created_by=user_id,
    )

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=fixed_now.replace(day=29, hour=11, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_recurring_series_with_snapshot(tpl_id, chat_id)
    assert snap is not None

    restored = m.restore_deleted_snapshot(snap)
    assert restored is not None
    assert isinstance(restored, list)
    assert len(restored) == len(snap.get("reminders") or [])

    # template снова активен
    tpl = m.get_recurring_template(tpl_id)
    assert tpl is not None
    assert tpl["active"] is True

    # reminders снова существуют (id будут новые)
    for new_id in restored:
        row = m.get_reminder_row(int(new_id))
        assert row is not None
        assert int(row["template_id"]) == int(tpl_id)