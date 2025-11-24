import logging
import os
import sqlite3
from datetime import datetime

from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TZ = ZoneInfo("Europe/Madrid")
DB_PATH = "reminders.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            run_at TEXT NOT NULL,
            text TEXT NOT NULL,
            sent INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def add_reminder(chat_id: int, run_at: datetime, text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reminders (chat_id, run_at, text, sent) VALUES (?, ?, ?, 0)",
        (chat_id, run_at.isoformat(), text),
    )
    conn.commit()
    conn.close()


def get_due_reminders(now: datetime):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, chat_id, run_at, text FROM reminders "
        "WHERE sent = 0 AND run_at <= ?",
        (now.isoformat(),),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_sent(reminder_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def get_future_reminders(chat_id: int):
    now = datetime.now(TZ).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT run_at, text FROM reminders "
        "WHERE sent = 0 AND chat_id = ? AND run_at > ? "
        "ORDER BY run_at ASC",
        (chat_id, now),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = get_future_reminders(update.effective_chat.id)

    if not reminders:
        await update.message.reply_text("Нет запланированных напоминаний.")
        return

    msg = "Запланированные напоминания:\n\n"
    for run_at_str, text in reminders:
        dt = datetime.fromisoformat(run_at_str)
        msg += f"• {dt.strftime('%d.%m %H:%M')} — {text}\n"

    await update.message.reply_text(msg)


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Формат: /remind DD.MM HH:MM Текст
    if len(context.args) < 3:
        await update.message.reply_text(
            "Формат: /remind DD.MM HH:MM Текст\n"
            "Например: /remind 1.12 11:00 Завтра в 20:45 футбол"
        )
        return

    date_str = context.args[0]    # "1.12" или "01.12"
    time_str = context.args[1]    # "11:00"
    text = " ".join(context.args[2:])

    try:
        # Поддержка 1.12
        day, month = map(int, date_str.split("."))
        hour, minute = map(int, time_str.split(":"))

        now = datetime.now(TZ)
        year = now.year

        run_at = datetime(year, month, day, hour, minute, tzinfo=TZ)

        if run_at < now:
            run_at = datetime(year + 1, month, day, hour, minute, tzinfo=TZ)

    except Exception:
        await update.message.reply_text(
            "Ошибка формата.\n"
            "Правильно так: /remind 1.12 11:00 Завтра в 20:45 футбол"
        )
        return

    add_reminder(update.effective_chat.id, run_at, text)
    await update.message.reply_text(
        f"Ок, напомню {run_at.strftime('%d.%m %H:%M')}: \"{text}\""
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я ремайндер бот.\n\n"
        "Команды:\n"
        "/remind DD.MM HH:MM Текст — создать напоминание\n"
        "/list — показать будущие напоминания\n\n"
        "Пример:\n"
        "/remind 1.12 11:00 Завтра в 20:45 футбол"
    )


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TZ)
    due = get_due_reminders(now)

    if not due:
        return

    for reminder_id, chat_id, run_at_str, text in due:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            mark_sent(reminder_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("remind", remind_command))

    app.job_queue.run_repeating(check_reminders, interval=30, first=10)

    app.run_polling()


if __name__ == "__main__":
    main()