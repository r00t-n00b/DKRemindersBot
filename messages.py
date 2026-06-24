"""User-facing message catalog for the Telegram reminder bot.

Keep user-visible texts here first. Handler code should reference MSG_* constants
or msg_* helper functions instead of embedding error/help strings inline.
"""

# ===== User-facing messages =====

MSG_REMIND_USAGE = (
    "Формат:\n"
    "/remind DD.MM HH:MM - текст\n"
    "или без времени:\n"
    "/remind 29.11 - важный звонок\n"
    "или только время:\n"
    "/remind 23:59 - проверить двери\n"
    "или относительное:\n"
    "/remind in 2 hours - текст\n"
    "или повторяющееся:\n"
    "/remind every Monday 10:00 - текст\n"
    "или bulk:\n"
    "/remind\n"
    "- 28.11 12:00 - завтра футбол"
)

MSG_NOT_UNDERSTOOD_PLAIN_TEXT = (
    "Я не понял, нужно ли здесь поставить напоминание.\n"
    "Напиши проще, например:\n"
    "напомни завтра в 18:00 поздравить Саню\n\n"
    "Или командой:\n"
    "/remind завтра 18:00 - поздравить Саню\n\n"
    "Все варианты ремайндеров есть в /help."
)

MSG_GROUP_USERNAME_PREFIX_FORBIDDEN = (
    "В группе нельзя ставить личное напоминание другому человеку через @username в начале команды.\n"
    "Так бот не поймёт, что это личный адресат.\n\n"
    "Если хочешь поставить напоминание в этот чат, используй команду:\n"
    "/remind 02.02 - test\n\n"
    "Свободное «напомни ...» в группе не работает.\n\n"
    "Если хочешь поставить личное напоминание пользователю, напиши боту в личку:\n"
    "/remind @someone 02.02 - test"
)

MSG_GROUP_ALIAS_PREFIX_FORBIDDEN = (
    "В группе нельзя начинать команду с alias.\n\n"
    "Если хочешь поставить напоминание в этот чат, используй команду:\n"
    "/remind 02.02 - текст\n\n"
    "Свободное «напомни ...» в группе не работает.\n\n"
    "Если хочешь поставить напоминание в другой чат через alias, напиши боту в личку:\n"
    "/remind <alias> 02.02 - текст"
)

MSG_INVALID_REMINDER_ID = (
    "Не понял, к какому напоминанию относится эта кнопка. "
    "Открой список заново через /list и попробуй ещё раз."
)
MSG_REMINDER_NOT_FOUND = (
    "Напоминание не найдено. Возможно, оно уже удалено. "
    "Проверь актуальный список через /list."
)
MSG_SOURCE_REMINDER_NOT_FOUND = (
    "Исходное напоминание не найдено. Возможно, оно уже удалено. "
    "Проверь актуальный список через /list."
)
MSG_REMINDER_ALREADY_DELETED_ALERT = "Уже удалено"
MSG_REMINDER_ALREADY_DELETED_TEXT = "Напоминание уже удалено. Проверь актуальный список через /list."
MSG_DELETE_FAILED_SHORT = (
    "Не смог удалить напоминание. Открой список через /list и попробуй ещё раз."
)
MSG_DELETE_FAILED_TEXT = (
    "Не смог удалить напоминание. Возможно, оно уже удалено или кнопка устарела. "
    "Проверь актуальный список через /list."
)
MSG_RESCHEDULE_OPEN_FAILED_TEXT = (
    "Не смог открыть перенос напоминания. Возможно, оно уже удалено или кнопка устарела. "
    "Проверь актуальный список через /list."
)


def msg_recurring_missing_dash(is_private: bool) -> str:
    if is_private:
        return (
            "Не понял повторяющееся напоминание.\n"
            "Для повтора нужен дефис между правилом и текстом.\n\n"
            "Для ежечасного повтора напиши так:\n"
            "/remind every hour - привет\n\n"
            "Или в личке свободным текстом:\n"
            "/remind every hour - привет"
        )

    return (
        "Не понял повторяющееся напоминание.\n"
        "В группе повторяющееся напоминание ставится только командой.\n"
        "Для повтора нужен дефис между правилом и текстом.\n\n"
        "Для ежечасного повтора напиши так:\n"
        "/remind every hour - привет\n\n"
        "Свободное «напомни ...» в группе не работает.\n"
        "Если хочешь поставить это в группу из лички, используй alias группы:\n"
        "/remind <alias> every hour - привет"
    )


def msg_recurring_parse_failed(is_private: bool) -> str:
    if is_private:
        return (
            "Не понял правило повтора.\n\n"
            "Для ежечасного повтора:\n"
            "/remind every hour - привет\n\n"
            "Для еженедельного повтора:\n"
            "/remind every Monday 10:00 - проверить документы"
        )

    return (
        "Не понял правило повтора.\n"
        "В группе повторяющееся напоминание ставится только командой.\n\n"
        "Для ежечасного повтора:\n"
        "/remind every hour - привет\n\n"
        "Для еженедельного повтора:\n"
        "/remind every Monday 10:00 - проверить документы"
    )


MSG_PARSE_DATE_TEXT_FAILED = (
    "Не смог понять дату и текст.\n"
    "Напиши в формате: дата - текст.\n"
    "Например: /remind завтра 18:00 - купить молоко"
)

MSG_UNEXPECTED_CALLBACK_ERROR = (
    "Не смог обработать кнопку. Возможно, сообщение устарело.\n"
    "Открой список заново через /list и попробуй ещё раз."
)

MSG_DELETE_SERIES_FAILED = (
    "Не смог удалить серию. Возможно, она уже удалена или кнопка устарела.\n"
    "Открой список заново через /list и попробуй ещё раз."
)

MSG_UNDO_EXPIRED = (
    "Вернуть уже нельзя: эта кнопка одноразовая или сообщение устарело.\n"
    "Проверь актуальные напоминания через /list."
)

MSG_UNDO_RESTORE_FAILED = (
    "Не смог восстановить напоминание. Возможно, оно уже восстановлено или данные устарели.\n"
    "Проверь актуальные напоминания через /list."
)

MSG_USER_CONTEXT_MISSING = (
    "Не смог определить, кто нажал кнопку.\n"
    "Открой список заново через /list и попробуй ещё раз."
)

MSG_EVENT_DATE_NOT_FOUND = (
    "Я не смог понять дату события из текста.\n"
    "Можно поставить обычное личное напоминание или выбрать время вручную."
)

MSG_UNKNOWN_SELF_REMIND_MODE = (
    "Не понял выбранный режим личного напоминания.\n"
    "Открой варианты заново и попробуй ещё раз."
)

MSG_UNKNOWN_TIME_OPTION = (
    "Не понял выбранный вариант времени.\n"
    "Выбери время заново или нажми «Кастом»."
)

MSG_RESCHEDULE_UNKNOWN_ACTION = (
    "Не понял, как перенести напоминание. Выбери вариант заново или открой список через /list."
)
MSG_RESCHEDULE_BAD_DATETIME = (
    "Не смог понять дату и время для переноса. Выбери дату и время заново."
)
MSG_RESCHEDULE_PAST_TIME = "Это время уже прошло. Выбери другое время."

def msg_after_me_requires_date_and_text(example: str) -> str:
    return "После me нужно указать дату и текст.\n" + example


def msg_user_has_not_started_bot(username: str) -> str:
    return (
        f"Я пока не могу написать {username} в личку, потому что он/она не нажимал(а) Start у бота.\n"
        "Пусть откроет бота и нажмет Start, потом повтори команду."
    )


def msg_after_target_requires_date_and_text(target: str, example: str) -> str:
    return f"После {target} нужно указать дату и текст.\n" + example


# ===== Alias/settings command messages =====

MSG_LINKCHAT_GROUP_ONLY = (
    "Команду /linkchat нужно вызывать в групповом чате, который хочешь привязать."
)

MSG_LINKCHAT_USAGE = (
    "Формат: /linkchat alias\n"
    "Например: /linkchat football"
)

MSG_ALIAS_EMPTY = "Alias не должен быть пустым."

def msg_linkchat_success(alias: str) -> str:
    return (
        f"Ок, запомнил этот чат как '{alias}' для тебя.\n"
        f"Теперь в личке можно писать:\n"
        f"напомни {alias} 28.11 12:00 завтра футбол\n"
        f"или командой:\n"
        f"/remind {alias} 28.11 12:00 - завтра футбол"
    )


MSG_ALIASES_LOAD_USER_FAILED = "Не смог получить user-aliases."
MSG_ALIASES_LOAD_CHAT_FAILED = "Не смог получить chat-aliases."

MSG_ALIASES_EMPTY = (
    "Алиасов пока нет.\n\n"
    "Создать chat-alias: /linkchat football\n"
    "Создать user-alias: /linkuser Наташа @username"
)

MSG_UNALIAS_USAGE = (
    "Использование: /unalias <alias>\n"
    "Пример: /unalias Наташа"
)

def msg_alias_not_found(alias: str) -> str:
    return f"Alias '{alias}' не найден."


def msg_unalias_deleted(alias: str, deleted_parts: list[str]) -> str:
    return f"Удалил alias '{alias}' из: {', '.join(deleted_parts)}."


MSG_RENAMEALIAS_USAGE = (
    "Использование: /renamealias <old> -> <new>\n"
    "Пример: /renamealias Наташа -> Натали"
)

def msg_renamealias_success(old_alias: str, new_alias: str, renamed_parts: list[str]) -> str:
    return f"Переименовал '{old_alias}' -> '{new_alias}' в: {', '.join(renamed_parts)}."


MSG_DEFAULT_TIME_NOT_SET = (
    "Время по умолчанию не задано. Для напоминаний без явно указанного времени бот использует 10:00.\n\n"
    "Поставить: /defaulttime 09:30\n"
    "Сбросить: /defaulttime reset"
)

def msg_default_time_current(formatted_time: str) -> str:
    return (
        f"Текущее время по умолчанию: {formatted_time}\n\n"
        "Изменить: /defaulttime 09:30\n"
        "Сбросить: /defaulttime reset"
    )


MSG_DEFAULT_TIME_RESET = (
    "Ок, сбросил время по умолчанию. Теперь для напоминаний без явно указанного времени бот снова использует 10:00."
)

MSG_DEFAULT_TIME_PARSE_FAILED = "Не понял время. Формат: /defaulttime 09:30"

def msg_default_time_set(formatted_time: str) -> str:
    return f"Ок, время по умолчанию: {formatted_time}."


MSG_LINKUSER_USAGE = (
    "Формат:\n"
    "/linkuser alias @username\n\n"
    "Пример:\n"
    "/linkuser misha @friend"
)

MSG_USER_ALIAS_EMPTY = "Alias не может быть пустым."
MSG_LINKUSER_ALIAS_STARTS_WITH_AT = (
    "Alias не должен начинаться с @. Напиши, например: /linkuser misha @friend"
)
MSG_LINKUSER_USERNAME_REQUIRED = (
    "Вторым аргументом нужен @username. Пример: /linkuser misha @friend"
)

def msg_linkuser_chat_alias_conflict(alias: str) -> str:
    return f"Alias '{alias}' уже занят chat-alias. Выбери другое имя."


def msg_linkuser_target_not_started(username: str) -> str:
    return f"Я пока не могу написать {username}, потому что он/она не нажимал(а) Start у бота."


def msg_linkuser_success(alias: str, username: str) -> str:
    return f"Ок, alias '{alias}' теперь указывает на {username}."

MSG_PAST_DATE_ALERT = "Эта дата уже прошла. Выбери другую."


# ===== Common callback/user-action messages =====

MSG_PICK_DATE = "Выбери дату"
MSG_PICK_TIME = "Выбери время"
MSG_RETURNED_OPTIONS = "Вернул варианты"
MSG_RETURNED_CHOICE = "Вернул выбор"
MSG_RETURNED_EVENT_OPTIONS = "Вернул варианты до события"
MSG_PERSONAL_REMINDER_CREATED = "Личное напоминание создано"

MSG_SELF_REMIND_PRIVATE_START = (
    "Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, "
    "а потом снова нажми кнопку в этом чате"
)

MSG_SELF_REMIND_SENT_TO_PRIVATE = "Отправил варианты в личку"
MSG_SELF_REMIND_CANCELLED = "Ок, личное напоминание не создаю."
MSG_OK_SHORT = "Ок"

MSG_SELF_REMIND_EVENT_DATE_NOT_FOUND_ANSWER = (
    "Не смог понять дату события. Выбери обычное напоминание или время вручную."
)

MSG_SELF_REMIND_EVENT_DATE_NOT_FOUND_TEXT = (
    "Я не смог понять дату события из текста.\n"
    "Ты можешь поставить себе обычный ремайндер:"
)

MSG_DELETE_NOT_FOUND_ALERT = "Не нашел такое напоминание"
MSG_NO_MORE_REMINDERS = "Напоминаний больше нет."
MSG_DELETE_CANCELLED = "Ок, ничего не удалил."
MSG_DELETE_RECURRING_ONE_LABEL = "Удалил ближайшее повторяющееся напоминание"
MSG_DELETE_RECURRING_SERIES_LABEL = "Удалил всю серию"
MSG_UNDO_RESTORING = "Ок, восстанавливаю..."
MSG_UNDO_BUTTON_REMINDER = "↩️ Вернуть ремайндер"
MSG_UNDO_BUTTON_SERIES = "↩️ Вернуть серию"
MSG_UNDO_BUTTON_NEXT_RECURRING = "↩️ Вернуть ближайший"
MSG_CREATED_DELETE_ANSWER = "Удалено"
MSG_RESTORED_NEXT_RECURRING_PREFIX = "Вернул ближайшее повторяющееся напоминание"
MSG_RESTORED_SINGLE_PREFIX = "Вернул"

def msg_created_snoozed(remind_at: str, text: str) -> str:
    return f"Перенёс напоминание на {remind_at}: {text}"


def msg_created_snoozed_answer(remind_at: str) -> str:
    return f"Перенесено на {remind_at}"


def msg_created_deleted(deleted_text: str) -> str:
    return f"Удалил: {deleted_text}"


def msg_delete_recurring_prompt(preview: str) -> str:
    return "Это повторяющееся напоминание. Как удалить?\n\n" + preview


def msg_self_remind_mode_prompt(reminder_text: str, source_chat_title: str) -> str:
    return f'Как тебе напомнить о "{reminder_text}" из чата "{source_chat_title}"?'


def msg_self_remind_regular_prompt(reminder_text: str, source_chat_title: str) -> str:
    return f'Когда напомнить тебе о "{reminder_text}" из чата "{source_chat_title}"?'


def msg_self_remind_event_before_prompt(event_at: str) -> str:
    return (
        f"Я понял, что событие из напоминания состоится {event_at}.\n"
        "За сколько до этого времени напомнить?"
    )


# ===== Remaining user-facing flow messages =====

MSG_DONE_COMPLETED = "Отмечено как завершенное"

MSG_VOICE_TRANSCRIPTION_FAILED = (
    "Не смог распознать голосовое: сервис распознавания сейчас перегружен. "
    "Попробуй еще раз чуть позже или напиши текстом."
)
MSG_VOICE_EMPTY = "Не услышал текст в голосовом."

MSG_THIS_CHAT_SOURCE_TITLE = "этого чата"

def msg_normalized_reminder_prefix(normalized_text: str, created_text: str) -> str:
    return (
        "Я понял:\n"
        f"{normalized_text}\n\n"
        f"{created_text}"
    )


def msg_nudge_unacked(reminder_text: str) -> str:
    return (
        "Ты никак не отреагировал на напоминание.\n"
        "Посмотри и нажми кнопку:\n\n"
        f"{reminder_text}"
    )


def msg_created_for_alias_chat(alias: str, remind_at: str, text: str) -> str:
    return f"Ок, напомню в чате '{alias}' {remind_at}: {text}"


def msg_created_for_other_user(remind_at: str, text: str) -> str:
    return f"Ок, напомню этому человеку {remind_at}: {text}"


def msg_list_user_not_started(username: str) -> str:
    return (
        f"Пользователь {username} еще не писал боту.\n"
        "Он должен сначала нажать Start или поставить любой ремайндер."
    )


def msg_list_alias_not_found_no_aliases(alias: str) -> str:
    return (
        f"Alias '{alias}' не найден.\n"
        "Сначала зайди в нужный чат и выполни /linkchat название.\n"
        f"Или создай user-alias: /linkuser {alias} @username"
    )


def msg_list_alias_not_found_known(alias: str, known_aliases: str) -> str:
    return (
        f"Alias '{alias}' не найден.\n"
        f"Из известных chat-alias: {known_aliases}"
    )


def msg_after_alias_requires_date_and_text_natural(alias: str) -> str:
    return (
        "После alias нужно указать дату и текст.\n"
        f"Пример:\nнапомни {alias} 28.11 12:00 завтра футбол\n"
        f"или командой:\n/remind {alias} 28.11 12:00 - завтра футбол"
    )


def msg_after_alias_requires_date_and_text_command(alias: str) -> str:
    return (
        "После alias нужно указать дату и текст.\n"
        "Пример:\n"
        f"/remind {alias} 28.11 12:00 - завтра футбол"
    )


def msg_alias_does_not_exist(alias: str) -> str:
    return (
        f'Алиаса "{alias}" не существует. '
        "Используй команду без него, если хочешь поставить ремайндер себе, "
        f'или присвой "{alias}" тому, кому нужно, с помощью команд /linkuser или /linkchat. '
        "Подробнее о них можешь прочитать в /help."
    )


__all__ = tuple(
    name
    for name in globals()
    if name.startswith("MSG_") or name.startswith("msg_")
)
