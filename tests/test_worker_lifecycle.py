import asyncio
from types import SimpleNamespace


def test_post_init_starts_and_post_shutdown_cancels_background_workers(main_module, monkeypatch):
    started = []
    cancelled = []

    async def fake_reminders_worker(app):
        started.append("reminders")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append("reminders")
            raise

    async def fake_nudge_worker(app):
        started.append("nudge")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append("nudge")
            raise

    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "migrate_alias_tables_to_owner_scope", lambda: None)
    monkeypatch.setattr(main_module, "reminders_worker", fake_reminders_worker)
    monkeypatch.setattr(main_module, "reminders_nudge_worker", fake_nudge_worker)

    async def scenario():
        app = SimpleNamespace(bot_data={})

        await main_module.post_init(app)
        await asyncio.sleep(0)

        assert set(app.bot_data) == {
            "reminders_worker_task",
            "reminders_nudge_worker_task",
        }
        assert sorted(started) == ["nudge", "reminders"]
        assert all(not task.done() for task in app.bot_data.values())

        await main_module.post_shutdown(app)
        await asyncio.sleep(0)

        assert app.bot_data == {}
        assert sorted(cancelled) == ["nudge", "reminders"]

    asyncio.run(scenario())


def test_post_init_does_not_start_duplicate_background_workers(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "migrate_alias_tables_to_owner_scope", lambda: None)

    async def fake_worker(app):
        await asyncio.Event().wait()

    monkeypatch.setattr(main_module, "reminders_worker", fake_worker)
    monkeypatch.setattr(main_module, "reminders_nudge_worker", fake_worker)

    async def scenario():
        app = SimpleNamespace(bot_data={})

        await main_module.post_init(app)
        first_reminders_task = app.bot_data["reminders_worker_task"]
        first_nudge_task = app.bot_data["reminders_nudge_worker_task"]

        await main_module.post_init(app)

        assert app.bot_data["reminders_worker_task"] is first_reminders_task
        assert app.bot_data["reminders_nudge_worker_task"] is first_nudge_task

        await main_module.post_shutdown(app)

    asyncio.run(scenario())


def test_post_shutdown_ignores_missing_background_workers(main_module):
    async def scenario():
        app = SimpleNamespace(bot_data={})
        await main_module.post_shutdown(app)
        assert app.bot_data == {}

    asyncio.run(scenario())
