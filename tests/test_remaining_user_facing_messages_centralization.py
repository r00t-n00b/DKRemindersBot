import ast
from pathlib import Path

import dkreminders_bot.ui.messages as messages


TARGET_FILES = [
    "dkreminders_bot/callbacks/delete_undo_router.py",
    "dkreminders_bot/commands/list_command_flow.py",
    "dkreminders_bot/commands/remind_target_resolution.py",
    "dkreminders_bot/callbacks/reminder_done_flow.py",
    "dkreminders_bot/workers/reminder_message_proxy.py",
    "dkreminders_bot/workers/reminders_workers.py",
    "dkreminders_bot/callbacks/self_remind_source.py",
    "dkreminders_bot/commands/single_oneoff_reminder.py",
    "dkreminders_bot/integrations/voice_remind_flow.py",
]


def test_remaining_user_facing_messages_are_exported():
    expected = [
        "MSG_DONE_COMPLETED",
        "MSG_VOICE_TRANSCRIPTION_FAILED",
        "MSG_VOICE_EMPTY",
        "MSG_THIS_CHAT_SOURCE_TITLE",
        "msg_normalized_reminder_prefix",
        "msg_nudge_unacked",
        "msg_created_for_alias_chat",
        "msg_created_for_other_user",
        "msg_list_user_not_started",
        "msg_list_alias_not_found_no_aliases",
        "msg_list_alias_not_found_known",
        "msg_after_alias_requires_date_and_text_natural",
        "msg_after_alias_requires_date_and_text_command",
        "msg_alias_does_not_exist",
    ]

    for name in expected:
        assert name in messages.__all__


def test_remaining_dynamic_messages_preserve_current_text():
    assert messages.msg_normalized_reminder_prefix("завтра 10 - тест", "Ок") == (
        "Я понял:\nзавтра 10 - тест\n\nОк"
    )
    assert messages.msg_nudge_unacked("купить молоко") == (
        "Ты никак не отреагировал на напоминание.\n"
        "Посмотри и нажми кнопку:\n\n"
        "купить молоко"
    )
    assert messages.msg_created_for_alias_chat("home", "02.02 12:00", "test") == (
        "Ок, напомню в чате 'home' 02.02 12:00: test"
    )
    assert messages.msg_created_for_other_user("02.02 12:00", "test") == (
        "Ок, напомню этому человеку 02.02 12:00: test"
    )
    assert messages.msg_list_user_not_started("@friend") == (
        "Пользователь @friend еще не писал боту.\n"
        "Он должен сначала нажать Start или поставить любой ремайндер."
    )
    assert messages.msg_list_alias_not_found_no_aliases("work") == (
        "Alias 'work' не найден.\n"
        "Сначала зайди в нужный чат и выполни /linkchat название.\n"
        "Или создай user-alias: /linkuser work @username"
    )
    assert messages.msg_list_alias_not_found_known("work", "home, gym") == (
        "Alias 'work' не найден.\n"
        "Из известных chat-alias: home, gym"
    )
    assert messages.msg_after_alias_requires_date_and_text_natural("home") == (
        "После alias нужно указать дату и текст.\n"
        "Пример:\nнапомни home 28.11 12:00 завтра футбол\n"
        "или командой:\n/remind home 28.11 12:00 - завтра футбол"
    )
    assert messages.msg_after_alias_requires_date_and_text_command("home") == (
        "После alias нужно указать дату и текст.\n"
        "Пример:\n"
        "/remind home 28.11 12:00 - завтра футбол"
    )
    assert messages.msg_alias_does_not_exist("home") == (
        'Алиаса "home" не существует. '
        "Используй команду без него, если хочешь поставить ремайндер себе, "
        'или присвой "home" тому, кому нужно, с помощью команд /linkuser или /linkchat. '
        "Подробнее о них можешь прочитать в /help."
    )


def test_target_modules_do_not_embed_remaining_user_facing_literals():
    forbidden_substrings = [
        "Пользователь ",
        "еще не писал боту",
        "Alias '",
        "Из известных chat-alias",
        "После alias нужно указать дату и текст",
        "Алиаса ",
        "Отмечено как завершенное",
        "Я понял:",
        "Ты никак не отреагировал на напоминание.",
        "Посмотри и нажми кнопку:",
        "этого чата",
        "Ок, напомню в чате",
        "Ок, напомню этому человеку",
        "Не услышал текст в голосовом.",
        "Не смог распознать голосовое",
    ]

    findings = []

    for file_name in TARGET_FILES:
        source = Path(file_name).read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for forbidden in forbidden_substrings:
                    if forbidden in node.value:
                        findings.append((file_name, node.lineno, forbidden, node.value))

    assert findings == []
