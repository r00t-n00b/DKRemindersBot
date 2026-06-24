import asyncio
from types import SimpleNamespace

import app_lifecycle


TARGETS = [
    "_start_background_worker",
    "_cancel_background_worker",
    "post_init",
    "post_shutdown",
]


def test_app_lifecycle_wrappers_in_main_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    for name in TARGETS:
        matches = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]

        assert len(matches) == 1

        node = matches[0]
        node_source = ast.get_source_segment(source, node)

        assert f"{name}_impl(" in node_source
        assert "deps=_build_app_lifecycle_deps()" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_app_lifecycle_module_contains_impls_and_no_main_import():
    source = open("app_lifecycle.py").read()

    assert "def _start_background_worker_impl(" in source
    assert "async def _cancel_background_worker_impl(" in source
    assert "async def post_init_impl(" in source
    assert "async def post_shutdown_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_start_background_worker_reuses_existing_task():
    calls = []

    async def sleeper():
        calls.append("started")
        await asyncio.sleep(10)

    async def run():
        app = SimpleNamespace(bot_data={})
        deps = SimpleNamespace(
            BACKGROUND_WORKER_TASK_KEYS=("a", "b"),
            init_db=lambda: None,
            logger=SimpleNamespace(info=lambda *args, **kwargs: None),
            migrate_alias_tables_to_owner_scope=lambda: None,
            reminders_nudge_worker=None,
            reminders_worker=None,
        )

        task1 = app_lifecycle._start_background_worker_impl(app, "task", sleeper, deps=deps)
        task2 = app_lifecycle._start_background_worker_impl(app, "task", sleeper, deps=deps)

        assert task1 is task2

        await asyncio.sleep(0)

        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass

    asyncio.run(run())

    assert calls == ["started"]


def test_cancel_background_worker_swallows_cancelled_error():
    async def sleeper():
        await asyncio.sleep(10)

    async def run():
        task = asyncio.create_task(sleeper())
        await app_lifecycle._cancel_background_worker_impl(
            task,
            deps=SimpleNamespace(
                BACKGROUND_WORKER_TASK_KEYS=(),
                init_db=lambda: None,
                logger=SimpleNamespace(info=lambda *args, **kwargs: None),
                migrate_alias_tables_to_owner_scope=lambda: None,
                reminders_nudge_worker=None,
                reminders_worker=None,
            ),
        )
        assert task.cancelled()

    asyncio.run(run())


def test_post_init_runs_db_migration_and_starts_workers(monkeypatch):
    calls = []

    async def worker(app):
        calls.append(("worker", app))
        await asyncio.sleep(10)

    async def nudge_worker(app):
        calls.append(("nudge", app))
        await asyncio.sleep(10)

    async def run():
        app = SimpleNamespace(bot_data={})
        deps = SimpleNamespace(
            BACKGROUND_WORKER_TASK_KEYS=("reminders_worker_task", "reminders_nudge_worker_task"),
            init_db=lambda: calls.append("init"),
            logger=SimpleNamespace(info=lambda *args, **kwargs: calls.append(("log", args))),
            migrate_alias_tables_to_owner_scope=lambda: calls.append("migrate"),
            reminders_worker=worker,
            reminders_nudge_worker=nudge_worker,
        )

        await app_lifecycle.post_init_impl(app, deps=deps)

        assert "init" in calls
        assert "migrate" in calls
        assert "reminders_worker_task" in app.bot_data
        assert "reminders_nudge_worker_task" in app.bot_data

        for task in app.bot_data.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(run())


def test_post_shutdown_cancels_known_workers():
    async def sleeper():
        await asyncio.sleep(10)

    async def run():
        app = SimpleNamespace(bot_data={
            "a": asyncio.create_task(sleeper()),
            "b": asyncio.create_task(sleeper()),
            "other": "untouched",
        })
        deps = SimpleNamespace(
            BACKGROUND_WORKER_TASK_KEYS=("a", "b"),
            init_db=lambda: None,
            logger=SimpleNamespace(info=lambda *args, **kwargs: None),
            migrate_alias_tables_to_owner_scope=lambda: None,
            reminders_nudge_worker=None,
            reminders_worker=None,
        )

        await app_lifecycle.post_shutdown_impl(app, deps=deps)

        assert "a" not in app.bot_data
        assert "b" not in app.bot_data
        assert app.bot_data["other"] == "untouched"

    asyncio.run(run())
