from datetime import timedelta


def _fetch_reminder_row(main_module, reminder_id):
    conn = main_module.sqlite3.connect(main_module.DB_PATH)
    conn.row_factory = main_module.sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
                id,
                delivered,
                delivery_state,
                processing_started_at,
                delivery_attempts,
                last_error,
                next_retry_at,
                sent_at,
                acked
            FROM reminders
            WHERE id = ?
            """,
            (reminder_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def test_claim_due_reminders_claims_pending_due_rows_once(main_module):
    now = main_module.get_now()

    due_id = main_module.add_reminder(
        chat_id=100,
        text="due reminder",
        remind_at=now - timedelta(minutes=1),
        created_by=1,
    )
    future_id = main_module.add_reminder(
        chat_id=100,
        text="future reminder",
        remind_at=now + timedelta(hours=1),
        created_by=1,
    )

    claimed = main_module.claim_due_reminders(now)

    assert [r.id for r in claimed] == [due_id]

    due_row = _fetch_reminder_row(main_module, due_id)
    future_row = _fetch_reminder_row(main_module, future_id)

    assert due_row["delivered"] == 0
    assert due_row["delivery_state"] == "processing"
    assert due_row["processing_started_at"] == now.isoformat()
    assert due_row["delivery_attempts"] == 1

    assert future_row["delivery_state"] == "pending"
    assert future_row["delivery_attempts"] == 0

    assert main_module.claim_due_reminders(now) == []


def test_claim_due_reminders_respects_limit(main_module):
    now = main_module.get_now()

    first_id = main_module.add_reminder(100, "first", now - timedelta(minutes=2), 1)
    second_id = main_module.add_reminder(100, "second", now - timedelta(minutes=1), 1)

    first_claim = main_module.claim_due_reminders(now, limit=1)
    second_claim = main_module.claim_due_reminders(now, limit=1)

    assert [r.id for r in first_claim] == [first_id]
    assert [r.id for r in second_claim] == [second_id]


def test_mark_reminder_sent_sets_delivery_state_sent(main_module):
    now = main_module.get_now()
    reminder_id = main_module.add_reminder(100, "send me", now - timedelta(minutes=1), 1)

    claimed = main_module.claim_due_reminders(now)
    assert [r.id for r in claimed] == [reminder_id]

    sent_at = now + timedelta(seconds=5)
    main_module.mark_reminder_sent(reminder_id, sent_at=sent_at)

    row = _fetch_reminder_row(main_module, reminder_id)

    assert row["delivered"] == 1
    assert row["delivery_state"] == "sent"
    assert row["processing_started_at"] is None
    assert row["last_error"] is None
    assert row["next_retry_at"] is None
    assert row["sent_at"] == sent_at.isoformat()
    assert row["acked"] == 0


def test_mark_reminder_delivery_failed_returns_to_pending_with_retry(main_module):
    now = main_module.get_now()
    reminder_id = main_module.add_reminder(100, "retry me", now - timedelta(minutes=1), 1)

    claimed = main_module.claim_due_reminders(now)
    assert [r.id for r in claimed] == [reminder_id]

    main_module.mark_reminder_delivery_failed(
        reminder_id,
        "telegram unavailable",
        failed_at=now,
        retry_after_seconds=120,
    )

    row = _fetch_reminder_row(main_module, reminder_id)

    assert row["delivered"] == 0
    assert row["delivery_state"] == "pending"
    assert row["processing_started_at"] is None
    assert row["last_error"] == "telegram unavailable"
    assert row["next_retry_at"] == (now + timedelta(seconds=120)).isoformat()

    assert main_module.claim_due_reminders(now) == []

    retry_claim = main_module.claim_due_reminders(now + timedelta(seconds=121))
    assert [r.id for r in retry_claim] == [reminder_id]


def test_reset_stale_processing_reminders_returns_old_processing_to_pending(main_module):
    now = main_module.get_now()
    reminder_id = main_module.add_reminder(100, "stale processing", now - timedelta(minutes=1), 1)

    claimed = main_module.claim_due_reminders(now)
    assert [r.id for r in claimed] == [reminder_id]

    changed = main_module.reset_stale_processing_reminders(
        now + timedelta(minutes=11),
        stale_after_seconds=600,
    )

    assert changed == 1

    row = _fetch_reminder_row(main_module, reminder_id)

    assert row["delivery_state"] == "pending"
    assert row["processing_started_at"] is None
    assert row["last_error"] == "Reset stale processing reminder"
    assert row["next_retry_at"] == (now + timedelta(minutes=11)).isoformat()
