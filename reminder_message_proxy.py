"""Message proxy used to route normalized text through /remind flow."""


class NormalizedReminderMessageProxy:
    def __init__(self, original_message, command_text: str, normalized_text: str):
        self._original_message = original_message
        self.text = command_text
        self.normalized_text = normalized_text
        self.voice = getattr(original_message, "voice", None)

    def __getattr__(self, name):
        return getattr(self._original_message, name)

    async def reply_text(self, text, **kwargs):
        await self._original_message.reply_text(
            "Я понял:\n"
            f"{self.normalized_text}\n\n"
            f"{text}",
            **kwargs,
        )
