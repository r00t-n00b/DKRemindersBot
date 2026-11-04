# DK Reminders Bot

Telegram reminder bot deployed on Fly.io.

The bot supports one-off and recurring reminders, natural-language text and voice input, reply/forward-context reminders, snooze/reschedule/done flows, personal self-reminders from group chats, group and user aliases, timezone-aware scheduling, and undo for delete actions.

Reply/forward-context reminders retain their source message through delivery, private-chat nudges, and repeated snooze (quick buttons or custom time). Notifications reply to the source only when it belongs to the destination chat. If the source was deleted, delivery is allowed without a reply.

## Personal settings

`/settings` opens a private inline menu for default time, timezone, reminder nudges, aliases, and `/list`. Group requests show no personal settings. Older timezone/default-time buttons remain supported.

- Default time accepts presets and custom `HH:MM` input (for example, `08:45`).
- Timezone accepts presets, location, a limited offline city-alias list, and any available IANA timezone such as `America/New_York`. Search results require confirmation; changing timezone retains the migration question for active reminders.
- Custom values are replies to a specific bot prompt. Unrelated messages still follow the ordinary reminder flow; `/cancel` closes the pending settings input.
- Nudge schedules contain 1–20 independently editable intervals, each from one minute to 365 days. Defaults are `[20, 60, 240, 720]` minutes between successful sends. Presets and custom values such as `45 мин`, `1 ч 30 мин`, and `2 дня` are supported.
- A schedule is edited as a draft and saved atomically. Sessions, drafts, and pending prompts survive restart and expire after 24 hours; stale buttons cannot change newer screens.
- Preferences belong to the private recipient, including reminders created by someone else. Each primary delivery snapshots its schedule. Schedule changes apply to later deliveries; disabling stops pending nudges immediately, and re-enabling only allows nudges for new primary deliveries.
- Snooze stops the old reminder's cycle; its next primary delivery uses current preferences. Groups still receive no nudges. Failed sends do not spend a repeat, and downtime does not produce a catch-up burst.

Migration adds nudge preference/snapshot fields and the `settings_sessions` table without rewriting existing reminders or series. Legacy delivered rows retain the default schedule. See `docs/SETTINGS_DESIGN.md` for the agreed UX and boundaries.

## Interval recurrence modes

Creating an interval series (for example, `/remind every 30 minutes - stretch` or «напоминай каждые полчаса размяться») asks **По расписанию** or **После выполнения** before creating any reminders. Cancel creates nothing. The choice survives a restart and expires after 24 hours.

- **По расписанию:** the existing schedule behavior.
- **После выполнения:** the next reminder is scheduled one interval after Done; no new occurrence is created while the current one is unfinished. Snooze moves the current occurrence and retains its series/source.
- Calendar schedules such as every day at 09:00 and existing series keep their previous behavior.
- Done/Snooze are transactional and reject duplicate actions. In private chats the recipient acts; in groups the series creator acts. Nudges remain private-only.
- Explicitly skipping one occurrence starts the next interval from the skip time. Deleting a series stops it; undo preserves the mode.
- Minutes/hours/days/weeks measure elapsed time across timezone/DST changes. Months use the series timezone and clamp to the last day of the month.

Pending choices use the additive `recurrence_choices` table. The series mode is stored in the existing template payload; existing rows are not rewritten.

## Current architecture

`main.py` is intentionally kept as the composition root:
- imports configuration and modules;
- builds dependency namespaces;
- exposes compatibility wrappers used by older tests and handler wiring;
- registers Telegram command/callback/message handlers;
- starts the application and background workers;
- supervises Telegram polling so transient DNS/network startup failures are retried instead of killing the process;
- starts an optional external liveness heartbeat when `HEARTBEAT_URL` is configured.

Business logic is split into modules:
- reminder parsing and command flow: `remind_command_router.py`, `remind_target_resolution.py`, `remind_dispatch.py`, `plain_text_remind_flow.py`, `plain_text_gemini_normalization.py`, `plain_text_local_normalization.py`, `voice_remind_flow.py`;
- callback flows: `reminder_callback_router.py`, `callback_simple_flows.py`, `created_action_callbacks.py`, `created_delete_router.py`, `created_snooze_router.py`, `delete_undo_router.py`;
- snooze/self-remind helpers: `snooze_*`, `self_remind_*`;
- storage: `storage_schema.py`, `storage_read.py`, `storage_write.py`, `storage_aliases.py`, `storage_delete_restore.py`, `storage_user_chats.py`, `storage_user_settings.py`, `storage_nudges.py`;
- presentation and messages: `presentation.py`, `messages.py`, `command_messages.py`.

User-facing error/status messages should be centralized in `messages.py`, except:
- `/start` and `/help` texts in `command_messages.py`;
- list/reminder formatting in `presentation.py`;
- Gemini prompts and text-normalization prompts, which are not direct user-facing responses.

## Tests

Run the full local test suite:

```bash
python3.11 -m pytest -q
```

Current expected result:

```text
1491 passed, 1 skipped
```

For feature work, tests should cover the full user/business path, not only isolated helpers:
- callback data generated by buttons;
- callback data matching registered handler patterns;
- actual handler invocation;
- absence of generic/unknown-option errors;
- expected user-visible response;
- expected side effects;
- negative/error paths;
- ambiguity/precedence cases where formats or handlers overlap.

GitHub Actions runs the pytest suite on every push to `main` and on pull requests.

The GitHub Actions workflow is test-only. It must not deploy to Fly.io.

## Test quality checks

Useful local checks:

```bash
python3.11 -m pytest -q
python3.11 -m pytest --collect-only -q
```

Obvious useless tests should not exist:
- empty `test_*.py` files;
- files without `test_` functions;
- tests with only `pass` or `...`;
- `assert True` / `assert 1 == 1`;
- duplicate top-level `test_*` definitions in the same file.

Some smoke/contract tests may look small but are intentionally useful, especially for:
- handler wiring;
- callback pattern contracts;
- import-cycle prevention;
- wrapper compatibility after extraction.

## Deploy

Production deploy is manual and must include a database backup before `fly deploy`.

Use this standard deploy block for production changes, adding both production files and relevant tests changed by the feature:

```bash
git status --short
git add <production files and relevant tests>
git commit -m "<meaningful message>"
git push
fly ssh console -a dk-reminders-bot -C 'sh -c "ts=$(date +%Y%m%d-%H%M%S); if [ -f /data/reminders.db ]; then cp /data/reminders.db /data/reminders-$ts.db.bak; else echo reminders.db not found, skip backup; fi"'
fly deploy
```

For docs-only or tests-only changes, deploy is not needed.

If code and tests were already committed and pushed separately, only run the backup and deploy commands:

```bash
fly ssh console -a dk-reminders-bot -C 'sh -c "ts=$(date +%Y%m%d-%H%M%S); if [ -f /data/reminders.db ]; then cp /data/reminders.db /data/reminders-$ts.db.bak; else echo reminders.db not found, skip backup; fi"'
fly deploy
```

## Post-deploy smoke test

After deploy, check status and logs:

```bash
fly status -a dk-reminders-bot
fly logs -a dk-reminders-bot
```

Basic Telegram smoke test:

```text
/remind через минуту - smoke
```

Expected: reminder is created and delivered without traceback in logs.

## Database and migration discipline

Production data is stored in SQLite on Fly persistent storage.

Before any change involving schemas, primary keys, ownership/scoping, migration logic, or data access filters:
- inspect current schema and row counts;
- create an explicit backup;
- prefer non-destructive migrations;
- preserve existing production rows;
- verify row counts/schema after migration.

Do not drop, ignore, or rewrite production rows just because ownership data is missing unless the consequences were explicitly reviewed and accepted.

## Reliability and production monitoring

The production bot runs on Fly.io as a polling worker. It does not expose an HTTP service.

Transient Telegram/DNS/network startup failures are handled by a polling supervisor with bounded retry backoff, so temporary connectivity failures do not cause a rapid crash/restart loop.

Production also supports an external heartbeat through the `HEARTBEAT_URL` Fly secret. The current production setup uses Healthchecks to detect loss of heartbeat and send DOWN/UP notifications through Telegram and email.

The monitoring chain has been verified end-to-end in production:

    machine stop -> heartbeat missing -> DOWN alert -> machine start -> heartbeat restored -> UP recovery

Heartbeat delivery failures are logged but must never terminate the reminder bot.

## Current product priority

See `BACKLOG.md` for the source of truth.

Completion-based interval recurrence is implemented; verify the chooser and Done/Snooze flow in Telegram after deployment. The `/settings` menu, custom values, and configurable nudge intervals are implemented. Next settings work is alias editing and the entry point for managing recurring series.

## Notes

Do not add an auto-deploy GitHub Actions workflow unless it preserves the manual database backup step.
