
"""Voice flow exception types."""

class VoiceProcessingError(Exception):

    """Base class for voice processing errors."""

class VoiceTelegramFileError(VoiceProcessingError):

    """Telegram voice file metadata/download failed."""

class VoiceTranscriptionServiceError(VoiceProcessingError):

    """Speech-to-text service failed after Telegram file was downloaded."""



class VoiceRecipientUnclearError(VoiceProcessingError):
    """A proposed external recipient is not supported by the spoken request."""
