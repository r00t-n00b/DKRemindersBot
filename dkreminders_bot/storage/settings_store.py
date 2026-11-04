"""Per-recipient nudge preferences and restart-safe settings sessions."""

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from dkreminders_bot.domain.nudge_policy import DEFAULT_GAPS, decode_gaps, validate_gaps
from dkreminders_bot.utils.time_utils import to_iso


def nudge_settings(conn, user_id):
    result = {"enabled": True, "gaps": list(DEFAULT_GAPS), "resume_after": None}
    cols = {r[1] for r in conn.execute("PRAGMA table_info(user_settings)")}
    if not {"nudge_enabled", "nudge_intervals_json", "nudge_resume_after"} <= cols:
        return result
    row = conn.execute("SELECT nudge_enabled, nudge_intervals_json, nudge_resume_after FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        result["enabled"] = bool(row[0])
        result["resume_after"] = row[2]
        if row[1] is not None:
            try:
                result["gaps"] = decode_gaps(row[1])
            except (ValueError, TypeError):
                pass
    return result


class SettingsStore:
    def __init__(self, db_path):
        self.db_path = db_path

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def nudges(self, user_id):
        with self.connection() as conn:
            return nudge_settings(conn, user_id)

    def set_gaps(self, user_id, gaps, now):
        gaps = validate_gaps(gaps)
        with self.connection() as conn:
            conn.execute("""INSERT INTO user_settings(user_id, updated_at, nudge_intervals_json) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET updated_at=excluded.updated_at, nudge_intervals_json=excluded.nudge_intervals_json""", (user_id, to_iso(now), json.dumps(gaps)))

    def set_enabled(self, user_id, enabled, now):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = nudge_settings(conn, user_id)
            resume = to_iso(now) if enabled and not previous["enabled"] else previous["resume_after"]
            conn.execute("""INSERT INTO user_settings(user_id, updated_at, nudge_enabled, nudge_resume_after) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET updated_at=excluded.updated_at, nudge_enabled=excluded.nudge_enabled, nudge_resume_after=excluded.nudge_resume_after""", (user_id, to_iso(now), int(enabled), resume))

    def open(self, user_id, chat_id, now):
        token = secrets.token_hex(8)
        with self.connection() as conn:
            previous = conn.execute("SELECT data FROM settings_sessions WHERE user_id=?", (user_id,)).fetchone()
            prompts = json.loads(previous[0]).get("prompts", []) if previous else []
            data = json.dumps({"page": "home", "prompts": prompts[-20:]})
            conn.execute("""INSERT INTO settings_sessions(user_id, token, chat_id, data, expires_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET token=excluded.token, chat_id=excluded.chat_id, message_id=NULL, prompt_message_id=NULL, data=excluded.data, expires_at=excluded.expires_at""", (user_id, token, chat_id, data, to_iso(now + timedelta(days=1))))
        return self.session(user_id, now)

    def session(self, user_id, now, *, include_expired=False):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM settings_sessions WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        if not include_expired and datetime.fromisoformat(result["expires_at"]).timestamp() <= now.timestamp():
            return None
        result["_snapshot"] = (result["data"], result["message_id"], result["prompt_message_id"])
        result["data"] = json.loads(result["data"])
        return result

    def save(self, session):
        # Compare the complete previous UI state as well as the session token.
        # An async Telegram response must not overwrite a newer cancellation.
        previous = session.get("_snapshot")
        if previous is None:
            return False
        serialized = json.dumps(session["data"], ensure_ascii=False)
        with self.connection() as conn:
            updated = conn.execute("""UPDATE settings_sessions SET data=?, message_id=?, prompt_message_id=?
                WHERE user_id=? AND token=? AND data=? AND message_id IS ? AND prompt_message_id IS ?""",
                (serialized, session["message_id"], session["prompt_message_id"], session["user_id"], session["token"], *previous)).rowcount
        if updated:
            session["_snapshot"] = (serialized, session["message_id"], session["prompt_message_id"])
        return bool(updated)
