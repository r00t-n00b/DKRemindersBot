import callback_contracts as c


def test_delete_callback_builders():
    assert c.cb_del(7) == "del:7"
    assert c.cb_del_one(7) == "del_one:7"
    assert c.cb_del_series(9) == "del_series:9"
    assert c.cb_del_cancel(7) == "del_cancel:7"


def test_created_callback_builders():
    assert c.cb_created_complete(7) == "created_complete:7"
    assert c.cb_created_delete(7) == "created_delete:7"
    assert c.cb_created_snooze(7, "1h") == "created_snooze:7:1h"
    assert c.cb_created_snooze_custom(7) == "created_snooze_custom:7"
    assert c.cb_created_snooze_cal(7, 2026, 6) == "created_snooze_cal:7:2026-06"
    assert c.cb_created_snooze_caltoday(7) == "created_snooze_caltoday:7"
    assert c.cb_created_snooze_pastdate(7, "2026-06-23") == "created_snooze_pastdate:7:2026-06-23"
    assert c.cb_created_snooze_pickdate(7, "2026-06-23") == "created_snooze_pickdate:7:2026-06-23"
    assert c.cb_created_snooze_picktime(7, "2026-06-23", "10:00") == "created_snooze_picktime:7:2026-06-23:10:00"
    assert c.cb_created_snooze_cancel(7) == "created_snooze_cancel:7"


def test_snooze_and_selfremind_callback_builders():
    assert c.cb_snooze(7, "20m") == "snooze:7:20m"
    assert c.cb_snooze_custom(7) == "snooze_custom:7"

    assert c.cb_selfremind_ask(7) == "selfremind:ask:7"
    assert c.cb_selfremind_back(7) == "selfremind:back:7"
    assert c.cb_selfremind_cancel_personal(7) == "selfremind:cancel_personal:7"
    assert c.cb_selfremind_set(7, "1h") == "selfremind:set:7:1h"
    assert c.cb_selfremind_mode(7, "event") == "selfremind:mode:7:event"
    assert c.cb_selfremind_event_before(7, "10h") == "selfremind:event_before:7:10h"
    assert c.cb_selfremind_event_custom(7) == "selfremind:event_custom:7"
