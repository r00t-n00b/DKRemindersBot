"""Database schema creation and migration helpers.

This module preserves the SQL behavior from main.py.
"""

from typing import List
import sqlite3


_DEP_NAMES = (
    "DB_PATH",
    "logger",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _ensure_column_impl(conn: sqlite3.Connection, table: str, column: str, ddl: str, *, deps) -> None:
    _apply_deps(deps)
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info({table})')
    cols = {row[1] for row in cur.fetchall()}
    if column not in cols:
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')
        conn.commit()


def init_db_impl(*, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('\n        CREATE TABLE IF NOT EXISTS reminders (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            chat_id INTEGER NOT NULL,\n            text TEXT NOT NULL,\n            remind_at TEXT NOT NULL,\n            created_by INTEGER,\n            created_at TEXT NOT NULL,\n            delivered INTEGER NOT NULL DEFAULT 0,\n            template_id INTEGER\n        )\n        ')
    c.execute('PRAGMA table_info(reminders)')
    cols = [row[1] for row in c.fetchall()]
    if 'template_id' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN template_id INTEGER')
        logger.info('DB migration: added reminders.template_id column')
    c.execute('PRAGMA table_info(reminders)')
    cols = [row[1] for row in c.fetchall()]
    if 'template_id' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN template_id INTEGER')
        logger.info('DB migration: added reminders.template_id column')
    if 'acked' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN acked INTEGER NOT NULL DEFAULT 0')
        logger.info('DB migration: added reminders.acked column')
    if 'sent_at' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN sent_at TEXT')
        logger.info('DB migration: added reminders.sent_at column')
    if 'nudge_count' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN nudge_count INTEGER NOT NULL DEFAULT 0')
        logger.info('DB migration: added reminders.nudge_count column')
    if 'delivery_state' not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN delivery_state TEXT NOT NULL DEFAULT 'pending'")
        logger.info('DB migration: added reminders.delivery_state column')
    if 'processing_started_at' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN processing_started_at TEXT')
        logger.info('DB migration: added reminders.processing_started_at column')
    if 'delivery_attempts' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN delivery_attempts INTEGER NOT NULL DEFAULT 0')
        logger.info('DB migration: added reminders.delivery_attempts column')
    if 'last_error' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN last_error TEXT')
        logger.info('DB migration: added reminders.last_error column')
    if 'next_retry_at' not in cols:
        c.execute('ALTER TABLE reminders ADD COLUMN next_retry_at TEXT')
        logger.info('DB migration: added reminders.next_retry_at column')

    c.execute(
        """
        UPDATE reminders
        SET delivery_state = CASE WHEN delivered = 1 THEN 'sent' ELSE 'pending' END
        WHERE delivery_state IS NULL
           OR delivery_state = ''
        """
    )

    c.execute('CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(delivered, remind_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reminders_delivery_claim ON reminders(delivered, delivery_state, remind_at, next_retry_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reminders_processing_started ON reminders(delivery_state, processing_started_at)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reminders_nudge ON reminders(delivered, acked, nudge_count, sent_at)')
    c.execute('\n        CREATE TABLE IF NOT EXISTS reminder_messages (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            reminder_id INTEGER NOT NULL,\n            chat_id INTEGER NOT NULL,\n            message_id INTEGER NOT NULL,\n            kind TEXT NOT NULL,\n            created_at TEXT NOT NULL,\n            UNIQUE(reminder_id, chat_id, message_id)\n        )\n        ')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reminder_messages_reminder_id ON reminder_messages(reminder_id)')
    c.execute('\n        CREATE TABLE IF NOT EXISTS chat_aliases (\n            alias TEXT NOT NULL,\n            chat_id INTEGER NOT NULL,\n            title TEXT,\n            created_by INTEGER NOT NULL,\n            PRIMARY KEY (created_by, alias)\n        )\n        ')
    c.execute('\n        CREATE TABLE IF NOT EXISTS recurring_templates (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            chat_id INTEGER NOT NULL,\n            text TEXT NOT NULL,\n            pattern_type TEXT NOT NULL,\n            payload TEXT NOT NULL,\n            time_hour INTEGER NOT NULL,\n            time_minute INTEGER NOT NULL,\n            created_by INTEGER,\n            created_at TEXT NOT NULL,\n            active INTEGER NOT NULL DEFAULT 1\n        )\n        ')
    c.execute('\n        CREATE TABLE IF NOT EXISTS user_aliases (\n            alias TEXT NOT NULL,\n            user_id INTEGER NOT NULL,\n            chat_id INTEGER NOT NULL,\n            username TEXT,\n            created_by INTEGER NOT NULL,\n            created_at TEXT NOT NULL,\n            PRIMARY KEY (created_by, alias)\n        )\n        ')
    c.execute('\n        CREATE TABLE IF NOT EXISTS user_chats (\n            user_id INTEGER PRIMARY KEY,\n            chat_id INTEGER NOT NULL,\n            username TEXT,\n            first_name TEXT,\n            last_name TEXT,\n            updated_at TEXT NOT NULL\n        )\n        ')
    c.execute('CREATE INDEX IF NOT EXISTS idx_user_chats_username ON user_chats(username)')
    c.execute('\n        CREATE TABLE IF NOT EXISTS user_settings (\n            user_id INTEGER PRIMARY KEY,\n            default_hour INTEGER,\n            default_minute INTEGER,\n            updated_at TEXT NOT NULL\n        )\n        ')
    conn.commit()
    conn.close()


def migrate_alias_tables_to_owner_scope_impl(*, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    def table_info(table_name: str):
        c.execute(f'PRAGMA table_info({table_name})')
        return c.fetchall()

    def primary_key_columns(table_name: str) -> List[str]:
        rows = table_info(table_name)
        pk_rows = [row for row in rows if int(row[5]) > 0]
        pk_rows.sort(key=lambda row: int(row[5]))
        return [str(row[1]) for row in pk_rows]
    user_cols = [str(row[1]) for row in table_info('user_aliases')]
    user_pk = primary_key_columns('user_aliases')
    if user_cols and user_pk != ['created_by', 'alias']:
        c.execute('ALTER TABLE user_aliases RENAME TO user_aliases_old_owner_scope')
        c.execute('\n            CREATE TABLE user_aliases (\n                alias TEXT NOT NULL,\n                user_id INTEGER NOT NULL,\n                chat_id INTEGER NOT NULL,\n                username TEXT,\n                created_by INTEGER NOT NULL,\n                created_at TEXT NOT NULL,\n                PRIMARY KEY (created_by, alias)\n            )\n            ')
        c.execute('\n            INSERT OR IGNORE INTO user_aliases(alias, user_id, chat_id, username, created_by, created_at)\n            SELECT alias, user_id, chat_id, username, created_by, created_at\n            FROM user_aliases_old_owner_scope\n            WHERE created_by IS NOT NULL\n            ')
        c.execute('DROP TABLE user_aliases_old_owner_scope')
    chat_cols = [str(row[1]) for row in table_info('chat_aliases')]
    chat_pk = primary_key_columns('chat_aliases')
    if chat_cols and chat_pk != ['created_by', 'alias']:
        c.execute('ALTER TABLE chat_aliases RENAME TO chat_aliases_old_owner_scope')
        c.execute('\n            CREATE TABLE chat_aliases (\n                alias TEXT NOT NULL,\n                chat_id INTEGER NOT NULL,\n                title TEXT,\n                created_by INTEGER NOT NULL,\n                PRIMARY KEY (created_by, alias)\n            )\n            ')
        if 'created_by' in chat_cols:
            c.execute('\n                INSERT OR IGNORE INTO chat_aliases(alias, chat_id, title, created_by)\n                SELECT alias, chat_id, title, created_by\n                FROM chat_aliases_old_owner_scope\n                WHERE created_by IS NOT NULL\n                ')
        c.execute('DROP TABLE chat_aliases_old_owner_scope')
    conn.commit()
    conn.close()
