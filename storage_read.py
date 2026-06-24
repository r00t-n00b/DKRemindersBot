"""Read-only storage helpers for reminders and recurring templates."""



from datetime import datetime

from typing import Any, Dict, List, Optional



from models import Reminder





_DEP_NAMES = (

    "DB_PATH",

    "json",

    "sqlite3",

)





def _apply_deps(deps) -> None:

    for name in _DEP_NAMES:

        globals()[name] = getattr(deps, name)



def get_due_reminders_impl(now: datetime, deps) -> List[Reminder]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, remind_at, created_by, template_id
        FROM reminders
        WHERE delivered = 0 AND remind_at <= ?
        ORDER BY remind_at ASC
        """,
        (now.isoformat(),),
    )
    rows = c.fetchall()
    conn.close()
    reminders: List[Reminder] = []
    for row in rows:
        rid, chat_id, text, remind_at_str, created_by, template_id = row
        reminders.append(
            Reminder(
                id=rid,
                chat_id=chat_id,
                text=text,
                remind_at=datetime.fromisoformat(remind_at_str),
                created_by=created_by,
                template_id=template_id,
            )
        )
    return reminders



def get_reminder_impl(reminder_id: int, deps) -> Optional[Reminder]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, remind_at, created_by, template_id, sent_at
        FROM reminders
        WHERE id = ?
        """,
        (reminder_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None

    rid, chat_id, text, remind_at_str, created_by, template_id, sent_at_str = row
    sent_at = datetime.fromisoformat(sent_at_str) if sent_at_str else None

    return Reminder(
        id=rid,
        chat_id=chat_id,
        text=text,
        remind_at=datetime.fromisoformat(remind_at_str),
        created_by=created_by,
        template_id=template_id,
        sent_at=sent_at,
    )



def get_active_reminders_created_by_for_chat_impl(chat_id: int, created_by: int, deps) -> List[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, remind_at, delivered, created_by, template_id
            FROM reminders
            WHERE chat_id = ?
              AND delivered = 0
              AND created_by = ?
            ORDER BY remind_at ASC
            """,
            (chat_id, created_by),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()



def get_active_reminders_for_chat_impl(chat_id: int, deps) -> List[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, remind_at, created_by, created_at, delivered, template_id
            FROM reminders
            WHERE chat_id = ? AND delivered = 0
            ORDER BY remind_at ASC
            """,
            (chat_id,),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()



def get_reminder_row_impl(rid: int, deps) -> Optional[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, remind_at, delivered, created_by, template_id
            FROM reminders
            WHERE id = ?
            """,
            (rid,),
        )
        row = c.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()



def get_recurring_template_row_impl(tpl_id: int, deps) -> Optional[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, created_at, active
            FROM recurring_templates
            WHERE id = ?
            """,
            (tpl_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        d = dict(row)
        # payload в базе у нас JSON-строка
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except Exception:
            d["payload"] = {}
        return d
    finally:
        conn.close()



def get_reminders_by_template_id_impl(template_id: int, chat_id: int, deps) -> List[Dict[str, Any]]:
    _apply_deps(deps)
    """
    Возвращает reminders этой серии (для snapshot при удалении серии).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, chat_id, text, remind_at, created_by, created_at, delivered, template_id
            FROM reminders
            WHERE chat_id = ? AND template_id = ?
            ORDER BY remind_at ASC
            """,
            (chat_id, template_id),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()



def get_unacked_sent_before_impl(dt: datetime, deps) -> List[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, sent_at
        FROM reminders
        WHERE delivered = 1
          AND acked = 0
          AND nudge_sent = 0
          AND sent_at IS NOT NULL
          AND sent_at <= ?
        ORDER BY sent_at ASC
        """,
        (dt.isoformat(),),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows



def get_recurring_template_impl(template_id: int, deps) -> Optional[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, active
        FROM recurring_templates
        WHERE id = ?
        """,
        (template_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    (
        tpl_id,
        chat_id,
        text,
        pattern_type,
        payload_json,
        time_hour,
        time_minute,
        created_by,
        active,
    ) = row
    try:
        payload = json.loads(payload_json) if payload_json else {}
    except Exception:
        payload = {}
    return {
        "id": tpl_id,
        "chat_id": chat_id,
        "text": text,
        "pattern_type": pattern_type,
        "payload": payload,
        "time_hour": time_hour,
        "time_minute": time_minute,
        "created_by": created_by,
        "active": bool(active),
    }
