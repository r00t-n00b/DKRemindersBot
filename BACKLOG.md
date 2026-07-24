# DK Reminders Bot — Backlog

Актуальный источник правды по крупному backlog бота.

Статусы:
- DONE — закрыто
- IN PROGRESS — начато, но не финализировано
- TODO — не начато / требует отдельной работы
- RULE — постоянное правило процесса

## 1. Delivery claim/status/retry — DONE

Production reminder-worker должен стабильно:
- claim-ить due reminders;
- не дублировать отправку;
- не терять reminders при ошибках;
- retry-ить failed delivery;
- корректно использовать статусы processing / sent / delivered / failed;
- переживать restart.

Связанные прод-проверки:
- команда проверки active/future/undelivered reminders в SQLite;
- проверка processing / sent / delivered состояний;
- восстановление после restart;
- понятный health-check или debug-команда для себя.

## 2. Time domain layer / timezone correctness — DONE

Закрыто:
- time domain layer;
- timezone correctness;
- timezone gate для plain text;
- сохранение CET как реального timezone, а не implicit default;
- продолжение исходного plain-text reminder после выбора timezone;
- смена timezone через /settings;
- напоминание про отпуск/переезд и смену timezone.

Остаётся проверить как часть voice UX:
- timezone gate для voice reminders, если пользователь новый.

## 3. /settings — IN PROGRESS

Нужно довести настройки до полноценного UX.

Уже сделано:
- read-only экран сначала — DONE;
- fallback time: понятный read-only текст “если время не указано...” — DONE;
- timezone — DONE;
- aliases summary — DONE;
- смена timezone через /settings — DONE;
- default/fallback reminder time через /settings — DONE;
- нормальный UX для смены timezone при отпуске/переезде с migration prompt — MOSTLY DONE.

Остаётся:
- собрать настройки в более полноценное меню, а не просто read-only summary + отдельные кнопки;
- editable aliases из /settings, а не только summary;
- nudge policy: включить/выключить nudges, интервал, максимум повторов;
- quick snooze “Завтра” / “Следующий понедельник” must use user default reminder time and show that time in button labels;
- язык кнопок / language preference;
- формат времени: 24h / verbose;
- тестовое напоминание из /settings;
- recurring management entry point из /settings;
- diagnostics/debug entry point только для себя;
- возможно показывать текущие user settings/debug summary только для себя.

## 4. Reply-context reminders — TODO

Научить бота создавать полезные напоминания из reply на Telegram-сообщение.

Базовый UX:
- фразы «напомни об этом», «напомни про это сообщение», «напомни через полчаса об этом» должны использовать сообщение, на которое ответил пользователь;
- не сохранять бесполезный текст вроде «об этом сообщении» без контекста;
- при доставке reminder должен содержать понятное описание исходного сообщения;
- по возможности сохранять связь с исходным Telegram-сообщением и отправлять reminder как reply либо давать ссылку/указание на источник.

Локальная обработка без Gemini:
- использовать `reply_to_message.text`;
- использовать caption вложения;
- использовать имя документа/файла;
- учитывать фото, видео, voice и другие типы вложений;
- для forwarded message учитывать автора/источник, если Telegram его предоставляет;
- делать короткий deterministic reminder text для простых случаев.

Gemini fallback:
- подключать только для длинных или неоднозначных сообщений;
- кратко суммаризировать действие, а не пересказывать весь текст;
- ограничивать длину итогового reminder text;
- при timeout/503 честно сообщать о временной ошибке;
- не терять исходный контекст при ошибке Gemini.

Пример:
- reply на PDF с подписью «потом посмотришь со мной job description, Tab 1 их, Tab 2 мой»;
- команда: «напомни через полчаса об этом сообщении»;
- ожидаемый reminder: «посмотреть с Наташей JD PMM PLG July 2026.pdf: Tab 1 — их JD, Tab 2 — мой».

Обязательно покрыть тестами:
- reply на обычный текст;
- reply на документ с caption;
- reply на документ без caption;
- reply на forwarded message;
- отсутствие reply;
- длинный текст с Gemini;
- Gemini temporary failure;
- исходное сообщение удалено к моменту доставки.

## 5. Inbox / незакрытые напоминания — TODO

Нужен отдельный inbox для delivered, но ещё не закрытых reminders:

- список незакрытых delivered reminders;
- done/snooze/delete из inbox;
- не показывать удалённое/завершённое;
- понятный UX для “висящих” напоминаний.

## 6. SQLite scalability hardening — TODO

Усилить SQLite под рост данных:

- индексы под due reminders;
- индексы под active/list/delete queries;
- проверить рост таблиц reminder_messages / nudges / recurring;
- безопасные миграции без ручной боли;
- production DB backup discipline.

## 7. Batch preview — TODO

Перед массовым созданием reminders нужен preview:

- preview перед созданием пачки;
- подтверждение / отмена;
- частичные ошибки;
- понятное отображение строк, которые не распарсились;
- защита от случайного массового создания.

## 8. Help/onboarding — TODO

Нормальный help и onboarding:

- /start для нового пользователя;
- /help с реальными примерами;
- onboarding после timezone;
- объяснить plain text, /remind, voice, recurring, groups;
- не заставлять пользователя повторять ввод после setup;
- единый стиль сообщений;
- меньше технических терминов;
- понятные confirmation messages;
- кнопки не должны вести в тупик;
- старые кнопки должны либо работать, либо объяснять, что устарели.

## 9. Repo/package structure cleanup — DONE

Корневую свалку `.py` файлов перенесли в нормальный package layout:

- root `main.py` оставлен как Fly-compatible entrypoint;
- production modules перенесены в `dkreminders_bot/`;
- добавлены package folders: callbacks, commands, domain, integrations, parsing, settings, storage, ui, utils, workers;
- tests updated for packaged imports;
- behavior changes не смешивались с refactor;
- full test suite green after move.

## 10. Убрать _apply_deps/globals постепенно — TODO

Постепенный технический рефакторинг:

- plain_text_remind_flow;
- voice_remind_flow;
- callback flows;
- timezone_features;
- перейти к явным deps/dataclass deps;
- не делать одним большим рискованным рефактором.

## 11. Улучшить wording invalid recurring ordinals — TODO

Сделать понятные ошибки для невалидных recurring формулировок:

- “каждый 32 день”;
- невалидные weekday/month/day;
- RU/EN wording;
- подсказки с правильными примерами.

## 12. Reminder lifecycle / Done-Snooze-Delete consistency — IN PROGRESS

Довести lifecycle до консистентного состояния.

Уже сделано:
- Snooze удаляет sibling delivery/nudge messages, если Telegram позволяет;
- Done удаляет sibling delivery/nudge messages, если Telegram позволяет;
- stale Snooze/Done buttons больше не должны создавать duplicate reminders;
- `Reminder` model читает `delivered` / `acked`, чтобы stale callbacks реально отсеивались;
- custom snooze не должен оставлять активные sibling buttons;
- created reminder action buttons на новых reminders регистрируются как `kind="created"`;
- created action messages деактивируются/удаляются после фактической доставки reminder;
- stale created-action buttons не должны оживлять уже delivered/acked reminder.

Остаётся:
- /list не показывает удалённое/завершённое — проверить и закрепить diagnostics;
- recurring reminders ведут себя правильно;
- undo не восстанавливает не то;
- done/snooze/delete после already deleted/already done — расширить coverage;
- recurring: delete one instance vs delete series;
- recurring + snooze;
- recurring после restart;
- nudge lifecycle;
- production sanity-check после lifecycle patches.

## 13. Callback/data consistency — TODO

Закрепить тестами, что router pattern совпадает с callback_data:

- created_del;
- created_resched;
- created_snooze;
- del;
- undo;
- selfremind;
- custom date/time;
- старые callback-и должны либо работать, либо честно говорить, что устарели;
- не должно быть unknown-option из-за несовпадения callback_data и pattern.

## 14. Групповые напоминания и self-remind — TODO

Отдельный крупный функциональный блок.

Флоу:
- “Напомнить мне лично” из группы;
- обычное групповое напоминание;
- reminder создаётся в личку, но из группового контекста.

Edge-cases:
- если пользователь не писал боту в личку;
- если пользователь уже знаком;
- source chat/group корректно сохраняется;
- callback нажимает другой человек;
- reminder создаётся в личку, но из группового контекста;
- popup/message тексты понятные;
- “Напомнить мне лично” не ломает групповой reminder;
- self-remind callback_data и router pattern совпадают;
- cancel/back в self-remind flow;
- обычное напоминание vs напоминание до события внутри self-remind.

## 15. Access control audit — TODO

Общий security/pass по всем флоу:

- /list alias / username;
- delete по list_ids;
- кнопки delete/snooze/done для reminders в чужих чатах;
- self-remind из групп;
- user-alias/chat-alias owner scope;
- callback нажал не тот пользователь;
- reminder создан в группе, действие нажато в личке или наоборот;
- нельзя удалить/сдвинуть чужой reminder через старую кнопку.

## 16. Voice UX polish — TODO

Отдельный большой блок по voice reminders:

- timezone gate для voice reminders;
- скачивание voice;
- transcription;
- Gemini retries;
- alias prompt;
- fallback;
- ошибки квоты;
- длинные voice;
- групповые voice;
- если Gemini вернул невалидный /remind текст — честная ошибка;
- логировать normalized voice text;
- возможно показывать “Я услышал: ...” перед созданием;
- Gemini quota/transient/model errors;
- fallback, если transcription/normalization упал;
- не создавать reminder из мусорной расшифровки.

Следующий вероятный приоритет:
- проверить, что voice reminders не обходят timezone onboarding и не создают reminder в implicit CET.

## 17. Plain text / Gemini / fallback — TODO

Plain text уже работает с timezone, но остаётся полировка:

- когда использовать local parser;
- когда Gemini;
- когда fallback;
- защита от Gemini quota/transient/model errors;
- не создавать reminder из обычной болтовни;
- нормально объяснять “я не понял”;
- логировать source нормализации;
- тесты на реальные фразы;
- alias в plain text;
- конфликт alias vs дата/время.

## 18. Recurring reminders — TODO

Повторяющиеся reminders — один из самых рискованных кусков.

Core behavior:
- “каждый день в 9”;
- “каждый понедельник”;
- “каждые 2 недели”;
- recurring + timezone;
- recurring + delete one instance;
- recurring + delete series;
- recurring + snooze;
- recurring + миграция timezone;
- recurring после restart;
- recurring + list/delete/undo;
- recurring + lifecycle consistency.

Recurring management UX:
- отдельный экран управления повторяющимися напоминаниями;
- список активных серий;
- показывать template_id / текст / human schedule / next instance / target chat;
- выключить/поставить на паузу серию;
- включить обратно;
- удалить ближайшее срабатывание;
- удалить всю серию;
- изменить текст;
- изменить время/schedule;
- entry point из /settings;
- entry point из /list, если reminder recurring;
- чётко различать “удалить ближайшее” и “удалить всю серию”;
- access control для group/private/created_by;
- тесты на private/group/created_by/undo/stale callbacks.

## 19. Snooze / reschedule UX — TODO

Полировка snooze/reschedule:

- snooze кнопки после созданного reminder;
- custom snooze calendar;
- custom time picker;
- back/cancel;
- защита от старых callback;
- не показывать бесполезные кнопки после удаления/выполнения;
- понятные тексты после переноса.

## 20. List / delete / undo — TODO

Довести до железобетона:

- /list в личке;
- /list в группе;
- список created by me / for this chat;
- delete single;
- delete recurring instance;
- delete recurring series;
- undo delete;
- старые callback-и;
- индексы после удаления;
- пустые списки.

Diagnostics / debug history:
- нормальный /list остаётся чистым и показывает только user-facing active reminders;
- добавить private/admin-only debug command, например `/debug_reminders` или `/history`;
- показать последние 20 reminders для текущего user/chat;
- поля: id, text, remind_at, delivered, acked, nudge_count, sent_at, template_id, delivery_state;
- показать количество tracked Telegram messages по kind: created / delivery / nudge;
- read-only, без мутаций;
- не раскрывать чужие reminders;
- тесты на private chat, group chat, alias/created_by boundaries, empty history.

## 21. Алисы чатов и пользователей — TODO

Бэклог по aliases:

- linkchat;
- linkuser;
- aliases;
- unalias;
- renamealias;
- owner-scope, чтобы алиасы разных людей не конфликтовали;
- запрет плохих alias-ов;
- конфликт alias vs дата/время;
- alias в voice/plain text.

## 22. “Напоминание до события” — TODO

Флоу:
- обычное напоминание;
- напоминание до события.

Нужно стабилизировать:
- парсинг даты события из текста;
- today/tomorrow/послезавтра/сегодня/завтра;
- dd.mm HH:MM;
- month name RU/EN;
- кнопки: за сутки / 10 часов / 3 часа / 1 час / 20 минут / custom;
- custom offset;
- fallback, если дату события не понял;
- “завтра/сегодня” считать от времени исходного сообщения, не от времени клика;
- тесты на RU/EN даты;
- интеграция с self-remind flow.

## 23. Production observability — TODO

Логирование и prod visibility:

- reminder created;
- reminder delivered;
- reminder failed/retried;
- list command target type: self/chat-alias/user-alias/username;
- timezone onboarding started/completed;
- plain text normalization source: local/local_relative/gemini/fallback;
- debug-команды/SQL-команды для проверки active/future/undelivered reminders;
- посмотреть активные reminders конкретного user/chat;
- посмотреть последние delivered/acked/nudged reminders;
- посмотреть tracked reminder_messages by kind;
- посмотреть timezone/settings пользователя;
- посмотреть pending recurring;
- dry-run due reminders;
- аккуратная debug-команда только для себя;
- health-ish prod checks после deploy.

## 24. Тестовая инфраструктура — RULE

Постоянное правило:

- каждая новая логика = тест вместе с кодом;
- тесты коммитятся вместе с функциональным изменением.

Особенно нужны тесты на:
- wiring handlers;
- callback_data;
- callback patterns;
- private vs group;
- timezone;
- recurring;
- delete/undo;
- old/stale callbacks;
- negative paths;
- access control;
- prod-risk edge cases.

## 25. DB migration discipline — RULE

Постоянное правило:

- миграции идемпотентные;
- тесты на schema changes;
- backup перед deploy/ручными DB-операциями;
- не удалять данные без backup;
- не смешивать рискованную миграцию с большим UX-рефактором;
- не удалять строки настроек, если можно обнулить конкретное поле;
- ручные SQLite-команды через fly ssh console давать без heredoc, чтобы zsh не зависал.

## Suggested next order

1. /settings: finish the planned settings menu, especially nudge policy, aliases editing, recurring management entry point, diagnostics entry point.
2. Production observability: add `/debug_reminders` or `/history` with delivered/acked/nudge_count/tracked message diagnostics.
3. Recurring management UX: list series, pause/resume, delete next occurrence, delete whole series, edit schedule/text.
4. Voice UX polish: timezone gate for voice reminders.
5. Reminder lifecycle / Done-Snooze-Delete consistency: remaining recurring/undo/nudge edge cases.
6. Callback/data consistency.
7. Access control audit.
8. Групповые напоминания и self-remind.
9. “Напоминание до события”.
