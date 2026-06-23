"""Voice prompt helpers for known aliases."""

from typing import Callable, Iterable, Tuple


def format_known_aliases_for_voice_prompt(
    created_by: int,
    *,
    get_all_user_aliases: Callable[[int], Iterable[Tuple[str, int]]],
    get_all_aliases: Callable[[int], Iterable[Tuple[str, int, str]]],
    logger,
) -> str:
        """
        Собираем известные aliases текущего пользователя для Gemini voice-normalization.
    
        Gemini не должен видеть чужие aliases и не должен придумывать aliases из воздуха.
        """
        user_aliases = []
        chat_aliases = []
    
        try:
            user_aliases = [a for a, _chat_id in get_all_user_aliases(created_by)]
        except Exception:
            logger.exception("Не смог получить user aliases для voice prompt")
            user_aliases = []
    
        try:
            chat_aliases = [a for a, _chat_id, _title in get_all_aliases(created_by)]
        except Exception:
            logger.exception("Не смог получить chat aliases для voice prompt")
            chat_aliases = []
    
        lines = [
            "Known aliases. Use these only if the spoken target clearly matches one of them.",
            "",
            "Known user aliases:",
        ]
    
        if user_aliases:
            for alias in sorted(set(user_aliases), key=str.lower):
                lines.append(f"- {alias}")
        else:
            lines.append("- none")
    
        lines.extend(["", "Known chat aliases:"])
    
        if chat_aliases:
            for alias in sorted(set(chat_aliases), key=str.lower):
                lines.append(f"- {alias}")
        else:
            lines.append("- none")
    
        return "\n".join(lines)
