import asyncio
from types import SimpleNamespace


def _run_remind_and_capture(main_module, text, monkeypatch):
    replies = []

    msg = SimpleNamespace(
        text=text,
        reply_text=lambda t, **k: replies.append(t),
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123, username="u", first_name="U", last_name="L"),
    )
    ctx = SimpleNamespace(user_data={})

    called = {"add_reminder": 0}

    def fake_add_reminder(*args, **kwargs):
        called["add_reminder"] += 1
        return 1

    monkeypatch.setattr(main_module, "add_reminder", fake_add_reminder)

    asyncio.run(main_module.remind_command(upd, ctx))

    return replies, called


def test_remind_empty_input_shows_help_and_creates_nothing(main_module, monkeypatch):
    replies, called = _run_remind_and_capture(main_module, "/remind", monkeypatch)

    assert replies
    text = "\n".join(replies).lower()
    assert "формат" in text or "format" in text
    assert called["add_reminder"] == 0


def test_remind_empty_input_with_spaces_shows_help_and_creates_nothing(main_module, monkeypatch):
    replies, called = _run_remind_and_capture(main_module, "/remind   ", monkeypatch)

    assert replies
    text = "\n".join(replies).lower()
    assert "формат" in text or "format" in text
    assert called["add_reminder"] == 0