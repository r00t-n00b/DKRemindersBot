import asyncio
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from zoneinfo import ZoneInfo

from telegram import (
    Update,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
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


def delete_reminder(reminder_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
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
        """,
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


def get_chat_reminders(chat_id: int) -> List[tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, text, remind_at
        FROM reminders
        WHERE chat_id = ? AND delivered = 0
        ORDER BY remind_at ASC
        """,
        (chat_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


# ===== Парсинг команд =====

# Старый строгий формат DD.MM HH:MM - текст
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


def add_months(dt: datetime, months: int) -> datetime:
    """Примитивное добавление месяцев: тот же день месяца, если возможно, иначе последний день."""
    year = dt.year
    month = dt.month + months
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    day = dt.day
    for d in range(day, 0, -1):
        try:
            return dt.replace(year=year, month=month, day=d)
        except ValueError:
            continue
    return dt.replace(year=year, month=month, day=1)


def weekday_from_name(name: str) -> Optional[int]:
    """Преобразует имя дня недели (en/ru) в номер weekday 0-6 (понедельник - понедельник)."""
    n = name.strip().lower()
    mapping = {
        "monday": 0, "mon": 0, "понедельник": 0, "пн": 0,
        "tuesday": 1, "tue": 1, "tues": 1, "вторник": 1, "вт": 1,
        "wednesday": 2, "wed": 2, "среда": 2, "ср": 2,
        "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "четверг": 3, "чт": 3,
        "friday": 4, "fri": 4, "пятница": 4, "пт": 4,
        "saturday": 5, "sat": 5, "суббота": 5, "сб": 5,
        "sunday": 6, "sun": 6, "воскресенье": 6, "вс": 6,
    }
    return mapping.get(n)


def next_weekday_date(now: datetime, target_wd: int) -> datetime:
    today_wd = now.weekday()
    delta = (target_wd - today_wd) % 7
    if delta == 0:
        delta = 7
    return now + timedelta(days=delta)


def next_weekend_date(now: datetime) -> datetime:
    """Ближайшая суббота 11:00, если уже прошло - следующая."""
    target_wd = 5  # суббота
    today_wd = now.weekday()
    delta = (target_wd - today_wd) % 7
    candidate_date = now.date() + timedelta(days=delta)
    candidate_dt = datetime(
        candidate_date.year,
        candidate_date.month,
        candidate_date.day,
        11,
        0,
        tzinfo=TZ,
    )
    if candidate_dt <= now:
        candidate_dt = candidate_dt + timedelta(days=7)
    return candidate_dt


def next_workday_date(now: datetime) -> datetime:
    """Ближайший рабочий день (пн-пт) на 11:00."""
    candidate = now
    while True:
        wd = candidate.weekday()
        if wd < 5:  # пн-пт
            candidate_dt = datetime(
                candidate.year,
                candidate.month,
                candidate.day,
                11,
                0,
                tzinfo=TZ,
            )
            if candidate_dt > now:
                return candidate_dt
        candidate = candidate + timedelta(days=1)


def parse_relative_in(rest: str, now: datetime) -> datetime:
    """
    "in 2 hours", "in 3 days", "in 1 week", "in 2 months"
    "через 2 часа", "через 3 дня", "через 2 недели", "через 1 месяц"
    """
    tokens = rest.split()
    if len(tokens) < 2:
        raise ValueError("Не смог понять формат после 'in/через'")

    try:
        num = int(tokens[0])
    except ValueError:
        raise ValueError("Ожидаю число после 'in/через', например 'in 2 hours'")

    unit = tokens[1].lower()

    minute_words_en = {"minute", "minutes", "min", "mins"}
    hour_words_en = {"hour", "hours", "hr", "hrs"}
    day_words_en = {"day", "days"}
    week_words_en = {"week", "weeks"}
    month_words_en = {"month", "months"}

    minute_words_ru = {"минута", "минуту", "минуты", "минут"}
    hour_words_ru = {"час", "часа", "часов"}
    day_words_ru = {"день", "дня", "дней"}
    week_words_ru = {"неделя", "неделю", "недели", "недель"}
    month_words_ru = {"месяц", "месяца", "месяцев"}

    if unit in minute_words_en or unit in minute_words_ru:
        return now + timedelta(minutes=num)
    if unit in hour_words_en or unit in hour_words_ru:
        return now + timedelta(hours=num)
    if unit in day_words_en or unit in day_words_ru:
        return now + timedelta(days=num)
    if unit in week_words_en or unit in week_words_ru:
        return now + timedelta(weeks=num)
    if unit in month_words_en or unit in month_words_ru:
        return add_months(now, num)

    raise ValueError("Не смог понять единицу времени после 'in/через'")


def parse_natural_when(when_str: str, now: datetime) -> datetime:
    """
    Поддерживает:
    - in / через N units
    - today / завтра / послезавтра и т.п.
    - next week/month/day/Monday/следующая неделя/следующий понедельник
    - weekend / weekday / workday / рабочий день
    - только дату DD.MM -> 11:00 по умолчанию
    - только время HH:MM -> ближайшее такое время (сегодня или завтра)
    """
    s = when_str.strip().lower()
    if not s:
        raise ValueError("Пустое время напоминания")

    # 1. 'in ...' / 'через ...'
    if s.startswith("in "):
        return parse_relative_in(s[3:].strip(), now)
    if s.startswith("через "):
        return parse_relative_in(s[6:].strip(), now)

    # 2. Выделяем возможное HH:MM в конце
    m_time = re.search(r'(\d{1,2}):(\d{2})$', s)
    time_hm: Optional[tuple[int, int]] = None
    if m_time:
        h = int(m_time.group(1))
        m = int(m_time.group(2))
        if h > 23 or m > 59:
            raise ValueError("Неверный формат времени HH:MM")
        time_hm = (h, m)
        s = s[:m_time.start()].strip()

    # 3. Только время без даты
    if not s and time_hm:
        h, m = time_hm
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        return candidate

    # 4. Только дата DD.MM или DD/MM
    m_date = re.fullmatch(r'(\d{1,2})[./](\d{1,2})', s)
    if m_date:
        day = int(m_date.group(1))
        month = int(m_date.group(2))
        year = now.year
        hour, minute = time_hm if time_hm else (11, 0)
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата: {e}") from e

        if dt < now - timedelta(minutes=1):
            try:
                dt = datetime(year + 1, month, day, hour, minute, tzinfo=TZ)
            except ValueError as e:
                raise ValueError(
                    f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
                ) from e
        return dt

    # 5. Текстовые варианты
    canon = " ".join(s.split())

    base_date = None

    if canon in ("today", "сегодня"):
        base_date = now.date()
    elif canon in ("tomorrow", "завтра", "next day", "следующий день"):
        base_date = now.date() + timedelta(days=1)
    elif canon in ("day after tomorrow", "послезавтра"):
        base_date = now.date() + timedelta(days=2)
    elif canon in ("next week", "следующая неделя"):
        base_date = now.date() + timedelta(weeks=1)
    elif canon in ("next month", "следующий месяц"):
        base_date = add_months(now, 1).date()
    elif canon in ("weekend", "выходные", "выходной"):
        return next_weekend_date(now)
    elif canon in ("weekday", "workday", "рабочий день"):
        return next_workday_date(now)
    elif canon.startswith("next "):
        wd_name = canon[5:].strip()
        wd = weekday_from_name(wd_name)
        if wd is None:
            raise ValueError("Не узнал день недели после 'next'")
        base_date = next_weekday_date(now, wd).date()
    elif canon.startswith("следующий "):
        wd_name = canon[len("следующий "):].strip()
        wd = weekday_from_name(wd_name)
        if wd is None:
            raise ValueError("Не узнал день недели после 'следующий'")
        base_date = next_weekday_date(now, wd).date()
    else:
        raise ValueError("Не распознал формат времени")

    hour, minute = time_hm if time_hm else (11, 0)
    return datetime(base_date.year, base_date.month, base_date.day, hour, minute, tzinfo=TZ)


def parse_reminder_line(line: str, now: datetime) -> Reminder:
    """
    Поддерживает:
    - 28.11 12:00 - текст
    - 28.11 - текст (по умолчанию 11:00)
    - 12:30 - текст (ближайшее такое время: сегодня или завтра)
    - tomorrow 18:00 - текст / завтра 18:00 - текст
    - tomorrow - текст (11:00)
    - day after tomorrow / послезавтра - текст
    - next Monday 19:00 - текст / следующий понедельник 19:00 - текст
    - weekend / weekday / workday / рабочий день - текст
    - in 2 hours - текст / через 2 часа - текст
    """

    stripped = line.strip()

    # 1. Пробуем строгий формат DD.MM HH:MM - текст
    m = REMIND_LINE_RE.match(stripped)
    if m:
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

        if dt < now - timedelta(minutes=1):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError as e:
                raise ValueError(
                    f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
                ) from e

        return Reminder(id=-1, chat_id=0, text=text, remind_at=dt, created_by=None)

    # 2. Общий случай: "<когда> - <текст>"
    sep_pos = None
    sep_len = None
    for sep in [" - ", " — ", " – "]:
        idx = stripped.find(sep)
        if idx != -1:
            sep_pos = idx
            sep_len = len(sep)
            break

    if sep_pos is None:
        raise ValueError("Ожидаю формат '<когда> - текст'")

    when_part = stripped[:sep_pos].strip()
    text = stripped[sep_pos + sep_len:].strip()

    if not when_part:
        raise ValueError("Не указано время напоминания до '-'")
    if not text:
        raise ValueError("Не указан текст после '-'")

    dt = parse_natural_when(when_part, now)
    return Reminder(id=-1, chat_id=0, text=text, remind_at=dt, created_by=None)


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
    В личке:
    - если первая строка начинается с "-" -> это bulk без alias
    - если первое слово похоже на дату/время или временное слово -> НЕ alias
    - иначе первое слово считаем alias.

    Работает и с bulk:
      "football 28.11 12:00 - текст"
        -> ("football", "28.11 12:00 - текст")

      "football\n- 28.11 12:00 - текст"
        -> ("football", "- 28.11 12:00 - текст")

      "- 28.11 12:00 - текст" (bulk без alias)
        -> (None, "- 28.11 12:00 - текст")
    """
    if not args_text:
        return None, ""

    # Сначала режем по строкам, потому что alias может быть только в первой
    lines = args_text.splitlines()
    first_line = lines[0].lstrip()
    rest_lines = "\n".join(lines[1:])

    if not first_line:
        # пустая первая строка - точно не alias
        return None, args_text.lstrip()

    # если начинается с "-", это точно bulk без alias
    if first_line.startswith("-"):
        return None, args_text.lstrip()

    first, *rest_first = first_line.split(maxsplit=1)
    lower = first.lower()

    # 1) Похоже на дату вида DD.MM или DD/MM
    if re.fullmatch(r"\d{1,2}[./]\d{1,2}", first):
        return None, args_text.lstrip()

    # 2) Похоже на время вида HH:MM
    if re.fullmatch(r"\d{1,2}:\d{2}", first):
        return None, args_text.lstrip()

    # 3) Ключевые слова, которые должны трактоваться как "время", а не alias
    RESERVED_TIME_WORDS = {
        # английский
        "in",
        "tomorrow",
        "today",
        "tonight",
        "next",
        "weekend",
        "weekday",
        "workday",
        "workdays",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        # русский
        "через",
        "завтра",
        "послезавтра",
        "выходные",
        "будни",
        "будний",
        "буднийдень",
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    }

    if lower in RESERVED_TIME_WORDS:
        # точно НЕ alias, а часть временного выражения
        return None, args_text.lstrip()

    # Иначе считаем это alias (как раньше)
    alias = first
    after_alias_first_line = rest_first[0] if rest_first else ""

    parts = []
    if after_alias_first_line:
        parts.append(after_alias_first_line)
    if rest_lines:
        parts.append(rest_lines)

    new_args = "\n".join(parts).lstrip()
    return alias, new_args


# ===== Хендлеры команд =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет. Я твой личный бот для напоминаний.\n\n"
        "Базовый формат:\n"
        "/remind DD.MM HH:MM - текст\n"
        "Пример: /remind 28.11 12:00 - завтра футбол в 20:45\n\n"
        "Можно по-разному задавать время:\n"
        "- /remind 28.11 12:00 - классический формат\n"
        "- /remind 28.11 - только дата, время будет 11:00 по умолчанию\n"
        "- /remind 23:59 - только время, сегодня или завтра (если уже прошло)\n"
        "- /remind in 2 hours - через 2 часа\n"
        "- /remind tomorrow 18:00 - завтра в 18:00\n"
        "- /remind weekend - в ближайшие выходные в 11:00\n\n"
        "Bulk (много строк сразу):\n"
        "/remind\n"
        "- 28.11 12:00 - завтра спринт Ф1 в 15:00\n"
        "- 28.11 12:00 - завтра футбол в 20:45\n\n"
        "Личка с alias чата:\n"
        "1) В чате: /linkchat football\n"
        "2) В личке: /remind football 28.11 12:00 - завтра футбол\n\n"
        "/list - показать активные напоминания для чата и кнопки для удаления\n"
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
        await message.reply_text(
            "Команду /linkchat нужно вызывать в групповом чате, который хочешь привязать."
        )
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


def build_list_message_and_keyboard(chat_id: int) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    rows = get_chat_reminders(chat_id)
    if not rows:
        return "Напоминаний нет.", None

    # текст
    lines: List[str] = ["Активные напоминания:", ""]
    for idx, (rid, text, remind_at_str) in enumerate(rows, start=1):
        dt = datetime.fromisoformat(remind_at_str)
        ts = dt.strftime("%d.%m %H:%M")
        lines.append(f"{idx}. {ts} - {text}")
    text = "\n".join(lines)

    # кнопки
    buttons: List[InlineKeyboardButton] = []
    for idx, (rid, _, _) in enumerate(rows, start=1):
        buttons.append(
            InlineKeyboardButton(
                text=f"❌ {idx}",
                callback_data=f"del:{rid}",
            )
        )
    keyboard_rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
    markup = InlineKeyboardMarkup(keyboard_rows)

    return text, markup


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message

    if chat is None or message is None:
        return

    text, markup = build_list_message_and_keyboard(chat.id)
    await message.reply_text(text, reply_markup=markup)


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return

    data = query.data or ""
    if not data.startswith("del:"):
        await query.answer()
        return

    try:
        reminder_id = int(data.split(":", 1)[1])
    except ValueError:
        await query.answer("Что-то пошло не так.")
        return

    # удаляем напоминание
    delete_reminder(reminder_id)

    chat_id = query.message.chat_id
    text, markup = build_list_message_and_keyboard(chat_id)

    await query.edit_message_text(text=text, reply_markup=markup)
    await query.answer("Удалил.")


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

    # В личке допускаем alias в первой строке, но корректно обрабатываем bulk
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
        error_lines: List[str] = []

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
    application.add_handler(CallbackQueryHandler(delete_callback))

    logger.info("Запускаем бота polling...")
    application.run_polling()


if __name__ == "__main__":
    main()