from __future__ import annotations
"""Application lifecycle helpers for background workers."""

import asyncio


_DEP_NAMES = (
    "BACKGROUND_WORKER_TASK_KEYS",
    "init_db",
    "logger",
    "migrate_alias_tables_to_owner_scope",
    "reminders_nudge_worker",
    "reminders_worker",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _start_background_worker_impl(application: Application, task_key: str, coro_factory, *, deps) -> asyncio.Task:
    _apply_deps(deps)
    existing_task = application.bot_data.get(task_key)
    if existing_task is not None and (not existing_task.done()):
        return existing_task
    task = asyncio.create_task(coro_factory())
    application.bot_data[task_key] = task
    return task


async def _cancel_background_worker_impl(task: asyncio.Task, *, deps) -> None:
    _apply_deps(deps)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def post_init_impl(application: Application, *, deps) -> None:
    _apply_deps(deps)
    init_db()
    migrate_alias_tables_to_owner_scope()
    _start_background_worker_impl(application, 'reminders_worker_task', lambda: reminders_worker(application), deps=deps)
    _start_background_worker_impl(application, 'reminders_nudge_worker_task', lambda: reminders_nudge_worker(application), deps=deps)
    logger.info('Фоновые worker напоминаний запущены из post_init')


async def post_shutdown_impl(application: Application, *, deps) -> None:
    _apply_deps(deps)
    for task_key in BACKGROUND_WORKER_TASK_KEYS:
        task = application.bot_data.pop(task_key, None)
        if task is not None:
            await _cancel_background_worker_impl(task, deps=deps)
    logger.info('Фоновые worker напоминаний остановлены из post_shutdown')
