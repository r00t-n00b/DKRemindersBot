"""Transactional creation choices and completion-based series transitions.

No Telegram calls run inside a transaction. Acknowledging the old reminder and
creating its successor commit together, including across duplicate callbacks.
"""

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timedelta

from dkreminders_bot.domain.recurrence import is_completion_based, next_after_completion
from dkreminders_bot.utils.time_utils import to_iso


class RecurrenceStore:
    def __init__(self, db_path):
        self.db_path = db_path

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_choice(self, spec, now):
        token = uuid.uuid4().hex
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO recurrence_choices(token, spec, expires_at) VALUES (?, ?, ?)",
                (token, json.dumps(spec, ensure_ascii=False), to_iso(now + timedelta(days=1))),
            )
        return token

    @staticmethod
    def _insert_reminder(conn, spec, template_id, when, now):
        values = {
            "chat_id": spec["chat_id"], "text": spec["text"],
            "remind_at": to_iso(when), "created_by": spec["created_by"],
            "created_at": to_iso(now), "template_id": template_id,
            "timezone_name": spec.get("timezone_name"),
            "source_chat_id": spec.get("source_chat_id"),
            "source_message_id": spec.get("source_message_id"),
        }
        return conn.execute(
            f"INSERT INTO reminders({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        ).lastrowid

    def choose(self, token, mode, actor_id, origin_chat_id, now):
        if mode not in {"schedule", "completion", "cancel"}:
            return {"status": "invalid"}
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM recurrence_choices WHERE token = ?", (token,)).fetchone()
            if row is None:
                return {"status": "expired"}
            spec = json.loads(row["spec"])
            if actor_id != spec["created_by"] or origin_chat_id != spec["origin_chat_id"]:
                return {"status": "forbidden"}
            if row["chosen_mode"] is not None:
                return {"status": "processed"}
            if datetime.fromisoformat(row["expires_at"]).timestamp() <= now.timestamp():
                return {"status": "expired"}
            if mode == "cancel":
                conn.execute("UPDATE recurrence_choices SET chosen_mode = ? WHERE token = ?", (mode, token))
                return {"status": "cancelled"}
            payload = {**spec["payload"], "recurrence_mode": mode}
            first_dt = datetime.fromisoformat(spec["first_dt"])
            if first_dt.timestamp() <= now.timestamp():
                # A delayed choice must not create a reminder in the past.
                first_dt = next_after_completion(payload, now, spec["timezone_name"])
                if mode == "schedule" and payload["unit"] in {"days", "weeks", "months"}:
                    first_dt = first_dt.replace(hour=spec["time_hour"], minute=spec["time_minute"], second=0, microsecond=0)
                    if first_dt.timestamp() <= now.timestamp():
                        first_dt = next_after_completion(payload, first_dt, spec["timezone_name"])
            tpl_id = conn.execute(
                """INSERT INTO recurring_templates
                (chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, created_at, active, timezone_name)
                VALUES (?, ?, 'interval', ?, ?, ?, ?, ?, 1, ?)""",
                (spec["chat_id"], spec["text"], json.dumps(payload, ensure_ascii=False),
                 spec["time_hour"], spec["time_minute"], spec["created_by"], to_iso(now), spec["timezone_name"]),
            ).lastrowid
            rid = self._insert_reminder(conn, spec, tpl_id, first_dt, now)
            conn.execute(
                "UPDATE recurrence_choices SET chosen_mode = ?, reminder_id = ? WHERE token = ?",
                (mode, rid, token),
            )
            return {"status": "created", "reminder_id": rid, "first_dt": first_dt, "spec": spec, "payload": payload}

    def completion_reminder(self, reminder_id):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT r.*, t.pattern_type, t.payload, t.active,
                t.timezone_name AS series_timezone
                FROM reminders r JOIN recurring_templates t ON t.id = r.template_id WHERE r.id = ?""",
                (reminder_id,),
            ).fetchone()
            if row is not None and is_completion_based(row["pattern_type"], json.loads(row["payload"])):
                return dict(row)
        return None

    def transition(self, reminder_id, *, actor_id, chat_id, now, snooze_until=None):
        with self.transaction() as conn:
            row = conn.execute(
                """SELECT r.*, t.pattern_type, t.payload, t.active,
                t.timezone_name AS series_timezone
                FROM reminders r JOIN recurring_templates t ON t.id = r.template_id WHERE r.id = ?""",
                (reminder_id,),
            ).fetchone()
            if row is None:
                return {"status": "processed"}
            r = dict(row)
            payload = json.loads(r["payload"])
            if not is_completion_based(r["pattern_type"], payload):
                return {"status": "legacy"}
            # In a private destination the recipient acts; in a group, the creator.
            owner = r["chat_id"] if r["chat_id"] > 0 else r["created_by"]
            if actor_id != owner or chat_id != r["chat_id"]:
                return {"status": "forbidden"}
            if r["acked"] or not r["delivered"] or not r["active"]:
                return {"status": "processed"}
            when = snooze_until if snooze_until is not None else next_after_completion(payload, now, r["series_timezone"])
            if when.timestamp() <= now.timestamp():
                return {"status": "past"}
            # Prevent another open occurrence even if old data is inconsistent.
            other = conn.execute(
                "SELECT 1 FROM reminders WHERE template_id = ? AND acked = 0 AND id != ?",
                (r["template_id"], reminder_id),
            ).fetchone()
            if other:
                return {"status": "processed"}
            conn.execute("UPDATE reminders SET acked = 1 WHERE id = ? AND acked = 0", (reminder_id,))
            r["timezone_name"] = r["series_timezone"] or r["timezone_name"]
            rid = self._insert_reminder(conn, r, r["template_id"], when, now)
            return {"status": "applied", "reminder_id": rid, "next_at": when}

    def skip(self, reminder_id, chat_id, now):
        """Explicitly skipping an occurrence starts one interval from the skip."""
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM reminders WHERE id = ? AND chat_id = ?", (reminder_id, chat_id)).fetchone()
            if row is None or row["acked"]:
                return None
            r = dict(row)
            template = conn.execute("SELECT * FROM recurring_templates WHERE id = ?", (r["template_id"],)).fetchone()
            if template is None or not template["active"]:
                return None
            tpl = dict(template)
            tpl["payload"] = json.loads(tpl["payload"])
            if not is_completion_based(tpl["pattern_type"], tpl["payload"]):
                return None
            other = conn.execute("SELECT 1 FROM reminders WHERE template_id = ? AND acked = 0 AND id != ?", (tpl["id"], reminder_id)).fetchone()
            if other:
                return None
            when = next_after_completion(tpl["payload"], now, tpl.get("timezone_name"))
            conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            spec = {**r, "timezone_name": tpl.get("timezone_name") or r.get("timezone_name")}
            new_id = self._insert_reminder(conn, spec, tpl["id"], when, now)
            return {"mode": "one", "kind": "single", "reminder": r, "template": tpl, "next_created_id": new_id}

    def delete_series(self, template_id, chat_id):
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM recurring_templates WHERE id = ? AND chat_id = ?", (template_id, chat_id)).fetchone()
            if row is None:
                return None
            tpl = dict(row)
            tpl["payload"] = json.loads(tpl["payload"])
            reminders = [dict(r) for r in conn.execute("SELECT * FROM reminders WHERE template_id = ? AND chat_id = ?", (template_id, chat_id))]
            conn.execute("UPDATE recurring_templates SET active = 0 WHERE id = ?", (template_id,))
            conn.execute("DELETE FROM reminders WHERE template_id = ? AND chat_id = ?", (template_id, chat_id))
            return {"kind": "series", "template": tpl, "reminders": reminders}

    def restore_series(self, snapshot, now):
        tpl = snapshot["template"]
        with self.transaction() as conn:
            row = conn.execute("SELECT active FROM recurring_templates WHERE id = ?", (tpl["id"],)).fetchone()
            if row is None or row["active"]:
                return None
            conn.execute("UPDATE recurring_templates SET active = 1 WHERE id = ?", (tpl["id"],))
            ids = []
            for r in snapshot["reminders"]:
                rid = self._insert_reminder(conn, r, tpl["id"], datetime.fromisoformat(r["remind_at"]), now)
                if r["acked"]:
                    # Completed history must never become pending deliveries.
                    conn.execute("UPDATE reminders SET delivered = 1, acked = 1, delivery_state = 'sent' WHERE id = ?", (rid,))
                ids.append(rid)
            return ids
