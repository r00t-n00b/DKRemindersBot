import ast
from pathlib import Path

import dkreminders_bot.ui.messages as messages


def test_alias_settings_messages_are_exported():
    expected = [
        "MSG_LINKCHAT_GROUP_ONLY",
        "MSG_LINKCHAT_USAGE",
        "MSG_ALIAS_EMPTY",
        "msg_linkchat_success",
        "MSG_ALIASES_LOAD_USER_FAILED",
        "MSG_ALIASES_LOAD_CHAT_FAILED",
        "MSG_ALIASES_EMPTY",
        "MSG_UNALIAS_USAGE",
        "msg_alias_not_found",
        "msg_unalias_deleted",
        "MSG_RENAMEALIAS_USAGE",
        "msg_renamealias_success",
        "MSG_DEFAULT_TIME_NOT_SET",
        "msg_default_time_current",
        "MSG_DEFAULT_TIME_RESET",
        "MSG_DEFAULT_TIME_PARSE_FAILED",
        "msg_default_time_set",
        "MSG_LINKUSER_USAGE",
        "MSG_USER_ALIAS_EMPTY",
        "MSG_LINKUSER_ALIAS_STARTS_WITH_AT",
        "MSG_LINKUSER_USERNAME_REQUIRED",
        "msg_linkuser_chat_alias_conflict",
        "msg_linkuser_target_not_started",
        "msg_linkuser_success",
    ]

    for name in expected:
        assert name in messages.__all__


def test_alias_settings_dynamic_messages_preserve_current_text():
    assert messages.msg_linkchat_success("football") == (
        "Ок, запомнил этот чат как 'football' для тебя.\n"
        "Теперь в личке можно писать:\n"
        "напомни football 28.11 12:00 завтра футбол\n"
        "или командой:\n"
        "/remind football 28.11 12:00 - завтра футбол"
    )

    assert messages.msg_alias_not_found("Наташа") == "Alias 'Наташа' не найден."
    assert messages.msg_unalias_deleted("Наташа", ["user-alias", "chat-alias"]) == (
        "Удалил alias 'Наташа' из: user-alias, chat-alias."
    )
    assert messages.msg_renamealias_success("Наташа", "Натали", ["user-alias"]) == (
        "Переименовал 'Наташа' -> 'Натали' в: user-alias."
    )
    assert messages.msg_default_time_current("09:30") == (
        "Текущее время по умолчанию: 09:30\n\n"
        "Изменить: /defaulttime 09:30\n"
        "Сбросить: /defaulttime reset"
    )
    assert messages.msg_default_time_set("09:30") == "Ок, время по умолчанию: 09:30."
    assert messages.msg_linkuser_chat_alias_conflict("misha") == (
        "Alias 'misha' уже занят chat-alias. Выбери другое имя."
    )
    assert messages.msg_linkuser_target_not_started("@friend") == (
        "Я пока не могу написать @friend, потому что он/она не нажимал(а) Start у бота."
    )
    assert messages.msg_linkuser_success("misha", "@friend") == (
        "Ок, alias 'misha' теперь указывает на @friend."
    )


def test_alias_settings_commands_do_not_embed_direct_safe_reply_literals():
    source = Path("dkreminders_bot/settings/alias_settings_commands.py").read_text()
    tree = ast.parse(source)

    cyrillic = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")

    findings = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr

        if name != "safe_reply":
            continue

        for arg in node.args[1:]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and any(ch in arg.value for ch in cyrillic):
                findings.append((arg.lineno, arg.value))

            if isinstance(arg, ast.JoinedStr):
                text = "".join(
                    part.value
                    for part in arg.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
                if any(ch in text for ch in cyrillic):
                    findings.append((arg.lineno, text))

    assert findings == []
