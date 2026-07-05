import asyncio
from types import SimpleNamespace

import main
import dkreminders_bot.integrations.voice_transcription as voice_transcription


def test_main_transcribe_voice_message_delegates_to_impl(monkeypatch):
    calls = []

    async def fake_impl(update, context, deps):
        calls.append((update, context, deps))
        return "recognized text"

    monkeypatch.setattr(main, "transcribe_voice_message_impl", fake_impl)

    update = SimpleNamespace()
    context = SimpleNamespace()

    result = asyncio.run(main.transcribe_voice_message(update, context))

    assert result == "recognized text"
    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context


def test_transcribe_voice_message_wrapper_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    wrappers = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "transcribe_voice_message"
    ]

    assert len(wrappers) == 1

    wrapper = wrappers[0]
    wrapper_source = ast.get_source_segment(source, wrapper)

    assert "transcribe_voice_message_impl(update, context, _build_voice_transcription_deps())" in wrapper_source
    assert wrapper.end_lineno - wrapper.lineno + 1 <= 3


def test_voice_transcription_module_contains_impl_and_no_main_import():
    source = open("dkreminders_bot/integrations/voice_transcription.py").read()

    assert "async def transcribe_voice_message_impl(" in source
    assert "_apply_deps(deps)" in source
    assert "import main" not in source
    assert "from main import" not in source


def test_voice_transcription_module_exports_impl():
    assert hasattr(voice_transcription, "transcribe_voice_message_impl")
