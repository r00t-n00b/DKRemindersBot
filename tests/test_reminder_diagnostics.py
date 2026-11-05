import sqlite3
from datetime import timedelta

import pytest

from dkreminders_bot.commands.reminder_diagnostics import SESSION_KEY
from dkreminders_bot.storage.reminder_diagnostics import ReminderDiagnosticsStore
from test_settings_menu_integration import env, Message, Query, update, button_data


def add(env, text='Своя задача', target=456, owner=456):
    return env.m.add_reminder(target, text, env.clock['now'], owner)


async def command(env, args=(), *, actor=456, chat_id=456):
    env.context.args = list(args)
    message = Message(env.bot, '/debug_reminders', chat_id)
    await env.m.debug_reminders_command(update(message, actor), env.context)
    return env.bot.sent[-1]


async def click(env, menu, text=None, *, data=None, actor=456):
    query = Query(menu, data or button_data(menu, text), actor)
    await env.m.debug_reminders_callback(update(menu, actor, query), env.context)
    return query


def fingerprint(env):
    with sqlite3.connect(env.m.DB_PATH) as c:
        names = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
        return {n: c.execute('select * from "'+n+'" order by rowid').fetchall() for n in names}


@pytest.mark.asyncio
async def test_history_includes_created_delivered_done_and_tracking_without_writes(env):
    pending = add(env, 'Ожидающая задача')
    done = add(env, 'Завершённая задача', target=999)
    now = env.clock['now'].isoformat()
    with sqlite3.connect(env.m.DB_PATH) as c:
        c.execute('''UPDATE reminders SET delivered=1,acked=1,sent_at=?,nudge_count=2,
            delivery_state='sent',delivery_attempts=3,last_nudge_at=?,source_chat_id=456,
            source_message_id=808,last_error='Temporary timeout',next_retry_at=? WHERE id=?''', (now, now, now, done))
        for i, kind in enumerate(['created', 'delivery', 'nudge', 'nudge']):
            c.execute('INSERT INTO reminder_messages(reminder_id,chat_id,message_id,kind,created_at) VALUES(?,?,?,?,?)', (done, 456, 100+i, kind, now))
    before = fingerprint(env)
    menu = await command(env)
    assert 'Ожидающая задача' in menu.text and 'Завершённая задача' in menu.text
    assert f'#{done} · Выполнено' in menu.text and f'#{pending} · Ожидает' in menu.text
    assert 'Доставлено: да · Выполнено: да' in menu.text
    assert 'Повторы: 2' in menu.text and 'попыток: 3' in menu.text
    assert 'создано 1 · доставка 1 · повторы 2' in menu.text
    assert '456/808' in menu.text and 'Temporary timeout' in menu.text
    assert now in menu.text
    assert fingerprint(env) == before


@pytest.mark.asyncio
async def test_default_history_never_shows_foreign_or_legacy_null_creator(env):
    add(env, 'Своё себе')
    add(env, 'Своё человеку', target=999)
    add(env, 'Своё группе', target=-100)
    add(env, 'Чужое мне', owner=777)
    add(env, 'Чужое группе', target=-100, owner=777)
    add(env, 'Наследие без владельца', owner=None)
    menu = await command(env)
    assert all(t in menu.text for t in ['Своё себе', 'Своё человеку', 'Своё группе'])
    assert all(t not in menu.text for t in ['Чужое мне', 'Чужое группе', 'Наследие без владельца'])
    assert 'Последние 3' in menu.text


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['user', 'chat', 'username', 'legacy_multiword'])
async def test_recipient_filter_checks_creator_and_alias_ownership(env, kind):
    if kind in {'user', 'legacy_multiword'}:
        target = 999
        alias = 'Старое имя' if kind == 'legacy_multiword' else 'Друг'
        env.m.set_user_alias(alias, target, target, 'natasha', 456)
        env.m.set_user_alias(alias, 888, 888, 'other', 777)
        args = alias.lower().split()
    elif kind == 'chat':
        target = -100
        env.m.set_chat_alias('Работа', target, 'Work', 456)
        env.m.set_chat_alias('Работа', -200, 'Other', 777)
        args = ['рАБОТА']
    else:
        target = 999
        env.m.upsert_user_chat(999, 999, 'natasha', 'Natasha', None)
        args = ['@NATASHA']
    add(env, 'Нужная запись', target=target)
    add(env, 'Другой получатель', target=123)
    add(env, 'Чужая запись', target=target, owner=777)
    menu = await command(env, args)
    assert 'Нужная запись' in menu.text
    assert 'Другой получатель' not in menu.text and 'Чужая запись' not in menu.text


@pytest.mark.asyncio
async def test_unknown_foreign_and_ambiguous_aliases_do_not_fall_back_to_all(env):
    add(env, 'Не показывать при ошибке')
    env.m.set_chat_alias('Чужой', -100, 'Work', 777)
    for target in ['неизвестный', 'Чужой', '@unknown', '@bad!']:
        menu = await command(env, [target])
        assert 'Получатель не найден' in menu.text
        assert 'Не показывать' not in menu.text
    env.m.set_user_alias('Одинаковый', 999, 999, 'natasha', 456)
    env.m.set_chat_alias('одинаковый', -100, 'Work', 456)
    menu = await command(env, ['Одинаковый'])
    assert 'несколько получателей' in menu.text


@pytest.mark.asyncio
async def test_history_limit_pagination_refresh_and_independence_from_other_menus(env):
    ids = [add(env, f'Задача{i:02d}') for i in range(25)]
    env.context.user_data.update(list_ids=[777], pending={'keep': True})
    menu = await command(env)
    assert 'Последние 20' in menu.text and 'страница 1/4' in menu.text
    assert menu.text.index('Задача24') < menu.text.index('Задача20')
    old_next = button_data(menu, '→')
    await click(env, menu, data=old_next)
    assert 'страница 2/4' in menu.text and 'Задача19' in menu.text
    stale = await click(env, menu, data=old_next)
    assert stale.answers[0][1].get('show_alert')
    await click(env, menu, '→')
    await click(env, menu, '→')
    assert 'Задача05' in menu.text and 'Задача04' not in menu.text
    with sqlite3.connect(env.m.DB_PATH) as c:
        c.execute('DELETE FROM reminders WHERE id>?', (ids[1],))
    await click(env, menu, 'Обновить')
    assert 'страница 1/1' in menu.text and 'Последние 2' in menu.text
    assert env.context.user_data['list_ids'] == [777] and env.context.user_data['pending'] == {'keep': True}
    await command(env)
    stale = await click(env, menu, 'Обновить')
    assert stale.answers[0][1].get('show_alert')


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['group', 'other_private', 'wrong_actor', 'wrong_message', 'expired', 'restart', 'malformed', 'invalid_page', 'negative'])
async def test_diagnostics_reject_invalid_callback_before_reading_storage(env, monkeypatch, case):
    add(env)
    menu = await command(env)
    data = button_data(menu, 'Обновить')
    actor = 456
    if case == 'group':
        menu.chat.type = 'supergroup'
        menu.chat.id = -100
    elif case == 'other_private':
        menu.chat.id = 777
    elif case == 'wrong_actor':
        actor = 777
    elif case == 'wrong_message':
        menu.message_id += 1
    elif case == 'expired':
        env.clock['now'] += timedelta(minutes=31)
    elif case == 'restart':
        env.context.user_data.clear()
    elif case == 'malformed':
        data = 'diag:broken'
    elif case == 'invalid_page':
        data = data.replace(':refresh', ':abc')
    else:
        data = data.replace(':refresh', ':-1')
    def forbidden(*args):
        pytest.fail('Unauthorized callback read the database')
    monkeypatch.setattr(ReminderDiagnosticsStore, 'recent', forbidden)
    q = await click(env, menu, data=data, actor=actor)
    assert q.answers[0][1].get('show_alert')


@pytest.mark.asyncio
@pytest.mark.parametrize('chat_id,actor', [(-100,456), (777,456)])
async def test_command_is_private_only_before_reading_database(env, monkeypatch, chat_id, actor):
    def forbidden(*args):
        pytest.fail('Non-private command read the database')
    monkeypatch.setattr(ReminderDiagnosticsStore, 'recent', forbidden)
    menu = await command(env, chat_id=chat_id, actor=actor)
    assert 'только в личном' in menu.text


@pytest.mark.asyncio
async def test_empty_history_can_be_refreshed(env):
    menu = await command(env)
    assert 'Напоминаний не найдено' in menu.text
    add(env, 'Новая задача')
    await click(env, menu, 'Обновить')
    assert 'Новая задача' in menu.text


@pytest.mark.asyncio
async def test_errors_are_redacted_and_messages_fit_telegram_limits(env, monkeypatch):
    token = '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456789'
    secret = 'configured-secret-value'
    monkeypatch.setenv('GEMINI_API_KEY', secret)
    for i in range(5):
        rid = add(env, f'{i}🌻'*500)
        with sqlite3.connect(env.m.DB_PATH) as c:
            c.execute('UPDATE reminders SET last_error=?,timezone_name=? WHERE id=?', (
                f'HTTP https://api.telegram.org/bot{token}/sendMessage\n{secret} API AIza'+'x'*40+'🌻'*500, '🌻'*1000, rid,
            ))
    menu = await command(env)
    assert '[скрыто]' in menu.text
    assert token not in menu.text and secret not in menu.text and 'AIza' not in menu.text
    assert len(menu.text.encode('utf-16-le'))//2 <= 4096
    assert all(len(b.callback_data.encode()) <= 64 for row in menu.reply_markup.inline_keyboard for b in row)
    assert menu.reply_markup is not None


@pytest.mark.asyncio
async def test_missing_database_is_not_created_and_failure_does_not_change_state(env, monkeypatch, tmp_path):
    path = tmp_path/'missing.db'
    monkeypatch.setattr(env.m, 'DB_PATH', str(path))
    menu = await command(env)
    assert 'Не удалось прочитать' in menu.text
    assert not path.exists()
    assert SESSION_KEY not in env.context.user_data


@pytest.mark.asyncio
async def test_callback_read_error_keeps_session_for_retry(env, monkeypatch):
    add(env)
    menu = await command(env)
    old = dict(env.context.user_data[SESSION_KEY])
    def fail(*args):
        raise sqlite3.OperationalError('database busy')
    with monkeypatch.context() as patch:
        patch.setattr(ReminderDiagnosticsStore, 'recent', fail)
        q = await click(env, menu, 'Обновить')
        assert 'Не удалось прочитать' in q.answers[0][0]
        assert env.context.user_data[SESSION_KEY] == old
    await click(env, menu, 'Обновить')
    assert 'Своя задача' in menu.text


@pytest.mark.asyncio
async def test_edit_fallback_binds_new_message_and_old_message_expires(env, monkeypatch):
    add(env)
    menu = await command(env)
    async def fail(*args, **kwargs):
        raise RuntimeError('message to edit not found')
    monkeypatch.setattr(Query, 'edit_message_text', fail)
    await click(env, menu, 'Обновить')
    replacement = env.bot.sent[-1]
    assert replacement.message_id != menu.message_id
    assert env.context.user_data[SESSION_KEY]['message_id'] == replacement.message_id
    q = await click(env, menu, 'Обновить')
    assert q.answers[0][1].get('show_alert')
    await click(env, replacement, 'Обновить')
    assert 'Своя задача' in env.bot.sent[-1].text


def test_diagnostic_reads_are_sqlite_read_only_and_preserve_all_rows(env, monkeypatch):
    add(env)
    before = fingerprint(env)
    original = sqlite3.connect
    def connect(database_uri, **kwargs):
        assert database_uri.endswith('?mode=ro') and kwargs.get('uri') is True
        conn = original(database_uri, **kwargs)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute('UPDATE reminders SET text=\'broken\'')
        conn.rollback()
        return conn
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, 'connect', connect)
        rows = ReminderDiagnosticsStore(env.m.DB_PATH).recent(456)
    assert len(rows) == 1
    assert fingerprint(env) == before


def test_commands_and_callback_are_registered(env, monkeypatch):
    commands, callbacks = [], []
    class App:
        @classmethod
        def builder(cls): return cls()
        def token(self, value): return self
        def post_init(self, value): return self
        def post_shutdown(self, value): return self
        def build(self): return self
        def add_handler(self, handler): pass
        def run_polling(self): pass
    def command_handler(names, callback):
        commands.append((names, callback))
    def callback_handler(callback, **kwargs):
        callbacks.append((callback, kwargs))
    monkeypatch.setenv('BOT_TOKEN', 'test-token')
    monkeypatch.setattr(env.m, 'Application', App)
    monkeypatch.setattr(env.m, 'CommandHandler', command_handler)
    monkeypatch.setattr(env.m, 'CallbackQueryHandler', callback_handler)
    monkeypatch.setattr(env.m, 'MessageHandler', lambda *args, **kwargs: None)
    monkeypatch.setattr(env.m, 'run_polling_forever', lambda *args, **kwargs: None)
    env.m.main()
    assert ('debug_reminders', env.m.debug_reminders_command) in commands
    assert ('history', env.m.debug_reminders_command) in commands
    assert any(c == env.m.debug_reminders_callback and kwargs['pattern'] == '^diag:' for c, kwargs in callbacks)
