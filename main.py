import asyncio
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List

from zoneinfo import ZoneInfo

from telegram import Update, Chat
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ===== Настройки =====

TZ = ZoneInfo("Europe/Madrid")
DB_PATH = os.environ.get("DB_PATH", "/data/reminders.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ===== Модель данных =====

@dataclass
class Reminder:
    id: int
    chat_id: int
    text: str
    remind_at: datetime
    created_by: Optional[int]


# ===== Работа с БД =====

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_aliases (
            alias TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            title TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def add_reminder(
    chat_id: int,
    text: str,
    remind_at: datetime,
    created_by: Optional[int],
) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO reminders (chat_id, text, remind_at, created_by, created_at, delivered)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (
            chat_id,
            text,
            remind_at.isoformat(),
            created_by,
            datetime.now(TZ).isoformat(),
        ),
    )
    reminder_id = c.lastrowid
    conn.commit()
    conn.close()
    return reminder_id


def get_due_reminders(now: datetime) -> List[Reminder]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, chat_id, text, remind_at, created_by
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
        rid, chat_id, text, remind_at_str, created_by = row
        reminders.append(
            Reminder(
                id=rid,
                chat_id=chat_id,
                text=text,
                remind_at=datetime.fromisoformat(remind_at_str),
                created_by=created_by,
            )
        )
    return reminders


def mark_reminder_sent(reminder_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET delivered = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def set_chat_alias(alias: str, chat_id: int, title: Optional[str]) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO chat_aliases(alias, chat_id, title)
        VALUES (?, ?, ?)
        ON CONFLICT(alias) DO UPDATE SET
            chat_id = excluded.chat_id,
            title = excluded.title
        """
        ,
        (alias, chat_id, title),
    )
    conn.commit()
    conn.close()


def get_chat_id_by_alias(alias: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM chat_aliases WHERE alias = ?", (alias,))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return None


def get_all_aliases():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT alias, chat_id, title FROM chat_aliases ORDER BY alias")
    rows = c.fetchall()
    conn.close()
    return rows


# ===== Парсинг команд =====

REMIND_LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<day>\d{1,2})
    [./](?P<month>\d{1,2})
    \s+
    (?P<hour>\d{1,2})
    :
    (?P<minute>\d{2})
    \s*
    [-–—]
    \s*
    (?P<text>.+)
    $
    """,
    re.VERBOSE,
)


def parse_reminder_line(line: str, now: datetime) -> Reminder:
    """
    Строка вида:
    28.11 12:00 - завтра футбол в 20:45
    """
    m = REMIND_LINE_RE.match(line.strip())
    if not m:
        raise ValueError("Ожидаю формат 'DD.MM HH:MM - текст'")

    day = int(m.group("day"))
    month = int(m.group("month"))
    hour = int(m.group("hour"))
    minute = int(m.group("minute"))
    text = m.group("text").strip()

    year = now.year
    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
    except ValueError as e:
        raise ValueError(f"Неверная дата или время: {e}") from e

    # Если дата уже в прошлом - считаем, что имеется в виду следующий год
    if dt < now - timedelta(minutes=1):
        try:
            dt = dt.replace(year=year + 1)
        except ValueError as e:
            raise ValueError(
                f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
            ) from e

    dummy = Reminder(id=-1, chat_id=0, text=text, remind_at=dt, created_by=None)
    return dummy


def extract_after_command(text: str) -> str:
    """
    Убирает /remind или /remind@Bot и возвращает остальной текст.
    """
    if not text:
        return ""
    stripped = text.strip()
    parts = stripped.split(maxsplit=1)
    if not parts:
        return ""
    if not parts[0].startswith("/"):
        return stripped
    if len(parts) == 1:
        return ""
    return parts[1]


def maybe_split_alias_first_token(args_text: str):
    """
    В личке: если первое слово не похоже на дату, считаем его alias.
    """
    args_text = args_text.strip()
    if not args_text:
        return None, ""

    first, *rest = args_text.split(maxsplit=1)
    # Похоже ли это на дату? 2 цифры.2 цифры
    if re.fullmatch(r"\d{1,2}[./]\d{1,2}", first):
        return None, args_text

    if not rest:
        return first, ""
    return first, rest[0]


# ===== Хендлеры команд =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет. Я твой личный бот для напоминаний.\n\n"
        "Основное:\n"
        "/remind DD.MM HH:MM - текст\n"
        "Пример: /remind 28.11 12:00 - завтра футбол в 20:45\n\n"
        "Bulk (много строк сразу):\n"
        "/remind\n"
        "- 28.11 12:00 - завтра спринт Ф1 в 15:00\n"
        "- 28.11 12:00 - завтра футбол в 20:45\n\n"
        "Личка с alias чата:\n"
        "1) В чате: /linkchat football\n"
        "2) В личке: /remind football 28.11 12:00 - завтра футбол\n"
        "\n"
        "/list - показать активные напоминания для чата\n"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def linkchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message

    if chat is None or message is None:
        return

    if chat.type == Chat.PRIVATE:
        await message.reply_text("Команду /linkchat нужно вызывать в групповом чате, который хочешь привязать.")
        return

    if not context.args:
        await message.reply_text("Формат: /linkchat alias\nНапример: /linkchat football")
        return

    alias = context.args[0].strip()
    if not alias:
        await message.reply_text("Alias не должен быть пустым.")
        return

    title = chat.title or chat.username or str(chat.id)
    set_chat_alias(alias, chat.id, title)

    await message.reply_text(
        f"Ок, запомнил этот чат как '{alias}'.\n"
        f"Теперь в личке можно писать:\n"
        f"/remind {alias} 28.11 12:00 - завтра футбол"
    )


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    now = datetime.now(TZ)
    raw_args = extract_after_command(message.text or "")

    if not raw_args.strip():
        await message.reply_text(
            "Формат:\n"
            "/remind DD.MM HH:MM - текст\n"
            "или bulk:\n"
            "/remind\n"
            "- 28.11 12:00 - завтра футбол\n"
        )
        return

    is_private = chat.type == Chat.PRIVATE

    target_chat_id = chat.id
    used_alias: Optional[str] = None

    # В личке допускаем alias первым словом
    if is_private:
        maybe_alias, rest = maybe_split_alias_first_token(raw_args)
        if maybe_alias is not None:
            alias_chat_id = get_chat_id_by_alias(maybe_alias)
            if alias_chat_id is None:
                aliases = get_all_aliases()
                if not aliases:
                    await message.reply_text(
                        f"Alias '{maybe_alias}' не найден.\n"
                        f"Сначала зайди в нужный чат и выполни /linkchat название.\n"
                    )
                else:
                    known = ", ".join(a for a, _, _ in aliases)
                    await message.reply_text(
                        f"Alias '{maybe_alias}' не найден.\n"
                        f"Из известных: {known}"
                    )
                return

            target_chat_id = alias_chat_id
            used_alias = maybe_alias
            raw_args = rest.strip()

            if not raw_args:
                await message.reply_text(
                    "После alias нужно указать дату и текст.\n"
                    "Пример:\n"
                    f"/remind {used_alias} 28.11 12:00 - завтра футбол"
                )
                return

    # Bulk или одиночный?
    if "\n" in raw_args:
        lines = [ln.strip() for ln in raw_args.splitlines() if ln.strip()]
        created = 0
        failed = 0
        error_lines: list[str] = []

        for line in lines:
            # убираем ведущий "- " если есть
            if line.startswith("- "):
                line = line[2:].strip()
            try:
                parsed = parse_reminder_line(line, now)
                reminder_id = add_reminder(
                    chat_id=target_chat_id,
                    text=parsed.text,
                    remind_at=parsed.remind_at,
                    created_by=user.id,
                )
                created += 1
                logger.info(
                    "Создан bulk reminder id=%s chat_id=%s at=%s text=%s",
                    reminder_id,
                    target_chat_id,
                    parsed.remind_at.isoformat(),
                    parsed.text,
                )
            except Exception as e:
                failed += 1
                error_lines.append(f"'{line}': {e}")

        reply = f"Готово. Создано напоминаний: {created}."
        if failed:
            reply += f" Не удалось разобрать строк: {failed}."
        if error_lines:
            reply += "\n\nПроблемные строки (до 5):\n" + "\n".join(error_lines[:5])

        await message.reply_text(reply)
        return

    # Одиночная строка
    try:
        parsed = parse_reminder_line(raw_args.strip(), now)
    except ValueError as e:
        await message.reply_text(f"Не смог понять дату и текст: {e}")
        return

    reminder_id = add_reminder(
        chat_id=target_chat_id,
        text=parsed.text,
        remind_at=parsed.remind_at,
        created_by=user.id,
    )

    logger.info(
        "Создан reminder id=%s chat_id=%s at=%s text=%s (from chat %s, user %s)",
        reminder_id,
        target_chat_id,
        parsed.remind_at.isoformat(),
        parsed.text,
        chat.id,
        user.id,
    )

    when_str = parsed.remind_at.strftime("%d.%m %H:%M")
    if used_alias:
        await message.reply_text(
            f"Ок, напомню в чате '{used_alias}' {when_str}: {parsed.text}"
        )
    else:
        await message.reply_text(
            f"Ок, напомню {when_str}: {parsed.text}"
        )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message

    if chat is None or message is None:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, text, remind_at
        FROM reminders
        WHERE chat_id = ? AND delivered = 0
        ORDER BY remind_at ASC
        """,
        (chat.id,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        await message.reply_text("Напоминаний нет.")
        return

    lines = []
    for rid, text, remind_at_str in rows:
        dt = datetime.fromisoformat(remind_at_str)
        ts = dt.strftime("%d.%m %H:%M")
        lines.append(f"{rid}. {ts} - {text}")

    reply = "Активные напоминания:\n\n" + "\n".join(lines)
    await message.reply_text(reply)


# ===== Фоновый worker =====

async def reminders_worker(app: Application) -> None:
    logger.info("Запущен фоновой worker напоминаний")
    while True:
        try:
            now = datetime.now(TZ)
            due = get_due_reminders(now)
            if due:
                logger.info("Нашел %s напоминаний к отправке", len(due))
            for r in due:
                try:
                    await app.bot.send_message(chat_id=r.chat_id, text=r.text)
                    mark_reminder_sent(r.id)
                    logger.info(
                        "Отправлено напоминание id=%s в чат %s: %s (время %s)",
                        r.id,
                        r.chat_id,
                        r.text,
                        r.remind_at.isoformat(),
                    )
                except Exception:
                    logger.exception("Ошибка при отправке напоминания id=%s", r.id)
        except Exception:
            logger.exception("Ошибка в worker напоминаний")

        await asyncio.sleep(10)


async def post_init(application: Application) -> None:
    init_db()
    application.create_task(reminders_worker(application))
    logger.info("Фоновый worker напоминаний запущен из post_init")


# ===== main =====

def main() -> None:
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("Не задан BOT_TOKEN")

    application = (
        Application.builder()
        .token(bot_token)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("linkchat", linkchat_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("list", list_command))

    logger.info("Запускаем бота polling...")
    application.run_polling()


if __name__ == "__main__":
    main()