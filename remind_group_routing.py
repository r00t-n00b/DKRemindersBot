"""Group /remind routing guards."""


async def reject_group_remind_target_prefix_if_needed(
    *,
    is_private: bool,
    raw_args: str,
    user_id: int,
    message,
    safe_reply,
    get_chat_id_by_alias_for_user,
    msg_group_username_prefix_forbidden: str,
    msg_group_alias_prefix_forbidden: str,
) -> tuple[bool, str]:
    if is_private:
        return False, raw_args

    raw_args = raw_args.strip()

    # Запрет только для single-line: bulk оставляем как есть.
    if raw_args and "\n" not in raw_args:
        parts = raw_args.split(maxsplit=1)
        if parts:
            first_token = parts[0].strip()

            if first_token.startswith("@") and len(first_token) > 1:
                await safe_reply(
                    message,
                    msg_group_username_prefix_forbidden,
                )
                return True, raw_args

            try:
                alias_chat_id = get_chat_id_by_alias_for_user(first_token, user_id)
            except Exception:
                alias_chat_id = None

            if alias_chat_id is not None:
                await safe_reply(
                    message,
                    msg_group_alias_prefix_forbidden,
                )
                return True, raw_args

    return False, raw_args
