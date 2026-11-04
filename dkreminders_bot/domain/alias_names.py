"""New settings aliases must be routable as the first token of /remind."""

import re
import unicodedata

from dkreminders_bot.ui.messages import ALIAS_MENU_NOTICES as N
from dkreminders_bot.utils.command_text import first_token_looks_like_reminder_start


def alias_key(value):
    return unicodedata.normalize("NFC", value).casefold()


def validate_alias_name(raw):
    name = unicodedata.normalize("NFC", (raw or "").strip())
    if not re.fullmatch(r"[^\W\d_][\w-]{0,63}", name, flags=re.UNICODE):
        raise ValueError(N["invalid"])
    if first_token_looks_like_reminder_start(name) or name.casefold() in {"me", "remind", "напомни", "напоминай", "напомнить"}:
        raise ValueError(N["reserved"])
    return name
