
"""Voice flow exception types."""

class VoiceProcessingError(Exception):

    """Base class for voice processing errors."""

class VoiceTelegramFileError(VoiceProcessingError):

    """Telegram voice file metadata/download failed."""

class VoiceTranscriptionServiceError(VoiceProcessingError):

    """Speech-to-text service failed after Telegram file was downloaded."""

