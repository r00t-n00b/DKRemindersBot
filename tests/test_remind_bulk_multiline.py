import asyncio
from datetime import datetime
from types import SimpleNamespace

from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")


def _mk_private(text: str):
    msg = SimpleNamespace(
        text=text,
        replies=[],
        reply_text=lambda t, **k: msg.replies.append(t),
    )
    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=msg,
        effective_user=SimpleNamespace(id=123, username="u"),
    )
    ctx = SimpleNamespace(user_data={}, args=[])
    return msg, upd, ctx


def test_remind_bulk_multiline_preserves_newlines_and_creates(main_module, monkeypatch):
    m = main_module
    now = datetime(2026, 1, 31, 16, 21, tzinfo=TZ)

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append(
            {
                "chat_id": chat_id,
                "text": text,
                "remind_at": remind_at,
                "created_by": created_by,
                "template_id": template_id,
            }
        )
        return len(created)

    monkeypatch.setattr(m, "get_now", lambda: now)
    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    # IMPORTANT: multiline payload after /remind
    msg, upd, ctx = _mk_private(
        "/remind Каталония\n"
        "12.02 12:00 - завтра в 20:45 футбол\n"
        "17.02 12:00 - завтра в 20:45 футбол\n"
        "21.02 12:00 - завтра в 18:00 футбол\n"
    )

    # Чтобы не зависеть от алиасов - пусть "Каталония" не будет распознана как алиас,
    # в этом тесте мы проверяем именно multiline bulk (создание 3)
    # Если у тебя первая строка в bulk трактуется как алиас - см. следующий тест.
    asyncio.run(m.remind_command(upd, ctx))

    assert len(created) == 3
    assert all("футбол" in r["text"] for r in created)
    assert msg.replies
    assert "Создано" in msg.replies[-1]


def test_remind_bulk_first_line_as_alias_routes_to_alias_chat(main_module, monkeypatch):
    m = main_module
    now = datetime(2026, 1, 31, 16, 21, tzinfo=TZ)

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append({"chat_id": chat_id, "text": text, "remind_at": remind_at})
        return len(created)

    # Имитируем, что первая строка - alias, и он резолвится в чат 777
    monkeypatch.setattr(m, "get_now", lambda: now)
    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)
    monkeypatch.setattr(m, "get_chat_id_by_alias", lambda alias: 777 if alias == "Каталония" else None)

    msg, upd, ctx = _mk_private(
        "/remind Каталония\n"
        "12.02 12:00 - матч 1\n"
        "17.02 12:00 - матч 2\n"
        "21.02 12:00 - матч 3\n"
    )

    asyncio.run(m.remind_command(upd, ctx))

    assert len(created) == 3
    assert all(r["chat_id"] == 777 for r in created)
    assert msg.replies
    assert "Создано" in msg.replies[-1]