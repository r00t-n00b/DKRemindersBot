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


async def open_unfinished(env):
    await env.m.unfinished_command(update(Message(env.bot, "/unfinished")), env.context)
    return env.bot.sent[-1]


@pytest.mark.asyncio
async def test_unfinished_includes_only_delivered_incoming_and_authored(env):
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
    assert "Ожидают выполнения: 4" in menu.text
    assert all(text in menu.text for text in ["Уже доставлено", "Мне от другого", "Моё для человека", "Моё для группы"])
    assert all(text not in menu.text for text in ["Планы", "Выполненное", "Чужое в общей группе", "Чужое человеку"])
    assert "Наташа" in menu.text and "Офис" in menu.text and "Мне" in menu.text
    rows, _, _, total = UnfinishedRemindersStore(env.m.DB_PATH).page(456)
    assert total == 4
    assert {row["id"] for row in rows} == {delivered, incoming, person, group}


@pytest.mark.asyncio
async def test_settings_entry_matches_command_and_back_opens_settings(env):
    add(env, "Проверить")
    menu = await open_menu(env)
    await click(env, menu, "Незавершённые напоминания")
    assert "Проверить" in menu.text and "Страница 1 из 1" in menu.text
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
    assert "Страница 1 из 1" in menu.text and "Ожидают выполнения: 6" in menu.text
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
    assert "Ожидают выполнения: 0" in menu.text and "Незавершённых пока нет" in menu.text
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
    menu = await open_unfinished(env)
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
    def fail(*args):
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
