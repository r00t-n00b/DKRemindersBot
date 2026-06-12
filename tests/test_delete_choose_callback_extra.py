import asyncio
from types import SimpleNamespace


def test_delete_choose_out_of_range_answers(main_module):
    answered = {"ok": False}

    async def fake_answer(*a, **k):
        answered["ok"] = True

    cbq = SimpleNamespace(
        data="choose:2",
        answer=fake_answer,
        message=SimpleNamespace(reply_text=lambda *a, **k: None),
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={"list_ids": [111], "list_chat_id": 1})

    asyncio.run(main_module.delete_choose_callback(upd, ctx))

    assert answered["ok"] is True


def test_delete_callback_out_of_range_answers(main_module):
    answered = {"ok": False}

    async def fake_answer(*a, **k):
        answered["ok"] = True

    cbq = SimpleNamespace(
        data="del:9",
        answer=fake_answer,
        message=SimpleNamespace(reply_text=lambda *a, **k: None),
    )
    upd = SimpleNamespace(callback_query=cbq)
    ctx = SimpleNamespace(user_data={"list_ids": [111], "list_chat_id": 1})

    asyncio.run(main_module.delete_callback(upd, ctx))

    assert answered["ok"] is True