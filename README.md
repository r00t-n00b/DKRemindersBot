# DK Reminders Bot

Telegram reminder bot deployed on Fly.io.

Documentation reconciled on 26 November 2026 against production **v411**, commit **581a7d7**.

The bot supports one-off and recurring reminders, natural-language text and voice input, reply/forward-context reminders, snooze/reschedule/done flows, personal self-reminders from group chats, group and user aliases, timezone-aware scheduling, and undo for delete actions.

Reply/forward-context reminders retain their source message through delivery, private-chat nudges, and repeated snooze (quick buttons or custom time). Notifications reply to the source only when it belongs to the destination chat. If the source was deleted, delivery is allowed without a reply.

## Personal settings

`/settings` opens a private inline menu for default time, timezone, reminder nudges, aliases, `/list`, and `/unfinished`. Group requests show no personal settings. Older timezone/default-time buttons remain supported.

- Default time accepts presets and custom `HH:MM` input (for example, `08:45`).
- Timezone accepts presets, location, a limited offline city-alias list, and any available IANA timezone such as `America/New_York`. Search results require confirmation; changing timezone retains the migration question for active reminders.
- Custom values are replies to a specific bot prompt. Unrelated messages still follow the ordinary reminder flow; `/cancel` closes the pending settings input.
- Nudge schedules contain 1–20 independently editable intervals, each from one minute to 365 days. Defaults are `[20, 60, 240, 720]` minutes between successful sends. Presets and custom values such as `45 мин`, `1 ч 30 мин`, and `2 дня` are supported.
- A schedule is edited as a draft and saved atomically. Sessions, drafts, and pending prompts survive restart and expire after 24 hours; stale buttons cannot change newer screens.
- Preferences belong to the private recipient, including reminders created by someone else. Each primary delivery snapshots its schedule. Schedule changes apply to later deliveries; disabling stops pending nudges immediately, and re-enabling only allows nudges for new primary deliveries.
- Snooze stops the old reminder's cycle; its next primary delivery uses current preferences. Groups still receive no nudges. Failed sends do not spend a repeat, and downtime does not produce a catch-up burst.

Migration adds nudge preference/snapshot fields and the `settings_sessions` table without rewriting existing reminders or series. Legacy delivered rows retain the default schedule. See `docs/SETTINGS_DESIGN.md` for the agreed UX and boundaries.

## Alias management in settings

`/settings` → **Мои алиасы** lists only the current user's aliases, with pagination and a detail screen. Chats (channels/groups) come before people, with alphabetical ordering within each section and section headers on every page. Creating, renaming, and deleting use drafts and confirmation buttons. Existing reminders keep their stored destination when an alias changes or is deleted.

- **Recipient reminders:** each alias detail has a **📋 Напоминания для этого алиаса** button. It shows only active, undelivered reminders created by the alias owner for that recipient, ordered by delivery time, 10 per page, with refresh and a return to the alias. Aliases sharing a recipient show the same reminders; renaming keeps them visible. This view is independent of `/list` pagination.
- **Person:** enter a short name and `@username`; the recipient must already have started the bot. The destination is revalidated when confirming.
- **Group:** enter a short name, then select a group with Telegram's native chat picker. The bot must already belong to that group; access is checked at selection and confirmation.
- New names are one token of 1–64 characters, starting with a letter, followed by letters, digits, `_` or `-`. Date/command words are rejected. Existing legacy aliases remain visible and removable.
- A new name cannot overwrite another alias of either type in the same owner scope, including case-insensitive collisions. Other owners may use the same name.
- Old callbacks, expired requests, cancelled group selections, and aliases modified through legacy commands are checked before mutation. `/cancel` also dismisses a pending group picker.
- `/linkuser`, `/linkchat`, `/renamealias`, and `/unalias` remain available.

This feature uses the existing alias tables and settings-session data; no schema migration is required.

The local alias audit on 26–28 November 2026 covers create → rename → create with the new name → delete → deliver previously created reminders for person and group aliases through the real handlers and worker with simulated Telegram responses. Pending publication: recipient lists sort by actual instant across UTC offsets; alias-input database read errors keep the original prompt valid for retry; settings screens disable link previews during both edits and replacement messages.

The native Telegram check on v411 verified a temporary self-recipient alias, pagination, rename, rejection of the old name, recipient lists, and delivery/completion of reminders created before and after rename. The user confirmed deleting the temporary alias and cleaning up the messages. Native group selection, delivery after alias deletion, and the unpublished preview fix still require live verification.

## Unfinished reminders

/unfinished or /settings → **📥 Незавершённые напоминания** shows delivered reminders awaiting completion in the requester's own private chat (delivered=1 and acked=0). This includes incoming reminders from other authors and personal legacy records without a creator. Future reminders are available through /list.

/unfinished alias opens the selected recipient's delivered, unfinished reminders created by the requester. Only aliases owned by that requester are resolved. Legacy multiword aliases are supported. Person aliases take priority over chat aliases of the same name, matching /list. An unknown alias returns an error. Each page and completion revalidates the selected alias and destination. Renaming, deleting, or retargeting the alias expires that view.

Reminders are ordered by scheduled instant, oldest first. Pages contain 8 entries with the task, scheduled time, timezone, and a recurring marker. The recipient alias appears in the heading for external lists. An empty list shows only the heading and an empty-state sentence. Page numbering appears when there are multiple pages. There is no 20-record cap. Page arrows and **Обновить** reread the database. The private session, recipient scope, and visible IDs survive restarts.

Numbered **✅1**, **✅2**, and subsequent buttons complete the corresponding visible reminder and immediately refresh the list. The personal view permits completion by the private recipient. An alias view permits completion of reminders created by the requester for that destination. Authorization and acknowledgement are checked in one transaction. Completion-based series create their next occurrence atomically. Inactive series are acknowledged without restarting them. Standard completion cleanup updates tracked messages.

Snooze removes the acknowledged occurrence from the list. The postponed occurrence appears after delivery. Reading uses SQLite read-only mode. Completing an entry changes its acknowledgement state and may create the next series occurrence. No schema migration is required.

## Reminder diagnostics

`/debug_reminders` (also `/history`) works only in a private chat and shows the latest 20 stored reminders **created by the requesting user**, including delivered and completed records. It includes that user's reminders to people and groups; it never shows reminders created by somebody else, even when the requester is the recipient. Legacy records without `created_by` are excluded. There is no cross-user admin view.

- `/debug_reminders` — all recipients.
- `/debug_reminders Наташа` — a user-owned person or chat alias (legacy multiword names are supported).
- `/debug_reminders @username` — a known private recipient.
- Unknown targets return an error; ambiguous person/chat aliases require renaming or using `@username`.

Each page shows 5 reminders, newest ID first, with creation/due/sent times, destination and series ID, delivery/acknowledgement flags, nudge count and last nudge, delivery state/attempts/retry time, source-message IDs, a short error summary, and tracked Telegram message counts by `created` / `delivery` / `nudge`. Dates retain their stored ISO offset and timezone. Configured API secrets and recognizable Telegram/Google tokens are hidden in error summaries.

Arrows and **Обновить** re-read the most recent 20 rows and current states. The private pagination session expires after 30 minutes of inactivity, on opening a new diagnostic screen, or after a restart; open the command again. It is independent of `/list` and `/settings`. The SQLite connection uses `mode=ro`; diagnostics adds no tables and performs no database writes. Deleted rows cannot be recovered from this view.

## Interval recurrence modes

Creating an interval series (for example, `/remind every 30 minutes - stretch` or «напоминай каждые полчаса размяться») asks **По расписанию** or **После выполнения** before creating any reminders. Cancel creates nothing. The choice survives a restart and expires after 24 hours.

- **По расписанию:** the existing schedule behavior.
- **После выполнения:** the next reminder is scheduled one interval after Done; no new occurrence is created while the current one is unfinished. Snooze moves the current occurrence and retains its series/source.
- Calendar schedules such as every day at 09:00 and existing series keep their previous behavior.
- Done/Snooze are transactional and reject duplicate actions. In private chats the recipient acts; in groups the series creator acts. Nudges remain private-only.
- Explicitly skipping one occurrence starts the next interval from the skip time. Deleting a series stops it; undo preserves the mode.
- Minutes/hours/days/weeks measure elapsed time across timezone/DST changes. Months use the series timezone and clamp to the last day of the month.

Pending choices use the additive `recurrence_choices` table. The series mode is stored in the existing template payload; existing rows are not rewritten.

## Recent parsing fixes

- Voice recipient validation compares a proposed target against the transcript. An explicit recipient before the schedule can authorize routing to that alias. Names mentioned inside the task are retained as task text. An unconfirmed target produces a clarification message. The guard supports named calendar dates such as 14 декабря, 14 december, and 14 Dec.
- Text requests with an explicit alias and relative delay, such as «напомни Наташе через 3 часа ответить всем в слаке», use the local parser.
- «Напомни на следующей неделе фильтры и их мейнтейнс» uses the local parser. Next week means the next Monday with the user's default time, unless a time is supplied. Russian forms such as «следующей» are recognized as date prefixes.

These changes were published in v405–v408 and are covered by handler-to-storage regression tests with simulated recognition responses. Real audio recognition remains part of Telegram smoke testing.

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
1661 passed, 1 skipped
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

Production uses Fly.io app dk-reminders-bot. The publication sequence is commit → push → SQLite backup on Fly → deploy, with CI checked before the application update.

1. Run the relevant tests and the full suite. Commit and push the intended files.
2. Create a uniquely named backup under /data using Python's sqlite3.Connection.backup API against /data/reminders.db. Verify the backup with PRAGMA integrity_check.
3. Download that backup to /Users/r00t_n00b/TGBOT-backups using fly sftp get. Verify its integrity and compare its SHA256 with the remote file. Store the backup path, commit, and checksum in a local manifest.
4. Wait for the commit's GitHub Tests workflow to succeed. Build from a clean git archive of the committed revision, then run fly deploy --remote-only -a dk-reminders-bot from that archive directory.
5. Verify machine startup, deployed source hashes, logs, database integrity, schema, and preservation of pre-deploy reminders. Complete the feature's smoke checks.

The online SQLite backup captures a consistent database while the bot is running. Documentation-only changes can be committed and pushed without a deployment.

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

Published features include completion-based interval recurrence, the native settings menu, alias editing and recipient lists, private diagnostics, and the delivered unfinished list with personal/alias scopes and completion buttons. The v411 list uses the compact message layout.

The next planned feature is recurring-series management from /settings. Further backlog items include snooze/delete from the unfinished list, remaining settings UX, voice timezone onboarding, and delivery observability. Deployment verification and user confirmation in Telegram are tracked separately in BACKLOG.md.

## Notes

Do not add an auto-deploy GitHub Actions workflow unless it preserves the manual database backup step.
