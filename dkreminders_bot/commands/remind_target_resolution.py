"""Resolve /remind target chat, aliases, and normalized reminder text."""

from dkreminders_bot.ui.messages import msg_after_alias_requires_date_and_text_command, msg_after_alias_requires_date_and_text_natural, msg_alias_does_not_exist

from dataclasses import dataclass
from typing import Optional


@dataclass
class RemindTargetResolution:
    aborted: bool
    raw_args: str
    had_newline: bool
    target_chat_id: int
    used_alias: Optional[str]


async def resolve_remind_target_and_args(
    *,
    is_private: bool,
    raw_args: str,
    had_newline: bool,
    chat,
    user,
    message,
    now,
    default_time,
    safe_reply,
    logger,
    strip_first_token_from_first_line,
    first_token_looks_like_reminder_start,
    get_user_chat_id_by_username,
    get_user_alias_chat_id_for_user,
    get_chat_id_by_alias_for_user,
    parse_with_optional_default_time,
    parse_date_time_smart,
    upsert_user_chat,
    msg_after_me_requires_date_and_text,
    msg_user_has_not_started_bot,
    msg_after_target_requires_date_and_text,
) -> RemindTargetResolution:
    target_chat_id = chat.id
    used_alias: Optional[str] = None

    # В личке допускаем slack-style "/remind me ..."
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip().lower()

            if first_token == "me":
                raw_args = strip_first_token_from_first_line(raw_args, first_token)

                logger.info(
                    "REMIND me-stripped chat_id=%s user_id=%s raw_args=%r",
                    chat.id,
                    user.id,
                    raw_args,
                )

                if not raw_args:
                    await safe_reply(
                        message,
                        msg_after_me_requires_date_and_text("Пример: /remind me on Tuesday - алкоголь под КС"),
                    )
                    return RemindTargetResolution(True, raw_args, had_newline, target_chat_id, used_alias)

    # В личке допускаем @username первым словом / первой строкой
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip()
            if first_token.lower() == "me":
                raw_args = strip_first_token_from_first_line(raw_args, first_token)

                if not raw_args:
                    await safe_reply(
                        message,
                        msg_after_me_requires_date_and_text("Пример: /remind me at 18:00 - купить молоко"),
                    )
                    return RemindTargetResolution(True, raw_args, had_newline, target_chat_id, used_alias)

            if first_token.startswith("@") and len(first_token) > 1:
                target = get_user_chat_id_by_username(first_token)
                if target is None:
                    await safe_reply(
                        message,
                        msg_user_has_not_started_bot(first_token),
                    )
                    return RemindTargetResolution(True, raw_args, had_newline, target_chat_id, used_alias)

                raw_args = strip_first_token_from_first_line(raw_args, first_token)

                if not raw_args:
                    await safe_reply(
                        message,
                        msg_after_target_requires_date_and_text(
                            first_token,
                            f"Пример: /remind {first_token} tomorrow 10:00 - привет",
                        ),
                    )
                    return RemindTargetResolution(True, raw_args, had_newline, target_chat_id, used_alias)

                target_chat_id = target
                used_alias = first_token

    # Если пользователь пишет "/remind напомни ...", это не alias "напомни",
    # а вложенный командный префикс. Убираем его до alias-routing.
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip() if raw_args else ""
        nested_tokens = first_line.split(maxsplit=1)
        if nested_tokens:
            nested_first = nested_tokens[0].strip(" ,.!?:;").lower()
            if nested_first in {"напомни", "напомнить", "remind"} and len(nested_tokens) == 2:
                rest_first_line = nested_tokens[1].strip()
                rest_lines = "\n".join(raw_args.splitlines()[1:])

                parts = []
                if rest_first_line:
                    parts.append(rest_first_line)
                if rest_lines.strip():
                    parts.append(rest_lines)

                raw_args = "\n".join(parts).strip()
                had_newline = "\n" in raw_args

    # В личке допускаем alias первым словом / первой строкой
    if is_private:
        first_line = raw_args.splitlines()[0].lstrip()
        if first_line and not first_line.startswith("-"):
            first_token = first_line.split(maxsplit=1)[0].strip()

            if first_token and first_token.lower() == "me":
                raw_args = strip_first_token_from_first_line(raw_args, first_token)

                if not raw_args:
                    await safe_reply(
                        message,
                        msg_after_me_requires_date_and_text("Пример: /remind me at 18:00 - купить молоко"),
                    )
                    return RemindTargetResolution(True, raw_args, had_newline, target_chat_id, used_alias)

            # alias != @username и alias != me (эти кейсы обработаны выше)
            elif first_token and not first_token.startswith("@"):
                # Не трогаем обычные команды, которые уже начинаются с даты/времени/recurring.
                # Важно: используем общий helper, чтобы maybe_split_alias_first_token()
                # и remind_command() не расходились по списку smart-prefixes.
                if not first_token_looks_like_reminder_start(first_token):
                    raw_args_without_first_token = strip_first_token_from_first_line(raw_args, first_token)

                    user_alias_chat_id = get_user_alias_chat_id_for_user(first_token, user.id)
                    if user_alias_chat_id is not None:
                        raw_args = raw_args_without_first_token
                        target_chat_id = user_alias_chat_id
                        used_alias = None

                        if not raw_args:
                            await safe_reply(
                                message,
                                msg_after_alias_requires_date_and_text_natural(first_token),
                            )
                            return RemindTargetResolution(True, raw_args, had_newline, target_chat_id, used_alias)
                    else:
                        alias_chat_id = get_chat_id_by_alias_for_user(first_token, user.id)
                        if alias_chat_id is not None:
                            raw_args = raw_args_without_first_token
                            target_chat_id = alias_chat_id
                            used_alias = first_token

                            if not raw_args:
                                await safe_reply(
                                    message,
                                    msg_after_alias_requires_date_and_text_command(used_alias),
                                )
                                return RemindTargetResolution(True, raw_args, had_newline, target_chat_id, used_alias)
                        elif raw_args_without_first_token and "\n" not in raw_args:
                            try:
                                parse_with_optional_default_time(
                                    parse_date_time_smart,
                                    raw_args_without_first_token,
                                    now,
                                    default_time=default_time,
                                )
                            except Exception:
                                pass
                            else:
                                await safe_reply(
                                    message,
                                    msg_alias_does_not_exist(first_token),
                                )
                                return RemindTargetResolution(True, raw_args, had_newline, target_chat_id, used_alias)

    # если человек пишет боту в личке - запомним его chat_id
    if is_private:
        upsert_user_chat(
            user_id=user.id,
            chat_id=chat.id,
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
        )

    logger.info(
        "REMIND normalized chat_id=%s target_chat_id=%s used_alias=%s raw_args=%r had_newline=%s",
        chat.id,
        target_chat_id,
        used_alias,
        raw_args,
        had_newline,
    )

    return RemindTargetResolution(False, raw_args, had_newline, target_chat_id, used_alias)
