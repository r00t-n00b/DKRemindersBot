# DK Reminders Bot

Telegram reminder bot.

## Tests

Run the full local test suite:

    python3.11 -m pytest -q

Current expected result:

    410 passed, 1 skipped

GitHub Actions runs the same pytest suite on every push to main and on pull requests.

The GitHub Actions workflow is test-only. It must not deploy to Fly.io.

## Deploy

Production deploy is manual and must include a database backup before fly deploy.

Use this standard deploy block for production changes:

    git add main.py
    git commit -m "<meaningful message>"
    git push
    fly ssh console -a dk-reminders-bot -C 'sh -c "ts=$(date +%Y%m%d-%H%M%S); if [ -f /data/reminders.db ]; then cp /data/reminders.db /data/reminders-$ts.db.bak; else echo reminders.db not found, skip backup; fi"'
    fly deploy

If code and tests were already committed and pushed separately, only run the backup and deploy commands:

    fly ssh console -a dk-reminders-bot -C 'sh -c "ts=$(date +%Y%m%d-%H%M%S); if [ -f /data/reminders.db ]; then cp /data/reminders.db /data/reminders-$ts.db.bak; else echo reminders.db not found, skip backup; fi"'
    fly deploy

## Post-deploy smoke test

After deploy, check status and logs:

    fly status -a dk-reminders-bot
    fly logs -a dk-reminders-bot

Basic Telegram smoke test:

    /remind через минуту - smoke

Expected: reminder is created and delivered without traceback in logs.

## Notes

Do not add an auto-deploy GitHub Actions workflow unless it preserves the manual database backup step.
