import asyncio
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from dkreminders_bot.callbacks.callback_contracts import RECURRENCE_MODE_PATTERN
from dkreminders_bot.domain.recurrence import next_after_completion
from dkreminders_bot.storage.completion_recurrence import RecurrenceStore
from dkreminders_bot.workers.reminders_workers import run_reminders_worker, run_reminders_nudge_worker


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Message:
    def __init__(self, text="", chat_id=456, message_id=100):
        self.text, self.chat_id, self.message_id = text, chat_id, message_id
        self.chat = SimpleNamespace(id=chat_id, type="private" if chat_id > 0 else "supergroup")
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return Message(text, self.chat_id, self.message_id + len(self.replies))


class Bot:
    def __init__(self):
        self.sent, self.deleted = [], []

    async def get_chat(self, chat_id):
        return SimpleNamespace(type="private" if chat_id > 0 else "supergroup")

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=200 + len(self.sent))

    async def delete_message(self, **kwargs):
        self.deleted.append(kwargs)

    async def edit_message_reply_markup(self, **kwargs):
        pass

    async def edit_message_text(self, **kwargs):
        pass


class Query:
    def __init__(self, data, actor=456, chat_id=456):
        self.data = data
        self.from_user = SimpleNamespace(id=actor)
        self.message = Message("размяться", chat_id, 200)
        self.answers, self.edits = [], []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        self.message.text = text

    async def edit_message_reply_markup(self, **kwargs):
        pass


@pytest.fixture
def env(main_module, monkeypatch):
    m = main_module
    clock = {"now": datetime(2026, 6, 12, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))}
    monkeypatch.setattr(m, "get_now", lambda: clock["now"])
    monkeypatch.setattr(m, "InlineKeyboardButton", Button)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", Markup)
    m.set_user_timezone_name(456, "Europe/Madrid")
    bot = Bot()
    return SimpleNamespace(m=m, clock=clock, store=RecurrenceStore(m.DB_PATH),
                           context=SimpleNamespace(bot=bot, user_data={}, args=[]), bot=bot)


def rows(env, table="reminders"):
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]


async def command(env, text="/remind every 30 minutes - размяться", chat_id=456):
    message = Message(text, chat_id)
    update = SimpleNamespace(effective_message=message, message=message, effective_chat=message.chat,
                             effective_user=SimpleNamespace(id=456, username="test", first_name="T", last_name="U"))
    await env.m.remind_command(update, env.context)
    return message


def choice_data(message, mode):
    return next(b.callback_data for row in message.replies[0][1]["reply_markup"].inline_keyboard
                for b in row if b.callback_data.endswith(":" + mode))


async def choose(env, message, mode="completion", actor=456, chat_id=456):
    query = Query(choice_data(message, mode), actor=actor, chat_id=chat_id)
    await env.m.recurrence_mode_callback(SimpleNamespace(callback_query=query), env.context)
    return query


async def click(env, data, actor=456, chat_id=456):
    query = Query(data, actor, chat_id)
    await env.m.snooze_callback(SimpleNamespace(callback_query=query), env.context)
    return query


class StopWorker(Exception):
    pass


async def worker_once(env, worker=run_reminders_worker):
    deps = env.m._build_reminders_worker_deps()

    async def stop(_):
        raise StopWorker

    deps.asyncio = SimpleNamespace(sleep=stop)
    with pytest.raises(StopWorker):
        await worker(SimpleNamespace(bot=env.bot), deps)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["schedule", "completion"])
async def test_choice_before_creation_is_persistent_and_idempotent(env, mode):
    message = await command(env)
    assert not rows(env)
    assert not rows(env, "recurring_templates")
    data = choice_data(message, mode)
    assert len(data.encode()) <= 64
    assert re.fullmatch(RECURRENCE_MODE_PATTERN, data)
    # Simulate restart: pending selection lives in SQLite, not context.user_data.
    env.m.init_db()
    env.context.user_data.clear()
    query = await choose(env, message, mode)
    assert query.edits and "Ок, создал повторяющееся напоминание." in query.edits[0][0]
    tpl = rows(env, "recurring_templates")[0]
    assert json.loads(tpl["payload"])["recurrence_mode"] == mode
    assert len(rows(env)) == 1
    await choose(env, message, "schedule" if mode == "completion" else "completion")
    assert len(rows(env)) == len(rows(env, "recurring_templates")) == 1
    assert "После выполнения" in query.edits[0][0] if mode == "completion" else "После выполнения" not in query.edits[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["/remind every day 09:00 - вода", "/remind каждый понедельник 09:00 - вода"])
async def test_calendar_schedules_do_not_ask_for_mode(env, text):
    message = await command(env, text)
    assert "Ок, создал повторяющееся напоминание." in message.replies[0][0]
    assert len(rows(env)) == 1
    assert not rows(env, "recurrence_choices")


@pytest.mark.asyncio
async def test_completion_delivery_waits_for_done_then_counts_from_actual_completion(env):
    await choose(env, await command(env))
    rid = rows(env)[0]["id"]
    env.clock["now"] += timedelta(minutes=30)
    await worker_once(env)
    assert len(env.bot.sent) == 1 and len(rows(env)) == 1
    env.clock["now"] += timedelta(minutes=21, seconds=37)
    await worker_once(env, run_reminders_nudge_worker)
    assert len(env.bot.sent) == 2 and len(rows(env)) == 1
    # Restart and a later worker pass cannot create the next occurrence.
    env.m.init_db()
    await worker_once(env)
    assert len(rows(env)) == 1
    done = await click(env, f"done:{rid}")
    expected = env.clock["now"] + timedelta(minutes=30)
    assert datetime.fromisoformat(rows(env)[1]["remind_at"]) == expected
    assert rows(env)[0]["acked"] == 1
    assert "Следующее напоминание" in done.edits[0][0]
    await click(env, f"done:{rid}")
    assert len(rows(env)) == 2
    env.clock["now"] = expected
    await worker_once(env)
    assert len(rows(env)) == 2 and len(env.bot.sent) == 3


@pytest.mark.asyncio
async def test_schedule_and_legacy_intervals_continue_on_delivery(env):
    await choose(env, await command(env), "schedule")
    env.clock["now"] += timedelta(minutes=30)
    await worker_once(env)
    assert len(rows(env)) == 2
    rid = rows(env)[0]["id"]
    await click(env, f"done:{rid}")
    assert len(rows(env)) == 2
    # Existing template without a mode remains schedule-based.
    tpl = env.m.create_recurring_template(456, "legacy", "interval", {"value": 1, "unit": "hours"}, 10, 0, 456)
    env.m.add_reminder(456, "legacy", env.clock["now"], 456, tpl)
    await worker_once(env)
    assert len(env.m.get_reminders_by_template_id(tpl, 456)) == 2


@pytest.mark.asyncio
async def test_quick_custom_and_repeated_snooze_keep_series_and_source(env):
    message = await command(env)
    # Put a source in the persisted choice, as provided by reply-context input.
    spec = json.loads(rows(env, "recurrence_choices")[0]["spec"])
    spec.update(source_chat_id=456, source_message_id=77)
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE recurrence_choices SET spec = ?", (json.dumps(spec),))
    await choose(env, message)
    tpl = rows(env)[0]["template_id"]
    for index, action in enumerate(("20m", "custom")):
        r = rows(env)[-1]
        env.clock["now"] = datetime.fromisoformat(r["remind_at"])
        await worker_once(env)
        assert env.bot.sent[-1]["reply_to_message_id"] == 77
        if action == "custom":
            await click(env, f"snooze:{r['id']}:custom")
            assert rows(env)[-1]["acked"] == 0
            target = env.clock["now"] + timedelta(hours=1)
            query = await click(env, f"snooze_picktime:{r['id']}:{target:%Y-%m-%d}:{target:%H:%M}")
        else:
            query = await click(env, f"snooze:{r['id']}:{action}")
        assert query.answers[-1][0].startswith("Отложено до")
        new = rows(env)[-1]
        assert new["id"] != r["id"] and new["template_id"] == tpl
        assert (new["source_chat_id"], new["source_message_id"]) == (456, 77)
        before = len(rows(env))
        await click(env, f"done:{r['id']}")
        await click(env, f"snooze:{r['id']}:20m")
        assert len(rows(env)) == before
    latest = rows(env)[-1]
    env.clock["now"] = datetime.fromisoformat(latest["remind_at"])
    await worker_once(env)
    env.clock["now"] += timedelta(minutes=17)
    await click(env, f"done:{latest['id']}")
    assert datetime.fromisoformat(rows(env)[-1]["remind_at"]) == env.clock["now"] + timedelta(minutes=30)
    assert all(r["template_id"] == tpl for r in rows(env))


@pytest.mark.asyncio
async def test_choice_cancel_expiry_delayed_and_ownership(env):
    message = await command(env)
    for actor, chat in [(999, 456), (456, 999)]:
        query = await choose(env, message, actor=actor, chat_id=chat)
        assert query.answers[-1][1] and not rows(env)
    await choose(env, message, "cancel")
    await choose(env, message)
    assert not rows(env)
    message = await command(env)
    env.clock["now"] += timedelta(days=2)
    expired = await choose(env, message)
    assert "истекло" in expired.answers[-1][0] and not rows(env)
    message = await command(env)
    env.clock["now"] += timedelta(hours=2)
    await choose(env, message)
    assert datetime.fromisoformat(rows(env)[0]["remind_at"]) > env.clock["now"]


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_id,actor", [(456, 999), (-100, 999)])
async def test_completion_actions_reject_wrong_actor(env, chat_id, actor):
    message = await command(env, chat_id=chat_id)
    await choose(env, message, chat_id=chat_id)
    r = rows(env)[0]
    env.m.mark_reminder_sent(r["id"], env.clock["now"])
    for data in (f"done:{r['id']}", f"snooze:{r['id']}:20m", f"snooze:{r['id']}:custom"):
        query = await click(env, data, actor=actor, chat_id=chat_id)
        assert query.answers[-1][1]
        assert len(rows(env)) == 1 and rows(env)[0]["acked"] == 0


@pytest.mark.asyncio
async def test_group_creator_can_complete_and_nudge_remains_private(env):
    await choose(env, await command(env, chat_id=-100), chat_id=-100)
    env.clock["now"] += timedelta(minutes=30)
    await worker_once(env)
    r = rows(env)[0]
    keyboard = env.bot.sent[-1]["reply_markup"].inline_keyboard
    data = [b.callback_data for line in keyboard for b in line]
    assert f"done:{r['id']}" in data
    assert f"selfremind:ask:{r['id']}" in data
    env.clock["now"] += timedelta(minutes=21)
    await worker_once(env, run_reminders_nudge_worker)
    assert len(env.bot.sent) == 1
    await click(env, f"done:{r['id']}", chat_id=-100)
    assert len(rows(env)) == 2


@pytest.mark.asyncio
async def test_inactive_series_does_not_restart_from_old_buttons(env):
    await choose(env, await command(env))
    r = rows(env)[0]
    env.m.mark_reminder_sent(r["id"], env.clock["now"])
    env.m.deactivate_recurring_template(r["template_id"])
    await click(env, f"done:{r['id']}")
    assert len(rows(env)) == 1


@pytest.mark.asyncio
async def test_bulk_intervals_each_require_selection_and_calendar_creates_immediately(env):
    message = await command(env, "/remind\nevery 30 minutes - один\nevery 2 hours - два\nevery day 09:00 - три")
    assert len(rows(env, "recurrence_choices")) == 2
    assert len(rows(env)) == 1
    assert "Ожидают выбора режима: 2" in message.replies[-1][0]


def test_completion_intervals_preserve_seconds_and_elapsed_time_over_dst():
    before = datetime(2026, 10, 25, 2, 45, 13, tzinfo=ZoneInfo("Europe/Madrid"), fold=0)
    after = next_after_completion({"value": 30, "unit": "minutes"}, before, "Europe/Madrid")
    assert after.timestamp() - before.timestamp() == 1800
    assert (after.hour, after.minute, after.second, after.fold) == (2, 15, 13, 1)
    month = next_after_completion({"value": 1, "unit": "months"}, datetime(2026, 1, 31, 12, tzinfo=timezone.utc), "UTC")
    assert (month.month, month.day, month.hour) == (2, 28, 12)


@pytest.mark.asyncio
async def test_concurrent_choice_and_done_only_create_one_successor(env):
    message = await command(env)
    token = choice_data(message, "completion").split(":")[1]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: RecurrenceStore(env.m.DB_PATH).choose(token, "completion", 456, 456, env.clock["now"]), range(8)))
    assert sum(r["status"] == "created" for r in results) == 1
    rid = rows(env)[0]["id"]
    env.m.mark_reminder_sent(rid, env.clock["now"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: RecurrenceStore(env.m.DB_PATH).transition(rid, actor_id=456, chat_id=456, now=env.clock["now"]), range(8)))
    assert sum(r["status"] == "applied" for r in results) == 1
    assert len(rows(env)) == 2


@pytest.mark.asyncio
async def test_failed_next_insert_rolls_back_ack_and_creation(env):
    message = await command(env)
    token = choice_data(message, "completion").split(":")[1]
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON reminders BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        env.store.choose(token, "completion", 456, 456, env.clock["now"])
    assert not rows(env, "recurring_templates") and rows(env, "recurrence_choices")[0]["chosen_mode"] is None
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("DROP TRIGGER fail_insert")
    await choose(env, message)
    rid = rows(env)[0]["id"]
    env.m.mark_reminder_sent(rid, env.clock["now"])
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON reminders BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        env.store.transition(rid, actor_id=456, chat_id=456, now=env.clock["now"])
    assert len(rows(env)) == 1 and rows(env)[0]["acked"] == 0


@pytest.mark.asyncio
async def test_skip_and_undo_leave_exactly_one_occurrence_in_series(env):
    await choose(env, await command(env))
    r = rows(env)[0]
    env.clock["now"] += timedelta(hours=2)
    snapshot = env.m.delete_recurring_one_instance_and_reschedule(r["id"], 456)
    assert snapshot is not None
    assert len(rows(env)) == 1
    assert datetime.fromisoformat(rows(env)[0]["remind_at"]) == env.clock["now"] + timedelta(minutes=30)
    assert rows(env)[0]["template_id"] == r["template_id"]
    restored = env.m.restore_deleted_snapshot(snapshot)
    assert restored is not None and len(rows(env)) == 1
    assert rows(env)[0]["template_id"] == r["template_id"]


@pytest.mark.asyncio
async def test_schema_upgrade_is_idempotent_and_preserves_existing_rows(env):
    tpl = env.m.create_recurring_template(456, "старое", "interval", {"value": 1, "unit": "hours"}, 10, 0, 456)
    env.m.add_reminder(456, "старое", env.clock["now"], 456, tpl)
    before = rows(env), rows(env, "recurring_templates")
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("DROP TABLE recurrence_choices")
    env.m.init_db()
    env.m.init_db()
    assert (rows(env), rows(env, "recurring_templates")) == before
    assert rows(env, "recurrence_choices") == []


@pytest.mark.asyncio
async def test_timezone_migration_then_completion_uses_updated_series_timezone(env):
    await choose(env, await command(env))
    rid = rows(env)[0]["id"]
    env.m.mark_reminder_sent(rid, env.clock["now"])
    env.m.move_active_reminders_timezone_for_user(user_id=456, old_tz="Europe/Madrid", new_tz="Asia/Tokyo", mode="recurring")
    await click(env, f"done:{rid}")
    next_row = rows(env)[-1]
    assert next_row["timezone_name"] == "Asia/Tokyo"
    assert datetime.fromisoformat(next_row["remind_at"]).timestamp() == env.clock["now"].timestamp() + 1800


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "напомни каждые 30 минут размяться", "напоминай каждые полчаса размяться",
    "каждый час размяться", "remind me every 30 minutes stretch",
])
async def test_plain_text_input_reaches_same_mode_chooser(env, text):
    message = Message(text)
    update = SimpleNamespace(effective_message=message, message=message, effective_chat=message.chat,
                             effective_user=SimpleNamespace(id=456, username="test", first_name="T", last_name="U"))
    await env.m.plain_text_remind_command(update, env.context)
    assert "Как повторять?" in message.replies[-1][0]
    assert not rows(env)


def test_mode_callback_is_registered_with_matching_pattern():
    from pathlib import Path
    source = Path("main.py").read_text()
    assert "CallbackQueryHandler(recurrence_mode_callback, pattern=RECURRENCE_MODE_PATTERN)" in source


@pytest.mark.asyncio
async def test_half_hour_command_and_interval_with_explicit_time_keep_schedule(env):
    message = await command(env, "/remind каждые полчаса - размяться")
    assert "30 минут" in message.replies[0][0]
    await choose(env, message, "schedule")
    first = rows(env)[0]
    assert datetime.fromisoformat(first["remind_at"]) == env.clock["now"] + timedelta(minutes=30)
    normalized = env.m._normalize_plain_text_reminder_locally("напоминай каждые 3 дня в 09:00 проверить фильтр")
    parsed = env.m.parse_recurring(normalized, env.clock["now"])
    assert parsed[-2:] == (9, 0)
    assert parsed[1] == "проверить фильтр"


@pytest.mark.asyncio
async def test_invalid_and_past_custom_time_cannot_ack_completion(env):
    await choose(env, await command(env))
    rid = rows(env)[0]["id"]
    env.m.mark_reminder_sent(rid, env.clock["now"])
    for data in (f"snooze_picktime:{rid}:bad-date:bad-time", f"snooze_picktime:{rid}:2020-01-01:09:00"):
        query = await click(env, data)
        assert query.answers[-1][1]
        assert len(rows(env)) == 1 and rows(env)[0]["acked"] == 0


@pytest.mark.asyncio
async def test_completion_transition_across_autumn_clock_change_is_future(env):
    await choose(env, await command(env))
    rid = rows(env)[0]["id"]
    env.m.mark_reminder_sent(rid, env.clock["now"])
    env.clock["now"] = datetime(2026, 10, 25, 2, 45, tzinfo=ZoneInfo("Europe/Madrid"), fold=0)
    result = env.store.transition(rid, actor_id=456, chat_id=456, now=env.clock["now"])
    assert result["status"] == "applied"
    assert result["next_at"].timestamp() - env.clock["now"].timestamp() == 1800


@pytest.mark.asyncio
async def test_worker_delivers_at_correct_instant_after_timezone_migration(env):
    await choose(env, await command(env))
    rid = rows(env)[0]["id"]
    env.m.mark_reminder_sent(rid, env.clock["now"])
    env.m.move_active_reminders_timezone_for_user(user_id=456, old_tz="Europe/Madrid", new_tz="Asia/Tokyo", mode="recurring")
    await click(env, f"done:{rid}")
    env.clock["now"] += timedelta(minutes=29)
    await worker_once(env)
    assert not env.bot.sent
    env.clock["now"] += timedelta(minutes=1)
    await worker_once(env)
    assert len(env.bot.sent) == 1


@pytest.mark.asyncio
async def test_worker_does_not_deliver_early_during_repeated_dst_hour(env):
    await choose(env, await command(env))
    rid = rows(env)[0]["id"]
    env.m.mark_reminder_sent(rid, env.clock["now"])
    env.clock["now"] = datetime(2026, 10, 25, 2, 45, tzinfo=ZoneInfo("Europe/Madrid"), fold=0)
    await click(env, f"done:{rid}")
    # The next local time is 02:15 *after* the clock change, still 30 min away.
    await worker_once(env)
    assert not env.bot.sent
    env.clock["now"] = datetime(2026, 10, 25, 2, 15, tzinfo=ZoneInfo("Europe/Madrid"), fold=1)
    await worker_once(env)
    assert len(env.bot.sent) == 1


@pytest.mark.asyncio
async def test_series_delete_undo_preserves_source_and_does_not_replay_completed_history(env):
    await choose(env, await command(env))
    first = rows(env)[0]
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("UPDATE reminders SET source_chat_id = 456, source_message_id = 77")
    env.m.mark_reminder_sent(first["id"], env.clock["now"])
    await click(env, f"done:{first['id']}")
    snapshot = env.m.delete_recurring_series_with_snapshot(first["template_id"], 456)
    assert not rows(env)
    restored = env.m.restore_deleted_snapshot(snapshot)
    assert len(restored) == 2
    restored_rows = rows(env)
    assert sum(r["acked"] == 0 for r in restored_rows) == 1
    assert sum(r["delivered"] == 0 for r in restored_rows) == 1
    assert all(r["source_message_id"] == 77 for r in restored_rows)
    # Consuming the snapshot twice must not create another open occurrence.
    assert env.m.restore_deleted_snapshot(snapshot) is None
    assert len(rows(env)) == 2
