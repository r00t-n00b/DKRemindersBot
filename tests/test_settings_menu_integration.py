import json
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from dkreminders_bot.domain.nudge_policy import DEFAULT_GAPS, parse_interval, validate_gaps
from dkreminders_bot.settings.timezone_search import search_timezones
from dkreminders_bot.storage.settings_store import SettingsStore


class Message:
    def __init__(self, bot, text='', chat_id=456, message_id=None, markup=None, reply_to=None):
        self.bot, self.text = bot, text
        self.chat_id = chat_id
        self.chat = SimpleNamespace(id=chat_id, type='private' if chat_id > 0 else 'supergroup')
        self.message_id = message_id or bot.next_id()
        self.reply_markup = markup
        self.reply_to_message = reply_to

    async def reply_text(self, text, **kwargs):
        m = Message(self.bot, text, self.chat_id, markup=kwargs.get('reply_markup'))
        self.bot.sent.append(m)
        return m


class Bot:
    def __init__(self):
        self.sent = []
        self.counter = 100

    def next_id(self):
        self.counter += 1
        return self.counter

    async def get_chat(self, chat_id):
        return SimpleNamespace(type='private' if chat_id > 0 else 'supergroup')

    async def send_message(self, **kwargs):
        m = Message(self, kwargs['text'], kwargs['chat_id'], markup=kwargs.get('reply_markup'))
        m.send_kwargs = kwargs
        self.sent.append(m)
        return m

    async def delete_message(self, **kwargs):
        pass

    async def edit_message_reply_markup(self, **kwargs):
        pass

    async def edit_message_text(self, *, chat_id, message_id, text, reply_markup=None):
        m = next(m for m in self.sent if m.chat_id == chat_id and m.message_id == message_id)
        m.text, m.reply_markup = text, reply_markup


class Query:
    def __init__(self, message, data, actor=456):
        self.message, self.data = message, data
        self.from_user = SimpleNamespace(id=actor)
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.message.text, self.message.reply_markup = text, kwargs.get('reply_markup')

    async def edit_message_reply_markup(self, reply_markup=None):
        self.message.reply_markup = reply_markup



def update(message, user_id=456, query=None):
    user = SimpleNamespace(id=user_id, username='u', first_name='U', last_name='L')
    return SimpleNamespace(effective_message=message, effective_chat=message.chat, effective_user=user, message=message, callback_query=query)


@pytest.fixture
def env(main_module, monkeypatch):
    clock = {'now': datetime(2026, 6, 12, 10, 0, tzinfo=ZoneInfo('Europe/Madrid'))}
    monkeypatch.setattr(main_module, 'get_now', lambda: clock['now'])
    main_module.set_user_timezone_name(456, 'Europe/Madrid')
    bot = Bot()
    return SimpleNamespace(m=main_module, clock=clock, store=SettingsStore(main_module.DB_PATH), bot=bot, context=SimpleNamespace(bot=bot, user_data={}, args=[]))


async def open_menu(env, chat_id=456, actor=456):
    await env.m.settings_command(update(Message(env.bot, '/settings', chat_id), actor), env.context)
    return env.bot.sent[-1]


def button_data(menu, text):
    return next(b.callback_data for row in menu.reply_markup.inline_keyboard for b in row if text in b.text)


async def click(env, menu, text=None, *, data=None, actor=456):
    query = Query(menu, data or button_data(menu, text), actor)
    await env.m.settings_callback(update(menu, actor, query), env.context)
    return query


async def reply(env, text, *, prompt=None, actor=456):
    prompt = prompt or env.bot.sent[-1]
    message = Message(env.bot, text, actor, reply_to=prompt)
    await env.m.plain_text_remind_command(update(message, actor), env.context)
    return message


@pytest.mark.asyncio
async def test_custom_time_validates_and_returns_to_same_menu_after_restart(env):
    menu = await open_menu(env)
    await click(env, menu, 'Время по умолчанию')
    await click(env, menu, 'Своё время')
    prompt = env.bot.sent[-1]
    assert prompt.reply_markup is not None
    # The prompt/session survives losing all in-memory Telegram context.
    env.context.user_data.clear()
    env.m.init_db()
    await reply(env, '25:00', prompt=prompt)
    assert env.m.get_user_default_time(456) is None
    assert 'корректное время' in env.bot.sent[-1].text
    await reply(env, '8.45')
    assert env.m.get_user_default_time(456) == (8, 45)
    assert '08:45' in menu.text
    assert len([m for m in env.bot.sent if '⚙️ Настройки' in m.text]) == 0


@pytest.mark.asyncio
async def test_custom_zone_requires_confirmation_and_preserves_existing_migration_flow(env):
    rid = env.m.add_reminder(456, 'вода', env.clock['now'] + timedelta(days=1), 456)
    menu = await open_menu(env)
    await click(env, menu, 'Часовой пояс')
    await click(env, menu, 'Другой город')
    await reply(env, 'Europe/Berlin')
    assert env.m.get_user_timezone_name(456) == 'Europe/Madrid'
    env.context.user_data.clear()
    await click(env, menu, 'Europe/Berlin')
    assert env.m.get_user_timezone_name(456) == 'Europe/Berlin'
    assert 'Перенести активные' in menu.text
    old = env.m.get_reminder(rid).remind_at
    await click(env, menu, 'Не переносить')
    assert env.m.get_reminder(rid).remind_at == old
    assert 'Europe/Berlin' in menu.text


@pytest.mark.asyncio
async def test_custom_city_and_unrecognised_timezone(env):
    menu = await open_menu(env)
    await click(env, menu, 'Часовой пояс')
    await click(env, menu, 'Другой город')
    await reply(env, 'несуществующий город')
    assert 'Не нашёл' in env.bot.sent[-1].text
    await reply(env, 'Тбилиси')
    await click(env, menu, 'Asia/Tbilisi')
    assert env.m.get_user_timezone_name(456) == 'Asia/Tbilisi'


@pytest.mark.asyncio
async def test_nudge_count_and_individual_custom_intervals_are_saved_atomically(env):
    menu = await open_menu(env)
    await click(env, menu, 'Повторные')
    await click(env, menu, 'Настроить')
    await click(env, menu, 'Количество')
    await click(env, menu, 'Другое количество')
    await reply(env, '5')
    await click(env, menu, '2.')
    await click(env, menu, 'Свой интервал')
    await reply(env, '1 ч 30 мин')
    assert env.store.nudges(456)['gaps'] == DEFAULT_GAPS
    env.context.user_data.clear()
    env.m.init_db()
    assert '2. 1 час 30 минут' in [b.text for row in menu.reply_markup.inline_keyboard for b in row]
    await click(env, menu, 'Сохранить')
    assert env.store.nudges(456)['gaps'] == [20, 90, 240, 720, 720]
    assert '5 дополнительных' in menu.text
    assert '90' not in menu.text or '1 час 30 минут' in menu.text


@pytest.mark.asyncio
async def test_draft_cancel_and_custom_input_cancel_do_not_change_settings(env):
    menu = await open_menu(env)
    await click(env, menu, 'Повторные')
    await click(env, menu, 'Настроить')
    await click(env, menu, '1.')
    await click(env, menu, 'Свой интервал')
    prompt = env.bot.sent[-1]
    await reply(env, '/cancel')
    assert 'Промежуток 1' in menu.text
    await click(env, menu, '10 минут')
    await click(env, menu, 'Отмена')
    assert env.store.nudges(456)['gaps'] == DEFAULT_GAPS
    await reply(env, '1 ч', prompt=prompt)
    assert 'запрос уже закрыт' in env.bot.sent[-1].text


@pytest.mark.asyncio
async def test_settings_input_only_consumes_reply_to_current_prompt(env):
    menu = await open_menu(env)
    await click(env, menu, 'Время по умолчанию')
    await click(env, menu, 'Своё время')
    unrelated = Message(env.bot, 'напомни через час погулять')
    assert await env.m.settings_custom_text(update(unrelated), env.context) is False
    other_user = Message(env.bot, '09:15', chat_id=999, reply_to=env.bot.sent[-1])
    assert await env.m.settings_custom_text(update(other_user, 999), env.context) is False
    assert env.m.get_user_default_time(456) is None


@pytest.mark.asyncio
async def test_stale_buttons_wrong_actor_group_and_expiry_cannot_change_settings(env):
    menu = await open_menu(env)
    await click(env, menu, 'Повторные')
    old_data = button_data(menu, 'Выключить')
    wrong = await click(env, menu, data=old_data, actor=999)
    assert wrong.answers[-1][1]['show_alert']
    assert env.store.nudges(456)['enabled']
    await click(env, menu, 'Настроить')
    stale = await click(env, menu, data=old_data)
    assert stale.answers[-1][1]['show_alert']
    assert env.store.nudges(456)['enabled']
    env.clock['now'] += timedelta(days=2)
    expired = await click(env, menu, 'Количество')
    assert expired.answers[-1][1]['show_alert']
    group = await open_menu(env, chat_id=-100)
    assert 'личном чате' in group.text and group.reply_markup is None
    assert 'Мои алиасы' not in group.text


@pytest.mark.asyncio
async def test_expired_settings_reply_is_not_parsed_as_new_reminder(env):
    menu = await open_menu(env)
    await click(env, menu, 'Время по умолчанию')
    await click(env, menu, 'Своё время')
    prompt = env.bot.sent[-1]
    env.clock['now'] += timedelta(days=2)
    await reply(env, '09:30', prompt=prompt)
    assert env.m.get_user_default_time(456) is None
    assert 'запрос уже закрыт' in env.bot.sent[-1].text


@pytest.mark.asyncio
async def test_menu_aliases_list_and_new_menu_invalidate_old_callbacks(env):
    menu = await open_menu(env)
    data = button_data(menu, 'Время по умолчанию')
    await click(env, menu, 'Мои алиасы')
    assert 'Алиасов пока нет' in menu.text
    await click(env, menu, 'Назад')
    await click(env, menu, 'Мои напоминания')
    assert 'напоминан' in env.bot.sent[-1].text.lower()
    await open_menu(env)
    result = await click(env, menu, data=data)
    assert result.answers[-1][1]['show_alert']


@pytest.mark.parametrize('value,expected', [('45 мин',45),('1 ч 30 мин',90),('2 дня',2880),('1.5 hours',90),('0,5 ч',30)])
def test_custom_interval_parser(value, expected):
    assert parse_interval(value) == expected


@pytest.mark.parametrize('value', ['0 мин','-1 ч','12:30','завтра','0.5 мин','1 ч мусор','99999999999999 дней'])
def test_custom_interval_parser_rejects_invalid_input(value):
    with pytest.raises(ValueError):
        parse_interval(value)


def test_iana_and_city_lookup_require_no_network_and_do_not_guess():
    assert search_timezones('Берлин') == ['Europe/Berlin']
    assert search_timezones('america/new_york') == ['America/New_York']
    assert search_timezones('not a real place') == []


@pytest.mark.asyncio
async def test_all_generated_settings_callbacks_fit_telegram_limit(env):
    menu = await open_menu(env)
    for label in ('Повторные', 'Настроить', 'Количество'):
        await click(env, menu, label)
        assert all(len(b.callback_data.encode()) <= 64 for row in menu.reply_markup.inline_keyboard for b in row)


def dbrow(env, rid):
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute('SELECT * FROM reminders WHERE id=?',(rid,)).fetchone())


def delivered(env, *, chat_id=456, created_by=456, source=False):
    kwargs = {'source_chat_id':chat_id,'source_message_id':77} if source else {}
    rid = env.m.add_reminder(chat_id, 'проверить документ', env.clock['now'], created_by, **kwargs)
    env.m.mark_reminder_sent(rid, env.clock['now'])
    return rid


class StopWorker(Exception):
    pass


async def nudge_once(env):
    from dkreminders_bot.workers.reminders_workers import run_reminders_nudge_worker
    deps = env.m._build_reminders_worker_deps()

    async def stop(_):
        raise StopWorker

    deps.asyncio = SimpleNamespace(sleep=stop)
    with pytest.raises(StopWorker):
        await run_reminders_nudge_worker(SimpleNamespace(bot=env.bot), deps)


@pytest.mark.asyncio
async def test_policy_is_snapshotted_at_delivery_and_new_settings_do_not_rewrite_old_cycle(env):
    env.store.set_gaps(456,[5, 15],env.clock['now'])
    old = delivered(env)
    env.store.set_gaps(456,[60],env.clock['now'])
    new = delivered(env)
    assert json.loads(dbrow(env,old)['nudge_policy_json']) == [5,15]
    env.clock['now'] += timedelta(minutes=5)
    assert [r['id'] for r in env.m.get_due_nudges(env.clock['now'])] == [old]
    await nudge_once(env)
    assert dbrow(env,old)['nudge_count'] == 1
    assert dbrow(env,new)['nudge_count'] == 0
    env.clock['now'] += timedelta(minutes=14)
    await nudge_once(env)
    assert len(env.bot.sent) == 1
    env.clock['now'] += timedelta(minutes=1)
    await nudge_once(env)
    assert dbrow(env,old)['nudge_count'] == 2
    assert len(env.bot.sent) == 2


@pytest.mark.asyncio
async def test_arbitrary_schedule_can_send_more_than_four_nudges_and_stops_at_length(env):
    env.store.set_gaps(456,[1,2,3,4,5,6],env.clock['now'])
    rid = delivered(env,source=True)
    for index, gap in enumerate([1,2,3,4,5,6]):
        env.clock['now'] += timedelta(minutes=gap)
        await nudge_once(env)
        assert dbrow(env,rid)['nudge_count'] == index+1
        assert env.bot.sent[-1].send_kwargs['reply_to_message_id'] == 77
        assert env.bot.sent[-1].send_kwargs['allow_sending_without_reply'] is True
    env.clock['now'] += timedelta(days=2)
    await nudge_once(env)
    assert len(env.bot.sent) == 6


@pytest.mark.asyncio
async def test_disable_is_immediate_and_reenable_does_not_revive_old_deliveries(env):
    env.store.set_gaps(456,[1],env.clock['now'])
    old = delivered(env)
    env.clock['now'] += timedelta(minutes=2)
    env.store.set_enabled(456,False,env.clock['now'])
    muted = delivered(env)
    await nudge_once(env)
    assert not env.bot.sent
    assert dbrow(env,old)['nudge_count'] == 0
    env.clock['now'] += timedelta(seconds=1)
    env.store.set_enabled(456,True,env.clock['now'])
    # Repeated On callbacks must not move the resume threshold.
    resume = env.store.nudges(456)['resume_after']
    env.clock['now'] += timedelta(seconds=1)
    env.store.set_enabled(456,True,env.clock['now'])
    assert env.store.nudges(456)['resume_after'] == resume
    fresh = delivered(env)
    env.clock['now'] += timedelta(minutes=2)
    await nudge_once(env)
    assert len(env.bot.sent) == 1
    assert dbrow(env,fresh)['nudge_count'] == 1
    assert dbrow(env,old)['nudge_count'] == dbrow(env,muted)['nudge_count'] == 0


@pytest.mark.asyncio
async def test_recipient_settings_apply_even_when_another_person_created_reminder(env):
    env.store.set_enabled(456,False,env.clock['now'])
    env.store.set_gaps(999,[1],env.clock['now'])
    rid = delivered(env,chat_id=999,created_by=456)
    env.clock['now'] += timedelta(minutes=1)
    await nudge_once(env)
    assert len(env.bot.sent) == 1 and env.bot.sent[0].chat_id == 999
    assert dbrow(env,rid)['nudge_count'] == 1


@pytest.mark.asyncio
async def test_restart_and_downtime_do_not_send_catchup_burst(env):
    rid = delivered(env)
    env.clock['now'] += timedelta(days=2)
    env.m.init_db()
    await nudge_once(env)
    await nudge_once(env)
    assert len(env.bot.sent) == 1 and dbrow(env,rid)['nudge_count'] == 1
    env.clock['now'] += timedelta(minutes=59)
    await nudge_once(env)
    assert len(env.bot.sent) == 1
    env.clock['now'] += timedelta(minutes=1)
    await nudge_once(env)
    assert len(env.bot.sent) == 2


@pytest.mark.asyncio
async def test_failed_telegram_send_does_not_spend_nudge(env, monkeypatch):
    env.store.set_gaps(456,[1],env.clock['now'])
    rid = delivered(env)
    env.clock['now'] += timedelta(minutes=1)

    async def fail(**kwargs):
        raise RuntimeError('Telegram unavailable')

    monkeypatch.setattr(env.bot,'send_message',fail)
    await nudge_once(env)
    assert dbrow(env,rid)['nudge_count'] == 0
    assert dbrow(env,rid)['last_nudge_at'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('action',['disable','done'])
async def test_worker_rechecks_state_after_awaiting_chat_type(env, monkeypatch, action):
    env.store.set_gaps(456,[1],env.clock['now'])
    rid = delivered(env)
    env.clock['now'] += timedelta(minutes=1)

    async def chat(chat_id):
        if action == 'disable':
            env.store.set_enabled(456,False,env.clock['now'])
        else:
            env.m.mark_reminder_acked(rid)
        return SimpleNamespace(type='private')

    monkeypatch.setattr(env.bot,'get_chat',chat)
    await nudge_once(env)
    assert not env.bot.sent


@pytest.mark.asyncio
async def test_snooze_stops_old_cycle_and_new_delivery_uses_current_recipient_gaps(env):
    env.store.set_gaps(456,[1,2],env.clock['now'])
    rid = delivered(env,source=True)
    env.clock['now'] += timedelta(minutes=1)
    await nudge_once(env)
    sent = env.bot.sent[-1]
    query = Query(sent,f'snooze:{rid}:20m')
    await env.m.snooze_callback(update(sent,query=query),env.context)
    assert dbrow(env,rid)['acked'] == 1
    env.store.set_gaps(456,[5],env.clock['now'])
    with sqlite3.connect(env.m.DB_PATH) as conn:
        new_id = conn.execute('SELECT max(id) FROM reminders').fetchone()[0]
    assert new_id != rid
    env.clock['now'] += timedelta(minutes=20)
    env.m.mark_reminder_sent(new_id,env.clock['now'])
    assert json.loads(dbrow(env,new_id)['nudge_policy_json']) == [5]
    assert dbrow(env,new_id)['source_message_id'] == 77
    before = len(env.bot.sent)
    env.clock['now'] += timedelta(minutes=4)
    await nudge_once(env)
    assert len(env.bot.sent) == before
    env.clock['now'] += timedelta(minutes=1)
    await nudge_once(env)
    assert len(env.bot.sent) == before+1


@pytest.mark.asyncio
async def test_legacy_rows_keep_default_policy_and_exhaust_never_revives_with_longer_schedule(env):
    rid = delivered(env)
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute('UPDATE reminders SET nudge_policy_json=NULL,nudge_count=2 WHERE id=?',(rid,))
    env.clock['now'] += timedelta(minutes=320)
    await nudge_once(env)
    assert dbrow(env,rid)['nudge_count'] == 3
    env.m.exhaust_nudges(rid)
    env.store.set_gaps(456,[1]*20,env.clock['now'])
    env.clock['now'] += timedelta(days=10)
    await nudge_once(env)
    assert len(env.bot.sent) == 1


@pytest.mark.asyncio
async def test_nudge_schedule_measures_elapsed_time_across_dst(env):
    env.store.set_gaps(456,[30],env.clock['now'])
    env.clock['now'] = datetime(2026,10,25,2,45,tzinfo=ZoneInfo('Europe/Madrid'),fold=0)
    rid = delivered(env)
    env.clock['now'] = datetime(2026,10,25,2,14,tzinfo=ZoneInfo('Europe/Madrid'),fold=1)
    await nudge_once(env)
    assert not env.bot.sent
    env.clock['now'] = datetime(2026,10,25,2,15,tzinfo=ZoneInfo('Europe/Madrid'),fold=1)
    await nudge_once(env)
    assert dbrow(env,rid)['nudge_count'] == 1


def test_new_settings_migrations_preserve_rows_and_are_idempotent(env):
    rid = env.m.add_reminder(456,'старое',env.clock['now'],456)
    before = dbrow(env,rid)
    env.m.init_db()
    env.m.init_db()
    assert dbrow(env,rid) == before
    assert env.store.nudges(456)['gaps'] == DEFAULT_GAPS
    assert env.m.get_user_timezone_name(456) == 'Europe/Madrid'
    with pytest.raises(ValueError):
        env.store.set_gaps(456,[],env.clock['now'])


@pytest.mark.asyncio
async def test_tracking_error_after_successful_send_does_not_repeat_nudge(env, monkeypatch):
    env.store.set_gaps(456,[1,5],env.clock['now'])
    rid = delivered(env)
    env.clock['now'] += timedelta(minutes=1)

    def fail(**kwargs):
        raise RuntimeError('tracking write unavailable')

    monkeypatch.setattr(env.m,'register_reminder_message',fail)
    await nudge_once(env)
    assert dbrow(env,rid)['nudge_count'] == 1
    env.clock['now'] += timedelta(seconds=30)
    await nudge_once(env)
    assert len(env.bot.sent) == 1


@pytest.mark.asyncio
async def test_custom_timezone_migration_survives_restart_and_old_buttons_cannot_run_twice(env):
    when = env.clock['now'] + timedelta(days=1)
    rid = env.m.add_reminder(456,'вода',when,456)
    menu = await open_menu(env)
    await click(env,menu,'Часовой пояс')
    await click(env,menu,'Другой город')
    await reply(env,'Asia/Tokyo')
    await click(env,menu,'Asia/Tokyo')
    data = button_data(menu,'Да, все')
    env.context.user_data.clear()
    await click(env,menu,data=data)
    moved = env.m.get_reminder(rid).remind_at
    assert moved.hour == when.hour and moved.utcoffset() == timedelta(hours=9)
    assert moved.timestamp() != when.timestamp()
    repeated = await click(env,menu,data=data)
    assert repeated.answers[-1][1]['show_alert']
    assert env.m.get_reminder(rid).remind_at == moved


@pytest.mark.asyncio
async def test_first_timezone_can_be_custom_and_resumes_pending_plain_text_reminder(env):
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute('DELETE FROM user_settings WHERE user_id=456')
    env.context.user_data['pending_plain_text_reminder_after_timezone'] = 'напомни через час проверить воду'
    menu = await open_menu(env)
    assert 'Не выбран' in menu.text
    await click(env,menu,'Часовой пояс')
    await click(env,menu,'Другой город')
    await reply(env,'Asia/Tokyo')
    await click(env,menu,'Asia/Tokyo')
    assert env.m.get_user_timezone_name_raw(456) == 'Asia/Tokyo'
    assert 'pending_plain_text_reminder_after_timezone' not in env.context.user_data
    with sqlite3.connect(env.m.DB_PATH) as conn:
        assert conn.execute('SELECT count(*) FROM reminders').fetchone()[0] == 1


@pytest.mark.asyncio
async def test_settings_callback_wrappers_ignore_noncallback_update(env):
    ordinary = update(Message(env.bot,'текст'))
    await env.m.settings_callback(ordinary,env.context)
    await env.m.timezone_settings_callback(ordinary,env.context)
    assert not env.bot.sent
