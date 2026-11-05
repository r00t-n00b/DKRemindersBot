"""Read-only, creator-scoped inspection of recent reminders."""

from contextlib import closing
from pathlib import Path
import re
import sqlite3

from dkreminders_bot.domain.alias_names import alias_key
from dkreminders_bot.ui.messages import DIAGNOSTICS_NOTICES as N


class ReminderDiagnosticsStore:
    def __init__(self, db_path):
        self.db_path = db_path

    def recent(self, owner, target=None):
        # mode=ro prevents accidental writes and creation of a missing database.
        uri = Path(self.db_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            target_chat = None
            if target:
                if target.startswith("@"):
                    if not re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{0,31}", target):
                        raise ValueError(N["unknown_target"])
                    row = conn.execute("""SELECT chat_id FROM user_chats
                        WHERE LOWER(username)=? AND user_id=chat_id AND chat_id>0
                        ORDER BY updated_at DESC LIMIT 1""", (target[1:].lower(),)).fetchone()
                    if row is None:
                        raise ValueError(N["unknown_target"])
                    target_chat = row[0]
                else:
                    aliases = conn.execute("""SELECT alias,chat_id FROM user_aliases WHERE created_by=?
                        UNION ALL SELECT alias,chat_id FROM chat_aliases WHERE created_by=?""", (owner, owner)).fetchall()
                    targets = {row["chat_id"] for row in aliases if alias_key(row["alias"]) == alias_key(target)}
                    if not targets:
                        raise ValueError(N["unknown_target"])
                    if len(targets) != 1:
                        raise ValueError(N["ambiguous_target"])
                    target_chat = targets.pop()
            condition = "r.created_by=?"
            params = [owner]
            if target_chat is not None:
                condition += " AND r.chat_id=?"
                params.append(target_chat)
            rows = conn.execute(f"""SELECT r.* FROM reminders r
                WHERE {condition} ORDER BY r.id DESC LIMIT 20""", params).fetchall()
            if not rows:
                return []
            ids = [row["id"] for row in rows]
            counts = conn.execute(f"""SELECT reminder_id,kind,COUNT(*) AS count
                FROM reminder_messages WHERE reminder_id IN ({','.join('?' for _ in ids)})
                GROUP BY reminder_id,kind""", ids).fetchall()
            tracked = {}
            for row in counts:
                tracked.setdefault(row["reminder_id"], {})[row["kind"]] = row["count"]
            return [{**dict(row), "tracked": tracked.get(row["id"], {})} for row in rows]
