import sqlite3
from datetime import timedelta

import pytest

from dkreminders_bot.storage.unfinished_reminders import UnfinishedRemindersStore
from test_settings_menu_integration import env, Message, button_data, click, open_menu, update


def add(env, text, *, chat=456, owner=456, delivered=True, acked=False, when=None, template=None):
    rid = env.m.add_reminder(chat, text, when or env.clock["now"], owner, template_id=template)
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE reminders SET delivered=?,acked=? WHERE id=?", (delivered, acked, rid))
    return rid


async def open_unfinished(env, args=()):
    env.context.args = list(args)
    await env.m.unfinished_command(update(Message(env.bot, "/unfinished")), env.context)
    return env.bot.sent[-1]


@pytest.mark.asyncio
async def test_unfinished_default_includes_only_delivered_personal_reminders(env):
    add(env, "Планы", delivered=False, when=env.clock["now"]+timedelta(days=2))
    delivered = add(env, "Уже доставлено", delivered=True)
    incoming = add(env, "Мне от другого", owner=777, delivered=True)
    person = add(env, "Моё для человека", chat=999)
    group = add(env, "Моё для группы", chat=-100)
    add(env, "Выполненное", delivered=True, acked=True)
    add(env, "Чужое в общей группе", owner=777, chat=-100, delivered=True)
    add(env, "Чужое человеку", owner=777, chat=999)
    env.m.set_user_alias("Наташа", 999, 999, "natasha", 456)
    env.m.set_chat_alias("Офис", -100, "Work", 456)

    menu = await open_unfinished(env)
    assert "Ожидают выполнения: 2" in menu.text
    assert all(text in menu.text for text in ["Уже доставлено", "Мне от другого"])
    assert all(text not in menu.text for text in ["Планы", "Выполненное", "Чужое в общей группе", "Чужое человеку", "Моё для человека", "Моё для группы"])
    assert "Наташа" not in menu.text and "Офис" not in menu.text
    rows, _, _, total = UnfinishedRemindersStore(env.m.DB_PATH).page(456)
    assert total == 2
    assert {row["id"] for row in rows} == {delivered, incoming}


@pytest.mark.asyncio
async def test_settings_entry_matches_command_and_back_opens_settings(env):
    add(env, "Проверить")
    menu = await open_menu(env)
    await click(env, menu, "Незавершённые напоминания")
    assert "Проверить" in menu.text and "Страница" not in menu.text
    await click(env, menu, "В настройки")
    assert "Часовой пояс:" in menu.text


@pytest.mark.asyncio
async def test_unfinished_has_no_twenty_row_limit_and_survives_restart(env):
    for i in reversed(range(25)):
        add(env, f"Дело{i:02d}", when=env.clock["now"]+timedelta(minutes=i))
    env.context.user_data["list_ids"] = [123]
    menu = await open_unfinished(env)
    assert "Ожидают выполнения: 25" in menu.text and "Страница 1 из 4" in menu.text
    assert menu.text.index("Дело00") < menu.text.index("Дело07")
    old_next = button_data(menu, "→")
    env.m.init_db()
    env.context.user_data.clear()
    await click(env, menu, data=old_next)
    assert "Страница 2 из 4" in menu.text and "Дело08" in menu.text
    stale = await click(env, menu, data=old_next)
    assert stale.answers[0][1].get("show_alert")
    await click(env, menu, "→")
    await click(env, menu, "→")
    assert "Дело24" in menu.text
    await click(env, menu, "←")
    assert "Страница 3 из 4" in menu.text


@pytest.mark.asyncio
async def test_completed_snoozed_and_deleted_records_disappear_on_refresh(env):
    for i in range(8):
        add(env, f"Дело{i}", delivered=True)
    current = add(env, "Отложить", delivered=True)
    menu = await open_unfinished(env)
    await click(env, menu, "→")
    assert "Страница 2 из 2" in menu.text
    env.m.mark_reminder_acked(current)
    successor = add(env, "После откладывания", delivered=False, when=env.clock["now"]+timedelta(hours=3))
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE reminders SET acked=1 WHERE text='Дело0'")
        conn.execute("DELETE FROM reminders WHERE text='Дело1'")
    await click(env, menu, "Обновить")
    assert "Страница" not in menu.text and "Ожидают выполнения: 6" in menu.text
    assert "После откладывания" not in menu.text and "Отложить" not in menu.text
    rows, _, _, _ = UnfinishedRemindersStore(env.m.DB_PATH).page(456)
    assert successor not in {r["id"] for r in rows}
    env.clock["now"] += timedelta(hours=4)
    await click(env, menu, "Обновить")
    assert "После откладывания" not in menu.text
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE reminders SET delivered=1 WHERE id=?", (successor,))
    await click(env, menu, "Обновить")
    assert "После откладывания" in menu.text and "Ожидают выполнения: 7" in menu.text
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE reminders SET acked=1")
    await click(env, menu, "Обновить")
    assert menu.text == "📥 Незавершённые напоминания\n\nНезавершённых напоминаний нет."
    assert "→" not in [b.text for row in menu.reply_markup.inline_keyboard for b in row]


@pytest.mark.asyncio
async def test_unfinished_keeps_delivered_occurrences_and_legacy_personal_records(env):
    tpl = env.m.create_recurring_template(456, "Вода", "daily", {}, 10, 0, 456)
    first = add(env, "Вода", delivered=True, template=tpl, when=env.clock["now"]-timedelta(days=1))
    second = add(env, "Вода", delivered=True, template=tpl)
    add(env, "Будущий повтор", delivered=False, template=tpl, when=env.clock["now"]+timedelta(days=1))
    legacy = add(env, "Старое личное", owner=None, delivered=True)
    add(env, "Без владельца в чужой группе", chat=-100, owner=None)
    menu = await open_unfinished(env)
    assert "Ожидают выполнения: 3" in menu.text and "🔁" in menu.text
    rows, _, _, _ = UnfinishedRemindersStore(env.m.DB_PATH).page(456)
    assert {r["id"] for r in rows} == {first, second, legacy}
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE recurring_templates SET active=0 WHERE id=?", (tpl,))
    await click(env, menu, "Обновить")
    assert "Ожидают выполнения: 3" in menu.text


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["wrong_actor", "expired", "wrong_message", "new_menu"])
async def test_unfinished_callbacks_require_current_private_session(env, case):
    add(env, "Личное")
    menu = await open_unfinished(env)
    data = button_data(menu, "Обновить")
    actor = 456
    if case == "wrong_actor":
        actor = 777
    elif case == "expired":
        env.clock["now"] += timedelta(days=2)
    elif case == "wrong_message":
        menu.message_id += 1
    else:
        await open_menu(env)
    q = await click(env, menu, data=data, actor=actor)
    assert q.answers[0][1].get("show_alert")


@pytest.mark.asyncio
async def test_unfinished_command_rejects_group_before_reading_database(env, monkeypatch):
    def forbidden(*args):
        pytest.fail("Group request read personal unfinished reminders")
    monkeypatch.setattr(UnfinishedRemindersStore, "page", forbidden)
    await env.m.unfinished_command(update(Message(env.bot, "/unfinished", chat_id=-100)), env.context)
    assert "лич" in env.bot.sent[-1].text


@pytest.mark.asyncio
async def test_unfinished_output_fits_telegram_and_preserves_reminder_records(env):
    env.m.set_user_alias("Я"*160, 999, 999, "natasha", 456)
    for i in range(8):
        rid = add(env, str(i)+"🌻"*500, chat=999, delivered=True)
        with sqlite3.connect(env.m.DB_PATH) as conn:
            conn.execute("UPDATE reminders SET timezone_name='Asia/Tokyo' WHERE id=?", (rid,))
    with sqlite3.connect(env.m.DB_PATH) as conn:
        before = conn.execute("SELECT * FROM reminders ORDER BY id").fetchall()
    menu = await open_unfinished(env, ["Я"*160])
    assert len(menu.text.encode("utf-16-le"))//2 < 4096
    assert "Asia/Tokyo" in menu.text and "17:00" in menu.text
    assert all(len(b.callback_data.encode()) <= 64 for row in menu.reply_markup.inline_keyboard for b in row)
    await click(env, menu, "Обновить")
    with sqlite3.connect(env.m.DB_PATH) as conn:
        assert conn.execute("SELECT * FROM reminders ORDER BY id").fetchall() == before


@pytest.mark.asyncio
async def test_unfinished_read_failure_can_be_retried(env, monkeypatch):
    add(env, "Сохранённое")
    original = UnfinishedRemindersStore.page
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("busy")
    monkeypatch.setattr(UnfinishedRemindersStore, "page", fail)
    menu = await open_unfinished(env)
    assert "Не удалось прочитать" in menu.text
    monkeypatch.setattr(UnfinishedRemindersStore, "page", original)
    await click(env, menu, "Обновить")
    assert "Сохранённое" in menu.text


def test_unfinished_page_orders_offset_dates_by_instant(env):
    from datetime import datetime
    older = add(env, "Раньше", when=datetime.fromisoformat("2026-06-12T09:00:00+01:00"))
    later = add(env, "Позже", when=datetime.fromisoformat("2026-06-12T10:00:00+00:00"))
    rows, _, _, _ = UnfinishedRemindersStore(env.m.DB_PATH).page(456)
    assert [r["id"] for r in rows] == [older, later]


@pytest.mark.asyncio
async def test_numbered_completion_buttons_acknowledge_selected_reminder_and_refresh(env):
    first = add(env, "Первое")
    second = add(env, "Второе")
    menu = await open_unfinished(env)
    first_button = button_data(menu, "✅1")
    assert first_button.endswith(f"u_done:{first}")
    assert button_data(menu, "✅2").endswith(f"u_done:{second}")
    await click(env, menu, "✅2")
    assert "Второе" not in menu.text and "Первое" in menu.text
    assert "Ожидают выполнения: 1" in menu.text
    assert env.m.get_reminder(second).acked == 1
    assert env.m.get_reminder(first).acked == 0
    await click(env, menu, "✅1")
    assert "Незавершённых напоминаний нет" in menu.text
    assert not any("u_done:" in b.callback_data for row in menu.reply_markup.inline_keyboard for b in row)


@pytest.mark.asyncio
async def test_completion_uses_visible_id_after_list_changes_and_clamps_last_page(env):
    ids = [add(env, f"Дело{i}") for i in range(9)]
    menu = await open_unfinished(env)
    await click(env, menu, "→")
    callback = button_data(menu, "✅9")
    add(env, "Более раннее", when=env.clock["now"]-timedelta(days=1))
    await click(env, menu, data=callback)
    assert env.m.get_reminder(ids[-1]).acked == 1
    for rid in ids[:-1]:
        assert env.m.get_reminder(rid).acked == 0
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("DELETE FROM reminders WHERE text='Более раннее'")
    await click(env, menu, "Обновить")
    assert "Страница" not in menu.text


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["wrong_actor", "forged_id", "old_revision", "not_delivered", "acked", "deleted", "retargeted", "expired"])
async def test_completion_rejects_foreign_or_changed_reminder(env, case):
    rid = add(env, "Моя")
    foreign = add(env, "Чужая", owner=777, chat=999)
    menu = await open_unfinished(env)
    data = button_data(menu, "✅1")
    actor = 456
    if case == "wrong_actor":
        actor = 777
    elif case == "forged_id":
        data = data.rsplit(":", 1)[0] + ":" + str(foreign)
    elif case == "old_revision":
        await click(env, menu, "Обновить")
    elif case == "expired":
        env.clock["now"] += timedelta(days=2)
    else:
        with sqlite3.connect(env.m.DB_PATH) as conn:
            if case == "not_delivered":
                conn.execute("UPDATE reminders SET delivered=0 WHERE id=?", (rid,))
            elif case == "acked":
                conn.execute("UPDATE reminders SET acked=1 WHERE id=?", (rid,))
            elif case == "deleted":
                conn.execute("DELETE FROM reminders WHERE id=?", (rid,))
            else:
                conn.execute("UPDATE reminders SET chat_id=999,created_by=777 WHERE id=?", (rid,))
    await click(env, menu, data=data, actor=actor)
    assert env.m.get_reminder(foreign).acked == 0
    remaining = env.m.get_reminder(rid)
    if remaining and case != "acked":
        assert remaining.acked == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("chat,owner", [(456, 777), (999, 456), (-100, 456), (456, None)])
async def test_completion_allows_private_recipient_or_creator(env, chat, owner):
    rid = add(env, "Доступное", chat=chat, owner=owner)
    args = []
    if chat != 456:
        if chat > 0:
            env.m.set_user_alias("Получатель", chat, chat, "recipient", 456)
        else:
            env.m.set_chat_alias("Получатель", chat, "Group", 456)
        args = ["Получатель"]
    menu = await open_unfinished(env, args)
    await click(env, menu, "✅1")
    assert env.m.get_reminder(rid).acked == 1


def completion_series(env, *, active=True):
    tpl = env.m.create_recurring_template(456, "Интервал", "interval", {
        "value": 3, "unit": "hours", "recurrence_mode": "completion",
    }, 10, 0, 456)
    rid = add(env, "Интервал", template=tpl)
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE reminders SET source_chat_id=456,source_message_id=987 WHERE id=?", (rid,))
        conn.execute("UPDATE recurring_templates SET active=? WHERE id=?", (active, tpl))
    return tpl, rid


@pytest.mark.asyncio
async def test_completion_series_counts_from_done_preserves_source_and_ignores_repeat_click(env):
    from datetime import datetime

    tpl, rid = completion_series(env)
    menu = await open_unfinished(env)
    data = button_data(menu, "✅1")
    env.clock["now"] += timedelta(hours=2)
    await click(env, menu, data=data)
    await click(env, menu, data=data)
    with sqlite3.connect(env.m.DB_PATH) as conn:
        rows = conn.execute("SELECT id,acked,remind_at,source_chat_id,source_message_id FROM reminders WHERE template_id=? ORDER BY id", (tpl,)).fetchall()
    assert len(rows) == 2 and rows[0][0] == rid and rows[0][1] == 1
    assert rows[1][1] == 0
    assert datetime.fromisoformat(rows[1][2]) == env.clock["now"]+timedelta(hours=3)
    assert rows[1][3:] == (456, 987)
    assert "Незавершённых напоминаний нет" in menu.text


@pytest.mark.asyncio
async def test_completion_of_inactive_series_acknowledges_without_restarting_it(env):
    tpl, rid = completion_series(env, active=False)
    menu = await open_unfinished(env)
    await click(env, menu, "✅1")
    assert env.m.get_reminder(rid).acked == 1
    with sqlite3.connect(env.m.DB_PATH) as conn:
        assert conn.execute("SELECT count(*) FROM reminders WHERE template_id=?", (tpl,)).fetchone()[0] == 1
        assert conn.execute("SELECT active FROM recurring_templates WHERE id=?", (tpl,)).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_failed_successor_insert_rolls_back_completion_and_button_can_retry(env):
    tpl, rid = completion_series(env)
    menu = await open_unfinished(env)
    data = button_data(menu, "✅1")
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("CREATE TRIGGER fail_inbox_next BEFORE INSERT ON reminders BEGIN SELECT RAISE(ABORT,'fail'); END")
    q = await click(env, menu, data=data)
    assert q.answers[0][1].get("show_alert")
    assert env.m.get_reminder(rid).acked == 0
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("DROP TRIGGER fail_inbox_next")
    await click(env, menu, data=data)
    assert env.m.get_reminder(rid).acked == 1


@pytest.mark.asyncio
async def test_completion_runs_normal_message_cleanup_and_recovers_from_telegram_error(env, monkeypatch):
    rid = add(env, "Завершить")
    cleaned = []
    async def failed_cleanup(bot, reminder_id, **kwargs):
        cleaned.append(reminder_id)
        raise RuntimeError("Telegram temporarily unavailable")
    monkeypatch.setattr(env.m, "clear_reminder_message_keyboards", failed_cleanup)
    menu = await open_unfinished(env)
    await click(env, menu, "✅1")
    assert cleaned == [rid]
    assert env.m.get_reminder(rid).acked == 1
    assert "Незавершённых напоминаний нет" in menu.text


def test_concurrent_completion_has_one_successor(env):
    from concurrent.futures import ThreadPoolExecutor
    from dkreminders_bot.storage.completion_recurrence import RecurrenceStore

    tpl, rid = completion_series(env)
    def complete(_):
        return RecurrenceStore(env.m.DB_PATH).transition(
            rid, actor_id=456, chat_id=456, now=env.clock["now"], from_inbox=True,
        )["status"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(complete, range(2)))
    assert sorted(results) == ["applied", "processed"]
    with sqlite3.connect(env.m.DB_PATH) as conn:
        assert conn.execute("SELECT count(*) FROM reminders WHERE template_id=? AND acked=0", (tpl,)).fetchone()[0] == 1


@pytest.mark.asyncio
async def test_completion_callback_fits_telegram_for_64_bit_reminder_id(env):
    rid = add(env, "Большой ID")
    large_id = 2**63-2
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE reminders SET id=? WHERE id=?", (large_id, rid))
    menu = await open_unfinished(env)
    data = button_data(menu, "✅1")
    assert len(data.encode()) <= 64
    await click(env, menu, data=data)
    assert env.m.get_reminder(large_id).acked == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("completion_based", [False, True])
async def test_completion_keeps_existing_next_occurrence_without_creating_duplicate(env, completion_based):
    if completion_based:
        tpl, rid = completion_series(env)
    else:
        tpl = env.m.create_recurring_template(456, "Серия", "daily", {}, 10, 0, 456)
        rid = add(env, "Серия", template=tpl)
    next_id = add(env, "Следующее", delivered=False, template=tpl, when=env.clock["now"]+timedelta(days=1))
    menu = await open_unfinished(env)
    await click(env, menu, "✅1")
    assert env.m.get_reminder(rid).acked == 1
    assert env.m.get_reminder(next_id).acked == 0
    with sqlite3.connect(env.m.DB_PATH) as conn:
        assert conn.execute("SELECT count(*) FROM reminders WHERE template_id=?", (tpl,)).fetchone()[0] == 2


@pytest.mark.asyncio
async def test_creator_can_finish_completion_series_for_another_private_recipient(env):
    tpl, rid = completion_series(env)
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE recurring_templates SET chat_id=999 WHERE id=?", (tpl,))
        conn.execute("UPDATE reminders SET chat_id=999 WHERE id=?", (rid,))
    env.m.set_user_alias("Друг", 999, 999, "friend", 456)
    menu = await open_unfinished(env, ["Друг"])
    await click(env, menu, "✅1")
    with sqlite3.connect(env.m.DB_PATH) as conn:
        rows = conn.execute("SELECT chat_id,acked FROM reminders WHERE template_id=? ORDER BY id", (tpl,)).fetchall()
    assert rows == [(999, 1), (999, 0)]


@pytest.mark.asyncio
async def test_completion_removes_buttons_from_tracked_delivery_and_nudge(env, monkeypatch):
    rid = add(env, "Закрыть с уведомлениями")
    with sqlite3.connect(env.m.DB_PATH) as conn:
        for mid, kind in [(777, "delivery"), (778, "nudge")]:
            conn.execute(
                "INSERT INTO reminder_messages(reminder_id,chat_id,message_id,kind,created_at) VALUES(?,?,?,?,?)",
                (rid, 456, mid, kind, env.clock["now"].isoformat()),
            )
    edited = []
    async def edit_markup(**kwargs):
        edited.append(kwargs)
    monkeypatch.setattr(env.bot, "edit_message_reply_markup", edit_markup)
    menu = await open_unfinished(env)
    await click(env, menu, "✅1")
    assert {item["message_id"] for item in edited} == {777, 778}
    assert all(item["reply_markup"] is None for item in edited)
    assert env.m.get_reminder(rid).acked == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["user", "chat"])
async def test_unfinished_alias_scope_shows_only_creator_records_for_recipient(env, kind):
    chat = 999 if kind == "user" else -100
    if kind == "user":
        env.m.set_user_alias("Получатель", chat, chat, "recipient", 456)
        env.m.set_user_alias("Получатель", 888, 888, "other", 777)
    else:
        env.m.set_chat_alias("Получатель", chat, "Group", 456)
        env.m.set_chat_alias("Получатель", -200, "Other", 777)
    wanted = add(env, "Внешнее моё", chat=chat)
    add(env, "Внешнее чужое", chat=chat, owner=777)
    add(env, "Внешнее будущее", chat=chat, delivered=False)
    add(env, "Внешнее выполненное", chat=chat, acked=True)
    add(env, "Личное")
    menu = await open_unfinished(env, ["пОлУчАтЕлЬ"])
    assert "Внешнее моё" in menu.text and "Незавершённые · Получатель" in menu.text
    assert all(text not in menu.text for text in ["Внешнее чужое", "Внешнее будущее", "Внешнее выполненное", "Личное"])
    await click(env, menu, "✅1")
    assert env.m.get_reminder(wanted).acked == 1


@pytest.mark.asyncio
async def test_alias_page_scope_survives_refresh_restart_and_back_to_personal_list(env):
    env.m.set_chat_alias("Работа", -100, "Work", 456)
    for i in range(10):
        add(env, f"Внешнее{i:02d}", chat=-100)
    add(env, "Мой личный")
    menu = await open_unfinished(env, ["Работа"])
    await click(env, menu, "→")
    assert "Внешнее08" in menu.text and "Мой личный" not in menu.text
    env.context.user_data.clear()
    env.m.init_db()
    await click(env, menu, "Обновить")
    assert "Незавершённые · Работа" in menu.text and "Внешнее08" in menu.text
    await click(env, menu, "В настройки")
    await click(env, menu, "Незавершённые напоминания")
    assert "Мой личный" in menu.text and "Внешнее" not in menu.text


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["renamed", "deleted", "retargeted"])
async def test_alias_changes_block_completion_and_invalidate_visible_list(env, case):
    env.m.set_chat_alias("Работа", -100, "Work", 456)
    rid = add(env, "Старый адресат", chat=-100)
    add(env, "Новый адресат", chat=-200)
    menu = await open_unfinished(env, ["Работа"])
    data = button_data(menu, "✅1")
    with sqlite3.connect(env.m.DB_PATH) as conn:
        if case == "renamed":
            conn.execute("UPDATE chat_aliases SET alias='Офис' WHERE created_by=456")
        elif case == "deleted":
            conn.execute("DELETE FROM chat_aliases WHERE created_by=456")
        else:
            conn.execute("UPDATE chat_aliases SET chat_id=-200 WHERE created_by=456")
    result = await click(env, menu, data=data)
    assert result.answers[0][1].get("show_alert")
    assert env.m.get_reminder(rid).acked == 0
    await click(env, menu, "Обновить")
    assert "Алиас изменён или удалён" in menu.text
    assert "Новый адресат" not in menu.text
    assert not any("u_done:" in b.callback_data for row in menu.reply_markup.inline_keyboard for b in row)


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["Неизвестный", "Чужой"])
async def test_unknown_or_foreign_alias_does_not_open_personal_fallback(env, alias):
    env.m.set_chat_alias("Чужой", -100, "Group", 777)
    add(env, "Мой личный")
    menu = await open_unfinished(env, [alias])
    assert "Алиас не найден" in menu.text and "Мой личный" not in menu.text


@pytest.mark.asyncio
async def test_legacy_multiword_alias_and_duplicate_name_follow_user_alias_priority(env):
    env.m.set_user_alias("Старое имя", 999, 999, "recipient", 456)
    env.m.set_chat_alias("Старое имя", -100, "Group", 456)
    add(env, "Человек", chat=999)
    add(env, "Группа", chat=-100)
    menu = await open_unfinished(env, ["Старое", "имя"])
    assert "Человек" in menu.text and "Группа" not in menu.text


@pytest.mark.asyncio
async def test_old_broad_session_cannot_complete_external_record_in_personal_mode(env):
    own = add(env, "Личное")
    external = add(env, "Внешнее", chat=999)
    menu = await open_unfinished(env)
    session = env.store.session(456, env.clock["now"])
    session["data"]["unfinished_ids"].append(external)
    env.store.save(session)
    data = button_data(menu, "✅1").rsplit(":", 1)[0] + ":" + str(external)
    result = await click(env, menu, data=data)
    assert result.answers[0][1].get("show_alert")
    assert env.m.get_reminder(external).acked == 0
    assert env.m.get_reminder(own).acked == 0
