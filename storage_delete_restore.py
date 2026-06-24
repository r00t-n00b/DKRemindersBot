"""Delete/restore storage helpers.

This module intentionally preserves the SQL and behavior from main.py.
It does not own schema creation or migrations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


_DEP_NAMES = (
    "DB_PATH",
    "add_reminder",
    "compute_next_occurrence",
    "get_recurring_template_row",
    "get_reminder_row",
    "get_reminders_by_template_id",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def delete_reminders_impl(reminder_ids: List[int], chat_id: int, *, deps) -> int:
    _apply_deps(deps)
    '\n    Удаляем напоминания. Если у них был template_id - деактивируем соответствующие шаблоны\n    (то есть удаление повторяющегося напоминания останавливает всю серию).\n    '
    if not reminder_ids:
        return 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    qmarks = ','.join(('?' for _ in reminder_ids))
    params = reminder_ids + [chat_id]
    c.execute(f'SELECT DISTINCT template_id FROM reminders WHERE id IN ({qmarks}) AND chat_id = ?', params)
    template_rows = c.fetchall()
    template_ids = [row[0] for row in template_rows if row[0] is not None]
    c.execute(f'DELETE FROM reminders WHERE id IN ({qmarks}) AND chat_id = ?', params)
    deleted = c.rowcount
    if template_ids:
        q2 = ','.join(('?' for _ in template_ids))
        c.execute(f'UPDATE recurring_templates SET active = 0 WHERE id IN ({q2})', template_ids)
    conn.commit()
    conn.close()
    return deleted


def delete_recurring_one_instance_and_reschedule_impl(rid: int, chat_id: int, *, deps) -> Optional[Dict[str, Any]]:
    _apply_deps(deps)
    '\n    Удаляет ОДИН инстанс recurring-ремайндера и сразу создает следующий инстанс,\n    не выключая серию.\n\n    Возвращает snapshot для undo.\n    Backward-compatible поля:\n      - mode="one" (старые тесты)\n      - kind="single" (новый общий undo)\n    '
    r = get_reminder_row(rid)
    if not r:
        return None
    if int(r['chat_id']) != int(chat_id):
        return None
    tpl_id = r.get('template_id')
    if tpl_id is None:
        return None
    tpl = get_recurring_template_row(int(tpl_id))
    if not tpl:
        return None
    if not tpl.get('active'):
        return None
    deleted = delete_single_reminder_row_impl(int(rid), int(chat_id), deps=deps)
    if not deleted:
        return None
    snapshot: Dict[str, Any] = {'mode': 'one', 'kind': 'single', 'reminder': r, 'template': tpl, 'next_created_id': None}
    try:
        last_dt = datetime.fromisoformat(str(r['remind_at']))
    except Exception:
        return snapshot
    pattern_type = str(tpl['pattern_type'])
    payload = tpl.get('payload') or {}
    time_hour = int(tpl['time_hour'])
    time_minute = int(tpl['time_minute'])
    next_dt = compute_next_occurrence(pattern_type, dict(payload), time_hour, time_minute, last_dt)
    if next_dt is not None:
        next_id = add_reminder(chat_id=int(r['chat_id']), text=str(r['text']), remind_at=next_dt, created_by=r.get('created_by'), template_id=int(tpl['id']))
        snapshot['next_created_id'] = int(next_id)
    return snapshot


def delete_single_reminder_row_impl(reminder_id: int, chat_id: int, *, deps) -> int:
    _apply_deps(deps)
    '\n    Удаляет ОДИН reminder, не трогая recurring_templates.\n    Возвращает количество удаленных строк (0 или 1).\n    '
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM reminders WHERE id = ? AND chat_id = ?', (reminder_id, chat_id))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted


def deactivate_recurring_template_impl(template_id: int, *, deps) -> int:
    _apply_deps(deps)
    '\n    Ставит active=0 у recurring_templates. Возвращает количество обновленных строк (0 или 1).\n    '
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE recurring_templates SET active = 0 WHERE id = ?', (template_id,))
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated


def activate_recurring_template_impl(template_id: int, *, deps) -> int:
    _apply_deps(deps)
    '\n    Ставит active=1 у recurring_templates. Возвращает количество обновленных строк (0 или 1).\n    '
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE recurring_templates SET active = 1 WHERE id = ?', (template_id,))
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated


def delete_recurring_series_impl(template_id: int, chat_id: int, *, deps) -> int:
    _apply_deps(deps)
    '\n    Удаляет все reminders серии (template_id) и деактивирует recurring_templates.active=0.\n    Возвращает количество удаленных reminders.\n    '
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM reminders WHERE chat_id = ? AND template_id = ?', (chat_id, template_id))
    deleted = c.rowcount
    c.execute('UPDATE recurring_templates SET active = 0 WHERE id = ?', (template_id,))
    conn.commit()
    conn.close()
    return deleted


def delete_reminder_with_snapshot_impl(rid: int, target_chat_id: int, *, deps) -> Optional[Dict[str, Any]]:
    _apply_deps(deps)
    '\n    Backward-compatible: удаляет один reminder и возвращает snapshot.\n    ВАЖНО: теперь это "single delete" и НЕ останавливает серию.\n    '
    return delete_single_reminder_with_snapshot_impl(rid, target_chat_id, deps=deps)


def delete_single_reminder_with_snapshot_impl(rid: int, target_chat_id: int, *, deps) -> Optional[Dict[str, Any]]:
    _apply_deps(deps)
    '\n    Удаляет один reminder и возвращает snapshot для undo.\n    Если reminder был recurring (template_id != None), шаблон НЕ деактивируем.\n    '
    r = get_reminder_row(rid)
    if not r:
        return None
    if int(r['chat_id']) != int(target_chat_id):
        return None
    tpl = None
    tpl_id = r.get('template_id')
    if tpl_id is not None:
        tpl = get_recurring_template_row(int(tpl_id))
    deleted = delete_single_reminder_row_impl(rid, target_chat_id, deps=deps)
    if not deleted:
        return None
    return {'kind': 'single', 'reminder': r, 'template': tpl}


def delete_recurring_series_with_snapshot_impl(template_id: int, target_chat_id: int, *, deps) -> Optional[Dict[str, Any]]:
    _apply_deps(deps)
    '\n    Удаляет всю серию и возвращает snapshot для undo:\n    - template (как есть, с этим же id)\n    - список reminders, которые были удалены\n    '
    tpl = get_recurring_template_row(int(template_id))
    if not tpl:
        return None
    if int(tpl['chat_id']) != int(target_chat_id):
        return None
    reminders = get_reminders_by_template_id(int(template_id), int(target_chat_id))
    if not reminders:
        deactivate_recurring_template_impl(int(template_id), deps=deps)
        return {'kind': 'series', 'template': tpl, 'reminders': []}
    deleted = delete_recurring_series_impl(int(template_id), int(target_chat_id), deps=deps)
    if deleted <= 0:
        return None
    return {'kind': 'series', 'template': tpl, 'reminders': reminders}


def restore_deleted_snapshot_impl(snapshot: Dict[str, Any], *, deps) -> Optional[Any]:
    _apply_deps(deps)
    '\n    Восстанавливает удаленный reminder или серию.\n    Возвращает:\n    - для single: новый reminder_id (int)\n    - для series: список новых reminder_id (List[int])\n    '
    kind = snapshot.get('kind') or 'single'
    if kind == 'single':
        r = snapshot.get('reminder') or {}
        if not r:
            return None
        next_id = snapshot.get('next_created_id')
        if next_id:
            delete_single_reminder_row_impl(int(next_id), int(r['chat_id']), deps=deps)
        tpl = snapshot.get('template')
        tpl_id = None
        if tpl and tpl.get('id') is not None:
            activate_recurring_template_impl(int(tpl['id']), deps=deps)
            tpl_id = int(tpl['id'])
        remind_at = datetime.fromisoformat(str(r['remind_at']))
        new_rid = add_reminder(chat_id=int(r['chat_id']), text=str(r['text']), remind_at=remind_at, created_by=r.get('created_by'), template_id=tpl_id)
        return new_rid
    if kind == 'series':
        tpl = snapshot.get('template') or {}
        tpl_id = tpl.get('id')
        if tpl_id is None:
            return None
        activate_recurring_template_impl(int(tpl_id), deps=deps)
        new_ids: List[int] = []
        for r in snapshot.get('reminders') or []:
            remind_at = datetime.fromisoformat(str(r['remind_at']))
            new_id = add_reminder(chat_id=int(r['chat_id']), text=str(r['text']), remind_at=remind_at, created_by=r.get('created_by'), template_id=int(tpl_id))
            new_ids.append(int(new_id))
        return new_ids
    return None
