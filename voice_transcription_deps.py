"""Dependency factory for _build_voice_transcription_deps."""

import builtins
from types import SimpleNamespace


VOICE_TRANSCRIPTION_DEP_SPECS = (
    ("_format_known_aliases_for_voice_prompt", "_format_known_aliases_for_voice_prompt"),
    ("_gemini_transcribe_audio_with_retries", "_gemini_transcribe_audio_with_retries"),
    ("download_telegram_file_bytes", "download_telegram_file_bytes"),
    ("genai", "genai"),
    ("genai_types", "genai_types"),
    ("os", "os"),
)


def _resolve_dep(namespace, source_name: str):
    if source_name in namespace:
        return namespace[source_name]
    if hasattr(builtins, source_name):
        return getattr(builtins, source_name)
    raise KeyError(source_name)


def build_voice_transcription_deps(namespace) -> SimpleNamespace:
    values = {}
    missing = []

    for attr_name, source_name in VOICE_TRANSCRIPTION_DEP_SPECS:
        try:
            values[attr_name] = _resolve_dep(namespace, source_name)
        except KeyError:
            missing.append(source_name)

    if missing:
        raise KeyError(f"Missing deps for build_voice_transcription_deps: {', '.join(missing)}")

    return SimpleNamespace(**values)
