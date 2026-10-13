"""Message proxy used to route normalized text through /remind flow."""

from dkreminders_bot.ui.messages import msg_normalized_reminder_prefix


class NormalizedReminderMessageProxy:
    def __init__(
        self,
        original_message,
        command_text: str,
        normalized_text: str,
        *,
        suppress_normalized_prefix: bool = False,
    ):
        self._original_message = original_message
        self.text = command_text
        self.normalized_text = normalized_text
        self.voice = getattr(original_message, "voice", None)
        self.suppress_normalized_prefix = suppress_normalized_prefix

    def __getattr__(self, name):
        return getattr(self._original_message, name)

    async def reply_text(self, text, **kwargs):
        if self.suppress_normalized_prefix:
            return await self._original_message.reply_text(text, **kwargs)

        return await self._original_message.reply_text(
            msg_normalized_reminder_prefix(self.normalized_text, text),
            **kwargs,
        )
