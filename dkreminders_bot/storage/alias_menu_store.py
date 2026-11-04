"""Owner-scoped, non-overwriting alias edits with optimistic target checks."""

import re
import sqlite3
from contextlib import contextmanager

from dkreminders_bot.domain.alias_names import alias_key, validate_alias_name
from dkreminders_bot.ui.messages import ALIAS_MENU_NOTICES as N
from dkreminders_bot.utils.time_utils import to_iso


TABLES = {"user": "user_aliases", "chat": "chat_aliases"}


class AliasMenuStore:
    def __init__(self, db_path):
        self.db_path = db_path

    @contextmanager
    def connection(self, *, write=False):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                if write:
                    conn.execute("BEGIN IMMEDIATE")
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _list(conn, owner):
        result = []
        for kind, table in TABLES.items():
            result.extend({**dict(r), "kind": kind} for r in conn.execute(f"SELECT * FROM {table} WHERE created_by=?", (owner,)))
        return sorted(result, key=lambda r: (
            0 if r["kind"] == "chat" else 1,
            alias_key(r["alias"]).replace("ё", "е"), alias_key(r["alias"]), r["alias"],
        ))

    def aliases(self, owner):
        with self.connection() as conn:
            return self._list(conn, owner)

    @classmethod
    def _available(cls, conn, owner, name, *, except_row=None):
        for row in cls._list(conn, owner):
            if alias_key(row["alias"]) == alias_key(name) and row != except_row:
                raise ValueError(N["conflict"])

    def available(self, owner, name):
        name = validate_alias_name(name)
        with self.connection() as conn:
            self._available(conn, owner, name)
        return name

    @staticmethod
    def _current(conn, owner, snapshot):
        kind = snapshot.get("kind")
        if kind not in TABLES or snapshot.get("created_by") != owner:
            raise ValueError(N["changed"])
        row = conn.execute(f"SELECT * FROM {TABLES[kind]} WHERE created_by=? AND alias=?", (owner, snapshot.get("alias"))).fetchone()
        if row is None or {**dict(row), "kind": kind} != snapshot:
            raise ValueError(N["changed"])
        return dict(snapshot)

    def current(self, owner, snapshot):
        with self.connection() as conn:
            return self._current(conn, owner, snapshot)

    @staticmethod
    def _user_target(conn, raw):
        if not re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{0,31}", raw or ""):
            raise ValueError(N["username"])
        row = conn.execute("""SELECT user_id, chat_id, username FROM user_chats
            WHERE LOWER(username)=? AND chat_id>0 AND user_id=chat_id
            ORDER BY updated_at DESC LIMIT 1""", (raw[1:].lower(),)).fetchone()
        if row is None:
            raise ValueError(N["unknown_user"])
        return dict(row)

    def user_target(self, raw):
        with self.connection() as conn:
            return self._user_target(conn, raw)

    def create(self, owner, name, kind, target, now):
        name = validate_alias_name(name)
        with self.connection(write=True) as conn:
            self._available(conn, owner, name)
            if kind == "user":
                latest = self._user_target(conn, "@" + target["username"])
                if latest != target:
                    raise ValueError(N["target_changed"])
                conn.execute("""INSERT INTO user_aliases(alias,user_id,chat_id,username,created_by,created_at)
                    VALUES(?,?,?,?,?,?)""", (name, target["user_id"], target["chat_id"], target["username"], owner, to_iso(now)))
            elif kind == "chat" and type(target.get("chat_id")) is int and target["chat_id"] < 0:
                conn.execute("INSERT INTO chat_aliases(alias,chat_id,title,created_by) VALUES(?,?,?,?)", (name, target["chat_id"], target.get("title"), owner))
            else:
                raise ValueError(N["group_unavailable"])
        return name

    def rename(self, owner, snapshot, new_name):
        new_name = validate_alias_name(new_name)
        with self.connection(write=True) as conn:
            row = self._current(conn, owner, snapshot)
            self._available(conn, owner, new_name, except_row=row)
            conn.execute(f"UPDATE {TABLES[row['kind']]} SET alias=? WHERE created_by=? AND alias=?", (new_name, owner, row["alias"]))
        return new_name

    def delete(self, owner, snapshot):
        with self.connection(write=True) as conn:
            row = self._current(conn, owner, snapshot)
            conn.execute(f"DELETE FROM {TABLES[row['kind']]} WHERE created_by=? AND alias=?", (owner, row["alias"]))
