import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from datetime import timedelta

import pytest

from dkreminders_bot.domain.alias_names import validate_alias_name
from dkreminders_bot.storage.alias_menu_store import AliasMenuStore
from test_settings_menu_integration import env, open_menu, click, reply, button_data, update, Message


async def aliases_menu(env):
    menu = await open_menu(env)
    await click(env, menu, 'Мои алиасы')
    return menu


def known_user(env, user_id=999, username='natasha'):
    env.m.upsert_user_chat(user_id, user_id, username, 'Test', 'User')


async def person_preview(env, name='Наташа', username='@natasha'):
    menu = await aliases_menu(env)
    await click(env, menu, 'Добавить алиас')
    await click(env, menu, 'Человек')
    await reply(env, name)
    await reply(env, username)
    return menu


@pytest.mark.asyncio
async def test_create_person_confirms_then_real_remind_routes_to_target(env):
    known_user(env)
    menu = await person_preview(env)
    assert env.m.get_user_alias('Наташа',456) is None
    assert 'Создать алиас?' in menu.text and '@natasha' in menu.text
    env.context.user_data.clear()
    env.m.init_db()
    commit = button_data(menu,'Создать алиас')
    await click(env,menu,data=commit)
    row = env.m.get_user_alias('Наташа',456)
    assert row['chat_id'] == row['user_id'] == 999
    await click(env,menu,data=commit)
    assert len(env.m.get_all_user_aliases(456)) == 1
    message = Message(env.bot,'/remind Наташа через час - проверить воду')
    await env.m.remind_command(update(message),env.context)
    with sqlite3.connect(env.m.DB_PATH) as conn:
        assert conn.execute('SELECT chat_id,text FROM reminders').fetchall() == [(999,'проверить воду')]


@pytest.mark.asyncio
async def test_person_creation_can_cancel_without_saving_and_does_not_intercept_other_text(env):
    known_user(env)
    menu = await aliases_menu(env)
    await click(env,menu,'Добавить алиас')
    await click(env,menu,'Человек')
    name_prompt = env.bot.sent[-1]
    assert await env.m.settings_custom_text(update(Message(env.bot,'через час - другое')),env.context) is False
    await reply(env,'Коллега')
    env.context.user_data.clear()
    await reply(env,'@natasha')
    await click(env,menu,'Отмена')
    assert env.m.get_all_user_aliases(456) == []
    await reply(env,'ЕщёИмя',prompt=name_prompt)
    assert 'запрос уже закрыт' in env.bot.sent[-1].text


@pytest.mark.asyncio
async def test_rename_person_and_delete_preserve_existing_reminders(env):
    known_user(env)
    env.m.set_user_alias('Наташа',999,999,'natasha',456)
    rid = env.m.add_reminder(999,'старое',env.clock['now'],456)
    menu = await aliases_menu(env)
    await click(env,menu,'👤 Наташа')
    await click(env,menu,'Переименовать')
    await reply(env,'Жена')
    assert env.m.get_user_alias('Наташа',456) is not None
    assert 'Наташа → Жена' in menu.text
    await click(env,menu,'Сохранить новое имя')
    assert env.m.get_user_alias('Наташа',456) is None
    assert env.m.get_user_alias('Жена',456)['chat_id'] == 999
    await click(env,menu,'👤 Жена')
    await click(env,menu,'Удалить')
    assert env.m.get_user_alias('Жена',456) is not None
    await click(env,menu,'Отмена')
    assert env.m.get_user_alias('Жена',456) is not None
    await click(env,menu,'👤 Жена')
    await click(env,menu,'Удалить')
    delete = button_data(menu,'Да, удалить')
    await click(env,menu,data=delete)
    await click(env,menu,data=delete)
    assert env.m.get_user_alias('Жена',456) is None
    assert env.m.get_reminder(rid).chat_id == 999


@pytest.mark.asyncio
async def test_invalid_names_unknown_username_and_casefold_conflicts_are_rejected(env):
    known_user(env)
    env.m.set_chat_alias('Работа',-100,'Work',456)
    menu = await aliases_menu(env)
    await click(env,menu,'Добавить алиас')
    await click(env,menu,'Человек')
    for invalid in ('завтра','me','@wrong','два слова','123','X'*65,'работа'):
        await reply(env,invalid)
        assert env.m.get_all_user_aliases(456) == []
    await reply(env,'Друг')
    await reply(env,'natasha')
    assert 'Отправь @username' in env.bot.sent[-1].text
    await reply(env,'@unknown_person')
    assert 'ещё не знаком' in env.bot.sent[-1].text
    await reply(env,'@natasha')
    assert 'Создать алиас?' in menu.text


@pytest.mark.asyncio
async def test_conflict_appearing_after_preview_never_overwrites_existing_alias(env):
    known_user(env)
    menu = await person_preview(env,'Коллега')
    env.m.set_chat_alias('коллега',-100,'Group',456)
    query = await click(env,menu,'Создать алиас')
    assert query.answers[-1][1]['show_alert']
    assert env.m.get_user_alias('Коллега',456) is None
    assert env.m.get_chat_id_by_alias('коллега',456) == -100


@pytest.mark.asyncio
async def test_username_target_is_revalidated_at_confirmation(env):
    known_user(env)
    menu = await person_preview(env)
    known_user(env,user_id=555,username='natasha')
    query = await click(env,menu,'Создать алиас')
    assert 'Получатель изменился' in query.answers[-1][0]
    assert env.m.get_all_user_aliases(456) == []


@pytest.mark.asyncio
async def test_external_commands_changing_selected_alias_make_confirmation_stale(env):
    env.m.set_user_alias('Друг',999,999,'natasha',456)
    menu = await aliases_menu(env)
    await click(env,menu,'👤 Друг')
    await click(env,menu,'Удалить')
    env.m.set_user_alias('Друг',555,555,'other',456)
    query = await click(env,menu,'Да, удалить')
    assert 'уже изменён' in query.answers[-1][0]
    assert env.m.get_user_alias('Друг',456)['chat_id'] == 555


@pytest.mark.asyncio
async def test_only_selected_kind_and_owner_change_even_for_legacy_duplicate_names(env):
    env.m.set_user_alias('Общий',999,999,'natasha',456)
    env.m.set_chat_alias('Общий',-100,'Group',456)
    env.m.set_user_alias('Общий',555,555,'other',777)
    menu = await aliases_menu(env)
    await click(env,menu,'👤 Общий')
    await click(env,menu,'Удалить')
    wrong = await click(env,menu,'Да, удалить',actor=777)
    assert wrong.answers[-1][1]['show_alert']
    assert env.m.get_user_alias('Общий',456) is not None
    await click(env,menu,'Да, удалить')
    assert env.m.get_user_alias('Общий',456) is None
    assert env.m.get_chat_id_by_alias('Общий',456) == -100
    assert env.m.get_user_alias('Общий',777)['chat_id'] == 555


@pytest.mark.asyncio
async def test_rename_case_only_and_cross_type_conflict_checks(env):
    env.m.set_user_alias('Друг',999,999,'natasha',456)
    env.m.set_chat_alias('Дом',-100,'Group',456)
    menu = await aliases_menu(env)
    await click(env,menu,'👤 Друг')
    await click(env,menu,'Переименовать')
    await reply(env,'дом')
    assert 'уже есть алиас' in env.bot.sent[-1].text
    await reply(env,'дРУГ')
    await click(env,menu,'Сохранить новое имя')
    assert env.m.get_user_alias('друг',456)['alias'] == 'дРУГ'


@pytest.mark.asyncio
async def test_pagination_uses_snapshots_and_keeps_callbacks_short_with_long_names(env):
    for i in range(19):
        env.m.set_user_alias(f'Человек{i:02d}',999,999,'natasha',456)
    env.m.set_user_alias('Я'*160,999,999,'natasha',456)
    env.m.set_user_alias('Чужой',555,555,'other',777)
    menu = await aliases_menu(env)
    assert 'Страница 1 из 3' in menu.text
    assert len([b for row in menu.reply_markup.inline_keyboard for b in row if 'a_open:' in b.callback_data]) == 8
    data = button_data(menu,'Человек00')
    # Reordering the underlying list cannot redirect an already shown index.
    env.m.set_user_alias('Ааа',555,555,'other',456)
    await click(env,menu,data=data)
    assert 'Человек00' in menu.text and '@natasha' in menu.text
    await click(env,menu,'К списку')
    await click(env,menu,'→')
    assert 'Страница 2' in menu.text
    await click(env,menu,'→')
    assert all(len(b.callback_data.encode()) <= 64 for row in menu.reply_markup.inline_keyboard for b in row)
    assert all('Чужой' not in b.text for row in menu.reply_markup.inline_keyboard for b in row)
    assert any('…' in b.text for row in menu.reply_markup.inline_keyboard for b in row)


@pytest.fixture
def groups(env,monkeypatch):
    env.bot.id = 987654321
    env.group_access = {'present':True,'title':'Рабочая группа','type':'supergroup'}

    async def get_chat(chat_id):
        return SimpleNamespace(id=chat_id,title=env.group_access['title'],type=env.group_access['type'])

    async def get_member(chat_id,user_id):
        assert user_id == env.bot.id
        return SimpleNamespace(status='member' if env.group_access['present'] else 'left')

    monkeypatch.setattr(env.bot,'get_chat',get_chat)
    monkeypatch.setattr(env.bot,'get_chat_member',get_member,raising=False)
    return env


async def group_picker(env):
    menu = await aliases_menu(env)
    await click(env,menu,'Добавить алиас')
    await click(env,menu,'Группа')
    await reply(env,'Работа')
    request = env.bot.sent[-1].reply_markup.keyboard[0][0].request_chat
    assert request.bot_is_member is True and request.chat_is_channel is False
    return menu,request.request_id


async def share(env,request_id,chat_id=-100,actor=456):
    message = Message(env.bot,chat_id=actor)
    message.chat_shared = SimpleNamespace(request_id=request_id,chat_id=chat_id)
    await env.m.settings_chat_shared(update(message,actor),env.context)
    return message


@pytest.mark.asyncio
async def test_native_group_picker_survives_restart_and_requires_final_confirmation(groups):
    env=groups
    menu,request_id = await group_picker(env)
    env.context.user_data.clear()
    env.m.init_db()
    await share(env,request_id)
    assert 'Создать алиас?' in menu.text and 'Рабочая группа' in menu.text
    assert env.m.get_all_aliases(456) == []
    assert env.bot.sent[-1].reply_markup.remove_keyboard is True
    await click(env,menu,'Создать алиас')
    assert env.m.get_chat_id_by_alias('Работа',456) == -100
    await click(env,menu,'💬 Работа')
    await click(env,menu,'Переименовать')
    await reply(env,'Команда')
    await click(env,menu,'Сохранить новое имя')
    assert env.m.get_chat_id_by_alias('Команда',456) == -100
    assert env.m.get_chat_id_by_alias('Работа',456) is None


@pytest.mark.asyncio
async def test_group_selection_rejects_wrong_actor_request_channels_and_missing_bot(groups):
    env=groups
    menu,request_id=await group_picker(env)
    await share(env,request_id,actor=777)
    await share(env,request_id+1)
    assert env.m.get_all_aliases(456) == []
    env.group_access['type']='channel'
    await share(env,request_id)
    assert 'проверить группу' in env.bot.sent[-1].text
    env.group_access['type']='supergroup'
    env.group_access['present']=False
    await share(env,request_id)
    assert 'проверить группу' in env.bot.sent[-1].text
    env.group_access['present']=True
    await share(env,request_id)
    env.group_access['present']=False
    result=await click(env,menu,'Создать алиас')
    assert 'проверить группу' in result.answers[-1][0]
    assert env.m.get_all_aliases(456) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_kind',['command','button','new_menu','expiry'])
async def test_cancelled_or_expired_group_picker_cannot_create_alias(groups,cancel_kind):
    env=groups
    menu,request_id=await group_picker(env)
    if cancel_kind=='command':
        command=Message(env.bot,'/cancel')
        await env.m.settings_cancel_command(update(command),env.context)
    elif cancel_kind=='button':
        await click(env,menu,'Отмена')
    elif cancel_kind=='new_menu':
        await open_menu(env)
    else:
        env.clock['now'] += timedelta(days=2)
    await share(env,request_id)
    assert env.m.get_all_aliases(456) == []
    assert 'уже закрыт' in env.bot.sent[-1].text


@pytest.mark.asyncio
async def test_alias_target_validation_rechecks_session_after_network_await(groups,monkeypatch):
    env=groups
    menu,request_id=await group_picker(env)
    original=env.bot.get_chat

    async def new_session_during_network(chat_id):
        env.store.open(456,456,env.clock['now'])
        return await original(chat_id)

    monkeypatch.setattr(env.bot,'get_chat',new_session_during_network)
    await share(env,request_id)
    assert 'уже закрыт' in env.bot.sent[-1].text
    assert env.m.get_all_aliases(456) == []


def test_alias_store_atomic_create_checks_conflicts_and_rolls_back(env):
    known_user(env)
    store=AliasMenuStore(env.m.DB_PATH)
    target=store.user_target('@natasha')

    def create(_):
        try:
            AliasMenuStore(env.m.DB_PATH).create(456,'Друг','user',target,env.clock['now'])
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(create,range(8))) == 1
    assert len(store.aliases(456)) == 1
    snapshot=store.aliases(456)[0]
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("CREATE TRIGGER fail_alias BEFORE UPDATE ON user_aliases BEGIN SELECT RAISE(ABORT,'write error'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.rename(456,snapshot,'Новое')
    assert store.current(456,snapshot)['alias']=='Друг'


@pytest.mark.parametrize('name',['завтра','every','me','@username','два слова','123','x'*65,'👤Друг','-Друг'])
def test_alias_names_must_be_unambiguous_and_routable(name):
    with pytest.raises(ValueError):
        validate_alias_name(name)


def test_alias_handler_is_registered_for_native_chat_selection():
    from pathlib import Path
    source=Path('main.py').read_text()
    assert 'MessageHandler(filters.StatusUpdate.CHAT_SHARED, settings_chat_shared)' in source


def test_settings_store_rejects_stale_snapshot_without_changing_cancelled_draft(env):
    env.store.open(456,456,env.clock['now'])
    old = env.store.session(456,env.clock['now'])
    newer = env.store.session(456,env.clock['now'])
    newer['data']['page']='aliases'
    newer['data']['cancelled']=True
    assert env.store.save(newer)
    old['data']['page']='alias_confirm'
    old['data']['alias_wizard']={'op':'create'}
    assert env.store.save(old) is False
    current=env.store.session(456,env.clock['now'])
    assert current['data']['page']=='aliases' and current['data']['cancelled']


@pytest.mark.asyncio
async def test_cancel_during_group_keyboard_removal_is_not_overwritten(groups,monkeypatch):
    env=groups
    menu,request_id=await group_picker(env)
    message=Message(env.bot)
    message.chat_shared=SimpleNamespace(request_id=request_id,chat_id=-100)
    original=message.reply_text

    async def cancel_during_reply(text,**kwargs):
        if getattr(kwargs.get('reply_markup'),'remove_keyboard',False):
            cancelled=env.store.session(456,env.clock['now'])
            cancelled['data'].pop('alias_wizard',None)
            cancelled['data']['page']='aliases'
            assert env.store.save(cancelled)
        return await original(text,**kwargs)

    monkeypatch.setattr(message,'reply_text',cancel_during_reply)
    await env.m.settings_chat_shared(update(message),env.context)
    assert env.store.session(456,env.clock['now'])['data']['page']=='aliases'
    assert env.m.get_all_aliases(456)==[]


@pytest.mark.asyncio
async def test_existing_alias_commands_and_menu_edits_are_compatible(env):
    known_user(env)
    env.context.args=['Друг','@natasha']
    await env.m.linkuser_command(update(Message(env.bot,'/linkuser Друг @natasha')),env.context)
    env.context.args=[]
    menu=await aliases_menu(env)
    await click(env,menu,'👤 Друг')
    await click(env,menu,'Переименовать')
    await reply(env,'Коллега')
    await click(env,menu,'Сохранить новое имя')
    env.context.args=['Коллега','->','Напарник']
    await env.m.renamealias_command(update(Message(env.bot,'/renamealias Коллега -> Напарник')),env.context)
    assert env.m.get_user_alias('Напарник',456)['chat_id']==999
    env.context.args=['Напарник']
    await env.m.unalias_command(update(Message(env.bot,'/unalias Напарник')),env.context)
    assert env.m.get_all_user_aliases(456)==[]


@pytest.mark.asyncio
async def test_failed_delete_reports_error_and_does_not_lose_alias(env):
    env.m.set_user_alias('Друг',999,999,'natasha',456)
    menu=await aliases_menu(env)
    await click(env,menu,'👤 Друг')
    await click(env,menu,'Удалить')
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute("CREATE TRIGGER fail_delete_alias BEFORE DELETE ON user_aliases BEGIN SELECT RAISE(ABORT,'write error'); END")
    query=await click(env,menu,'Да, удалить')
    assert 'Не удалось сохранить' in query.answers[-1][0]
    assert env.m.get_user_alias('Друг',456) is not None
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute('DROP TRIGGER fail_delete_alias')
    await click(env,menu,'Да, удалить')
    assert env.m.get_user_alias('Друг',456) is None


@pytest.mark.asyncio
async def test_new_alias_menu_message_remains_working_when_edit_falls_back_to_reply(env,monkeypatch):
    from test_settings_menu_integration import Query
    menu=await aliases_menu(env)
    original=Query.edit_message_text

    async def fail(self,text,**kwargs):
        raise RuntimeError('message to edit not found')

    monkeypatch.setattr(Query,'edit_message_text',fail)
    await click(env,menu,'Добавить алиас')
    replacement=env.bot.sent[-1]
    assert replacement.message_id != menu.message_id
    monkeypatch.setattr(Query,'edit_message_text',original)
    await click(env,replacement,'Человек')
    assert 'Отправь название алиаса' in replacement.text
    assert env.store.session(456,env.clock['now'])['message_id']==replacement.message_id


@pytest.mark.asyncio
async def test_alias_list_groups_chats_before_people_and_sorts_names_without_case(env):
    for name in ['Юлия', 'борис', 'Анна']:
        env.m.set_user_alias(name, 999, 999, 'natasha', 456)
    for name in ['Работа', 'ёжик', 'Дом', 'Журнал']:
        env.m.set_chat_alias(name, -100, 'Chat', 456)
    menu = await aliases_menu(env)
    buttons = [b for row in menu.reply_markup.inline_keyboard for b in row]
    assert [b.text for b in buttons if 'a_open:' in b.callback_data] == [
        '💬 Дом', '💬 ёжик', '💬 Журнал', '💬 Работа', '👤 Анна', '👤 борис', '👤 Юлия',
    ]
    assert [b.text for b in buttons[:6]] == [
        '— 💬 Каналы и группы —', '💬 Дом', '💬 ёжик', '💬 Журнал', '💬 Работа', '— 👤 Люди —',
    ]
    snapshot = env.store.session(456, env.clock['now'])
    q = await click(env, menu, '— 👤 Люди —')
    assert q.answers and not q.answers[0][1].get('show_alert')
    assert env.store.session(456, env.clock['now']) == snapshot
    await click(env, menu, '👤 Анна')
    assert 'Анна' in menu.text and '@natasha' in menu.text


@pytest.mark.asyncio
@pytest.mark.parametrize('chat_count', [0, 7, 8, 9])
async def test_alias_section_headers_repeat_on_pages_without_using_alias_slots(env, chat_count):
    for i in range(chat_count):
        env.m.set_chat_alias(f'Канал{i:02d}', -100-i, 'Chat', 456)
    for i in range(10):
        env.m.set_user_alias(f'Алиса{i:02d}', 999, 999, 'natasha', 456)
    expected = [('chat', f'Канал{i:02d}') for i in range(chat_count)] + [('user', f'Алиса{i:02d}') for i in range(10)]
    menu = await aliases_menu(env)
    pages = (len(expected)+7)//8
    for page in range(pages):
        items = expected[page*8:(page+1)*8]
        buttons = [b for row in menu.reply_markup.inline_keyboard for b in row]
        actual = [b.text for b in buttons if 'a_open:' in b.callback_data]
        assert actual == [('💬 ' if kind == 'chat' else '👤 ') + name for kind, name in items]
        headers = [b.text for b in buttons if 'a_section:' in b.callback_data]
        assert headers == [label for kind, label in [('chat', '— 💬 Каналы и группы —'), ('user', '— 👤 Люди —')] if any(k == kind for k, _ in items)]
        assert all(len(b.callback_data.encode()) <= 64 for b in buttons)
        if page+1 < pages:
            await click(env, menu, '→')
    if pages > 1:
        await click(env, menu, '←')
        assert f'Страница {pages-1} из {pages}' in menu.text


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,target', [('user', 999), ('chat', -100)])
async def test_alias_reminders_show_only_owner_pending_for_exact_recipient(env, kind, target):
    if kind == 'user':
        env.m.set_user_alias('Получатель', target, target, 'natasha', 456)
    else:
        env.m.set_chat_alias('Получатель', target, 'Chat', 456)
    wanted = env.m.add_reminder(target, 'Моё активное', env.clock['now'], 456)
    env.m.add_reminder(target, 'Чужое секретное', env.clock['now'], 777)
    env.m.add_reminder(target+1, 'Другому адресату', env.clock['now'], 456)
    sent = env.m.add_reminder(target, 'Уже доставленное', env.clock['now'], 456)
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute('UPDATE reminders SET delivered=1 WHERE id=?', (sent,))
    env.context.user_data['list_ids'] = [12345]
    menu = await aliases_menu(env)
    await click(env, menu, 'Получатель')
    await click(env, menu, 'Напоминания для этого алиаса')
    assert 'Моё активное' in menu.text and 'всего 1' in menu.text
    assert all(text not in menu.text for text in ['Чужое секретное', 'Другому адресату', 'Уже доставленное'])
    assert env.context.user_data['list_ids'] == [12345]
    assert env.m.get_reminder(wanted).chat_id == target
    await click(env, menu, 'К алиасу')
    assert 'Куда:' in menu.text
    await click(env, menu, 'К списку алиасов')
    assert 'Мои алиасы' in menu.text


@pytest.mark.asyncio
async def test_alias_reminders_empty_and_refresh_after_new_reminder(env):
    env.m.set_chat_alias('Работа', -100, 'Work', 456)
    menu = await aliases_menu(env)
    await click(env, menu, 'Работа')
    await click(env, menu, 'Напоминания для этого алиаса')
    assert 'пока нет' in menu.text and 'всего 0' in menu.text
    env.m.add_reminder(-100, 'Появилось новое', env.clock['now'], 456)
    await click(env, menu, 'Обновить')
    assert 'Появилось новое' in menu.text and 'всего 1' in menu.text


@pytest.mark.asyncio
async def test_alias_reminders_pagination_refresh_clamps_and_survives_restart(env):
    env.m.set_user_alias('Друг', 999, 999, 'natasha', 456)
    for i in reversed(range(22)):
        env.m.add_reminder(999, f'Задача{i:02d}', env.clock['now']+timedelta(minutes=i), 456)
    menu = await aliases_menu(env)
    await click(env, menu, 'Друг')
    await click(env, menu, 'Напоминания для этого алиаса')
    assert 'Страница 1 из 3' in menu.text
    assert menu.text.index('Задача00') < menu.text.index('Задача09')
    assert 'Задача10' not in menu.text
    old_next = button_data(menu, '→')
    env.context.user_data.clear()
    env.m.init_db()
    await click(env, menu, data=old_next)
    assert 'Страница 2 из 3' in menu.text and 'Задача10' in menu.text
    stale = await click(env, menu, data=old_next)
    assert stale.answers[0][1].get('show_alert')
    await click(env, menu, '→')
    assert 'Задача20' in menu.text and 'Задача21' in menu.text
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute('DELETE FROM reminders WHERE text >= ?', ('Задача08',))
    await click(env, menu, 'Обновить')
    assert 'Страница 1 из 1' in menu.text and 'всего 8' in menu.text
    with sqlite3.connect(env.m.DB_PATH) as conn:
        conn.execute('UPDATE reminders SET delivered=1')
    await click(env, menu, 'Обновить')
    assert 'пока нет' in menu.text


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['rename', 'delete', 'retarget'])
async def test_alias_reminder_button_rejects_alias_changed_by_legacy_commands(env, change):
    env.m.set_chat_alias('Работа', -100, 'Work', 456)
    env.m.add_reminder(-200, 'Новый закрытый адресат', env.clock['now'], 456)
    menu = await aliases_menu(env)
    await click(env, menu, 'Работа')
    callback = button_data(menu, 'Напоминания для этого алиаса')
    with sqlite3.connect(env.m.DB_PATH) as conn:
        if change == 'rename':
            conn.execute("UPDATE chat_aliases SET alias='Офис' WHERE created_by=456")
        elif change == 'delete':
            conn.execute('DELETE FROM chat_aliases WHERE created_by=456')
        else:
            conn.execute('UPDATE chat_aliases SET chat_id=-200 WHERE created_by=456')
    result = await click(env, menu, data=callback)
    assert result.answers[0][1].get('show_alert')
    assert 'изменён или удалён' in result.answers[0][0]
    assert 'Новый закрытый адресат' not in menu.text
    assert 'Мои алиасы' in menu.text


@pytest.mark.asyncio
async def test_alias_reminders_follow_recipient_after_rename_and_include_recurring(env):
    env.m.set_user_alias('Старое', 999, 999, 'natasha', 456)
    tpl = env.m.create_recurring_template(999, 'Полить цветы', 'daily', {}, 12, 0, 456)
    rid = env.m.add_reminder(999, 'Полить цветы', env.clock['now'], 456, template_id=tpl)
    selected = AliasMenuStore(env.m.DB_PATH).aliases(456)[0]
    AliasMenuStore(env.m.DB_PATH).rename(456, selected, 'Новое')
    menu = await aliases_menu(env)
    await click(env, menu, 'Новое')
    await click(env, menu, 'Напоминания для этого алиаса')
    assert '«Новое»' in menu.text and 'Полить цветы' in menu.text and '🔁' in menu.text
    assert env.m.get_reminder(rid).chat_id == 999


@pytest.mark.asyncio
async def test_alias_reminders_access_and_telegram_message_limits(env):
    env.m.set_user_alias('Я'*160, 999, 999, 'natasha', 456)
    for i in range(11):
        env.m.add_reminder(999, f'{i:02d}'+ '🌻'*300, env.clock['now'], 456)
    menu = await aliases_menu(env)
    await click(env, menu, '👤 Я')
    callback = button_data(menu, 'Напоминания для этого алиаса')
    rejected = await click(env, menu, data=callback, actor=777)
    assert rejected.answers[0][1].get('show_alert')
    await click(env, menu, data=callback)
    assert len(menu.text.encode('utf-16-le'))//2 < 4096
    assert all(len(b.callback_data.encode()) <= 64 for row in menu.reply_markup.inline_keyboard for b in row)
    env.clock['now'] += timedelta(days=2)
    expired = await click(env, menu, 'Обновить')
    assert expired.answers[0][1].get('show_alert')
