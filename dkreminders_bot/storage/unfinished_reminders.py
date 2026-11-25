"""Paged unfinished reminders visible to their creator or private recipient."""

from contextlib import closing
from pathlib import Path
import sqlite3

PAGE_SIZE = 8


class UnfinishedRemindersStore:
    def __init__(self, db_path):
        self.db_path = db_path

    def page(self, user_id, number=0):
        uri = Path(self.db_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            scope = "r.delivered=1 AND r.acked=0 AND (r.chat_id=? OR r.created_by=?)"
            params = (user_id, user_id)
            total = conn.execute(
                f"SELECT COUNT(*) FROM reminders r WHERE {scope}", params,
            ).fetchone()[0]
            pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            number = max(0, min(number, pages - 1))
            rows = conn.execute(f"""
                SELECT r.id,r.text,r.chat_id,r.remind_at,r.template_id,
                    COALESCE(r.timezone_name,rt.timezone_name) AS timezone_name,
                    COALESCE(
                        (SELECT alias FROM user_aliases WHERE created_by=? AND chat_id=r.chat_id
                         ORDER BY alias LIMIT 1),
                        (SELECT alias FROM chat_aliases WHERE created_by=? AND chat_id=r.chat_id
                         ORDER BY alias LIMIT 1)
                    ) AS target_alias
                FROM reminders r
                LEFT JOIN recurring_templates rt ON rt.id=r.template_id
                WHERE {scope}
                ORDER BY julianday(r.remind_at),r.id
                LIMIT ? OFFSET ?
            """, (user_id, user_id, *params, PAGE_SIZE, number * PAGE_SIZE)).fetchall()
            return [dict(row) for row in rows], number, pages, total
