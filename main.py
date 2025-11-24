import os
import asyncio
import logging
import sqlite3
from datetime import datetime, time as dtime

from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

DB_PATH = "reminders.db"
TZ = ZoneInfo("Europe/Madrid")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- БД ----------

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            remind_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def add_reminder(chat_id: int, text: str, remind_at: datetime) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reminders (chat_id, text, remind_at) VALUES (?, ?, ?)",
        (chat_id, text, remind_at.isoformat()),
    )
    conn.commit()
    conn.close()


def get_upcoming_reminders(chat_id: int | None = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if chat_id is None:
        cur.execute(
            "SELECT id, chat_id, text, remind_at FROM reminders ORDER BY remind_at ASC"
        )
    else:
        cur.execute(
            "SELECT id, chat_id, text, remind_at FROM reminders WHERE chat_id = ? ORDER BY remind_at ASC",
            (chat_id,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_due_reminders(now: datetime):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, chat_id, text, remind_at FROM reminders WHERE remind_at <= ?",
        (now.isoformat(),),
    )
    rows = cur.fetchall()
    if rows:
        ids = [row[0] for row in rows]
        cur.execute(
            f"DELETE FROM reminders WHERE id IN ({','.join('?' for _ in ids)})",
            ids,
        )
        conn.commit()
    conn.close()
    return rows


# ---------- Парсинг даты/времени ----------

def parse_date_time(date_str: str, time_str: str) -> datetime | None:
    """
    Ожидаем формат:
    - дата: 1.12 или 01.12
    - время: 11:00 или 11.00
    """
    try:
        day_str, month_str = date_str.split(".")
        day = int(day_str)
        month = int(month_str)
        # год - текущий или следующий, если дата уже прошла
        now = datetime.now(TZ)
        year = now.year
        dt_candidate = datetime(year, month, day, tzinfo=TZ)
        if dt_candidate.date() < now.date():
            year += 1
        # время
        sep = ":" if ":" in time_str else "."
        hh_str, mm_str = time_str.split(sep)
        hh = int(hh_str)
        mm = int(mm_str)
        return datetime(year, month, day, hh, mm, tzinfo=TZ)
    except Exception as e:
        logger.warning("Не смог распарсить дату/время %s %s: %s", date_str, time_str, e)
        return None


# ---------- Хендлеры команд ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! Я бот-напоминалка.\n\n"
        "Формат команды:\n"
        "/remind 1.12 11:00 Завтра в 20:45 футбол\n\n"
        "Это значит: 1 декабря в 11:00 я напомню в этот чат текстом "
        "«Завтра в 20:45 футбол».\n\n"
        "Посмотреть все напоминания в чате:\n"
        "/list"
    )
    await update.message.reply_text(text)


async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    chat_id = update.effective_chat.id

    if len(context.args) < 3:
        await update.message.reply_text(
            "Нужно так:\n/reminд 1.12 11:00 Текст напоминания"
        )
        return

    date_str = context.args[0]
    time_str = context.args[1]
    text = " ".join(context.args[2:])

    remind_at = parse_date_time(date_str, time_str)
    if remind_at is None:
        await update.message.reply_text(
            "Не понял дату/время. Пример: /remind 1.12 11:00 Завтра футбол"
        )
        return

    add_reminder(chat_id, text, remind_at)

    await update.message.reply_text(
        f"Ок, напомню {remind_at.strftime('%d.%m.%Y в %H:%M')}:\n{text}"
    )


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    chat_id = update.effective_chat.id
    rows = get_upcoming_reminders(chat_id)

    if not rows:
        await update.message.reply_text("В этом чате нет запланированных напоминаний.")
        return

    lines = ["Запланированные напоминания:"]
    for _, _chat_id, text, remind_at_str in rows:
        dt = datetime.fromisoformat(remind_at_str)
        lines.append(f"- {dt.strftime('%d.%m %H:%M')} — {text}")

    await update.message.reply_text("\n".join(lines))


# ---------- Фоновая проверка напоминаний ----------

async def reminders_worker(app: Application) -> None:
    """
    Вместо JobQueue просто крутится вечный цикл и каждые 30 секунд
    проверяет, нет ли напоминаний с временем ≤ сейчас.
    """
    await asyncio.sleep(5)  # чуть подождать после старта
    logger.info("Запущен фоновой worker напоминаний")

    while True:
        try:
            now = datetime.now(TZ)
            due = get_due_reminders(now)
            for _id, chat_id, text, remind_at_str in due:
                try:
                    await app.bot.send_message(chat_id=chat_id, text=text)
                    logger.info(
                        "Отправлено напоминание в чат %s: %s (время %s)",
                        chat_id,
                        text,
                        remind_at_str,
                    )
                except Exception as e:
                    logger.warning(
                        "Не удалось отправить напоминание в чат %s: %s", chat_id, e
                    )
        except Exception as e:
            logger.error("Ошибка в reminders_worker: %s", e)

        await asyncio.sleep(30)


async def post_init(app: Application) -> None:
    # Запускаем фонового работника после инициализации приложения
    asyncio.create_task(reminders_worker(app))


# ---------- main ----------

def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN")

    init_db()

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("list", list_cmd))

    logger.info("Запускаем бота polling...")
    app.run_polling()


if __name__ == "__main__":
    main()