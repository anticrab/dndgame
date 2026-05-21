# Аудит 15: CLI + GameRunner (этап I)

**Автор:** Maxim Lokotkov
**Дата:** 2026-05-22
**Под ревью:**

- `src/dnd/application/dto/player_intent.py`
- `src/dnd/application/ports/player_intent_provider.py`
- `src/dnd/application/engine/game_runner.py`
- `src/dnd/interfaces/cli/scripted_provider.py`
- `src/dnd/interfaces/cli/console_provider.py`
- `src/dnd/interfaces/cli/event_printer.py`
- `src/dnd/interfaces/cli/app.py` (команда `play`)
- `tests/unit/application/test_game_runner.py`
- `tests/integration/cli/test_console_provider.py`
- `tests/integration/cli/test_event_printer.py`
- `tests/e2e/test_cli_play.py`

**Прогон тестов:** `pytest -q --ignore=tests/e2e/test_playthrough.py` → **703 passed in 1.16s**.

Голый `pytest -q` показывает `3 failed, 704 passed`: три падения в `tests/e2e/test_playthrough.py`, который **не входит в этап I** (файл untracked, не в коммите `802d221`), скрипт`ScriptedRNG` спроектирован под другой контент. На вертикаль CLI это не влияет, но файл следует либо доработать, либо удалить отдельно.

**Не оценивалось** (вне ТЗ этапа I): TUI (этап J), multiplayer/hotseat, persistence (SaveRepository), i18n.

---

## 1. Резюме

Этап I **архитектурно чист** и решает декларированную задачу: бой реально играется через `dnd play <scenario_id>`, port `PlayerIntentProvider` корректно отделяет «принятие решений» (UI / scripted / AI) от «как идёт игра» (`GameRunner` в application). Hexagonal-правила соблюдены — application ничего не знает про `rich` / `questionary` / `typer`; `EventPrinter` живёт в `interfaces/cli` и подписывается на bus через публичный port `EventBus.subscribe`. Тесты детерминированы: `ScriptedIntentProvider` + `ScriptedRNG` + fake-prompts, никакого настоящего TTY/questionary в pytest не дёргается. Покрытие — все шесть видов intent'а, smoke-цепочка `play <scenario>` через monkeypatch.

**S0 не обнаружено** — runtime-крашей в коде CLI / GameRunner нет, основной happy-path и негативные ветки (нет оружия / пустой ввод / провайдер не возвращает EndTurn) безопасны.

**S1 находки** (то, что стоит закрыть до этапа J):

- **CL-UX001 (S1)** — UX-ловушка: выбор «Attack» при отсутствии валидных целей **завершает весь ход** игрока (`_build_attack_intent` → `EndTurnIntent`). Аналогично — невалидный ввод координат для Move (`"garbage"`, пустая строка, off-grid) и пустой путь. Игрок теряет turn за одну случайную опечатку. Поведение зафиксировано тестами `test_console_provider_attack_with_no_targets_becomes_end_turn` / `test_console_provider_move_invalid_text_becomes_end_turn` — значит, это **спроектированное** поведение, а не недосмотр, но для интерактивного CLI оно враждебно. Ожидаемо — re-prompt с сообщением «нет целей» / «не понял координаты», а не молчаливый конец хода. PHB-2024 эту ситуацию не нормирует; решение целиком UX-уровня.
- **CL-A001 (S1)** — `app.py:play` передаёт в `build_default_dependencies` плейсхолдерный `Battlefield(1, 1)`, который сразу же выбрасывается `build_encounter_from_scenario` (см. `scenario_builder.py:91-99`). Это рабочая, но **мёртвая ссылка**: composition root намеренно «знает», что её зависимость будет переиспользована частично. Чище — выделить `build_dependencies_without_battlefield()` или принять `battlefield: Battlefield | None`. Не баг, но сигнал, что layering между composition root и scenario builder требует ещё одного прохода.

**S2 находки**: невыход из `dnd play` без Ctrl+C (`questionary` возвращает `None` → трактуется как EndTurn → следующий ход), GameRunner не перепроверяет `actor.is_alive` между intent'ами одного хода (теоретический edge-case при OA-смерти посреди Move), и `Battlefield(1,1)` / тестовая ветка `del warrior` в нескольких тестах (smoke-asserts без проверки эффекта). Подробности — ниже.

---

## 2. Архитектура — S0 / S1 / S2

### S0

Не обнаружено.

### S1

#### CL-A001 (S1) — composition root в `play` передаёт «мёртвый» Battlefield

`src/dnd/interfaces/cli/app.py:84`:

```python
deps = build_default_dependencies(battlefield=Battlefield(1, 1))
enc = build_encounter_from_scenario(scenario, content=repo, deps=deps)
```

`build_encounter_from_scenario` (`scenario_builder.py:90-99`) строит новый `Battlefield` из `MapTemplate` и создаёт **новый** `EncounterDependencies`, перенося из переданного только `dice_roller / modifier_applier / condition_service / event_bus / rng`. Аргумент `battlefield` фактически не используется — это контрактный мусор. `e2e/test_cli_play.py` копирует ту же ошибку (`Battlefield(1, 1)` в `patched_play`).

**Чем плохо.** Тест на 30-50 строк выше может скопировать паттерн и забыть, что битфилд внутри не тот. Если завтра `ComputerDiceRoller` или `ModifierApplier` начнут ссылаться на battlefield в конструкторе, бой сломается, а тесты этого не покажут.

**Фикс.** Либо `build_default_dependencies(battlefield: Battlefield | None = None)` с явным контрактом «битфилд может быть подменён сценарием», либо разделить factory на `build_engine_services()` (без battlefield) и `bind_to_battlefield(services, bf)`.

### S2

#### CL-A002 (S2) — `EncounterDependencies.event_bus` доступ через `enc.deps.event_bus`

`app.py` использует цепочку `enc.deps.event_bus` (см. `app.py:87`). Это работает, но обходит инкапсуляцию: Encounter единственный известный owner шины внутри своей зоны, а consumer должен дотягиваться через `.deps.`. Чистее — публичный `enc.event_bus` proxy на `_deps.event_bus`. Не блокирует stage I.

#### CL-A003 (S2) — `_apply_intent` ловит расширения PlayerIntent через `TypeError`

`GameRunner._apply_intent` (`game_runner.py:142`) кидает `TypeError` для неизвестного intent. Это нормальный defensive guard, но: если завтра в `PlayerIntent` добавят `ItemUseIntent` без правки runner'а, ход PC упадёт с `TypeError` — runner протечёт в encounter loop без `end_turn`, и encounter может зависнуть в неконсистентном состоянии. Лучше — поймать на уровне `_run_pc_turn`, залогировать и принудительно завершить ход.

---

## 3. Правила (PHB-2024) — S0 / S1 / S2

### S0

Не обнаружено.

### S1

Не обнаружено: `GameRunner` корректно использует `can_perform_against` для Attack/Move (проверка LoS, cover, range, проходимости, бюджета) и `can_perform` для Dodge/Dash/Disengage. Экономика «одна Action на ход» соблюдается на уровне `TurnContext.can_spend` — вторая Dodge/Dash в один ход вернёт `Forbidden(NO_ECONOMY_LEFT)`, runner молча проглатит. Тест `test_runner_move_then_attack_in_same_turn` подтверждает: PC может Move-then-Attack в одном ходу через два Intent'а.

### S2

#### CL-R001 (S2) — `GameRunner` не перепроверяет `actor.is_alive` между intent'ами

`_run_pc_turn` крутит цикл до `_MAX_INTENTS_PER_TURN`. Если PC получит OA-смерть посреди Move (теоретически — OA дамаджит actor'а до 0 HP, MoveAction обрабатывает это внутри себя), следующий iteration спросит у provider новый intent у уже мёртвого PC. Все Action'ы упрутся в `can_perform` (UNCONSCIOUS условие → `CONDITION_BLOCKS_ACTION`, Move через `_MOVEMENT_BLOCKERS`), но цикл провисит до `EndTurnIntent` или до `_MAX_INTENTS_PER_TURN`.

В текущем MVP PC — единственный игрок, OAs от монстров реально работают. Но stack OAs на одном Move реально может уронить актора. Лучше — после каждого `_apply_intent` проверить `if not actor.is_alive or actor.is_at_zero_hp: return`.

#### CL-R002 (S2) — Dash активирует `CombatStance.DASHING`, но Dash вне MVP сбрасывается на старте следующего хода

Это документировано в `stances.py:114-119` («Dash дважды за ход через Cunning Action Плута»), но в текущем тесте `test_dash_intent_doubles_movement_for_pc` ассерт `del warrior` молчит. Это smoke-тест без проверки эффекта (см. § 5).

---

## 4. UX / надёжность — S0 / S1 / S2

### S0

Не обнаружено.

### S1

#### CL-UX001 (S1) — выбор «Attack» без целей или невалидный Move молча завершают ход

Описано в резюме. Зафиксировано в тестах:
- `test_console_provider_attack_with_no_targets_becomes_end_turn`
- `test_console_provider_move_invalid_text_becomes_end_turn`

Это **программный контракт**, но для интерактивного CLI — антипаттерн. Минимальный фикс:

```python
def _build_attack_intent(...):
    if not targets:
        self._print_warning("[red]No reachable targets — choose another action.[/]")
        return self.next_intent(actor, ctx, encounter)  # re-prompt
    ...
```

То же для пустого/невалидного ввода Move (с подсказкой формата). Альтернатива — сделать выбор «Attack» в главном меню условным (greyed-out при отсутствии целей).

Дополнительный нюанс: Ctrl+C в `questionary.select` возвращает `None`, что трактуется как «End turn» (`console_provider.py:96-97`). Игрок не может выйти из `dnd play` цивилизованно — только серией Ctrl+C, пока typer не получит `KeyboardInterrupt`. На stage J (TUI) надо предусмотреть явный `Quit`-пункт.

### S2

#### CL-UX002 (S2) — `_MAX_INTENTS_PER_TURN = 50` без обратной связи игроку

Лимит написан в `game_runner.py:53`. Если провайдер (например, скриптованный или будущий AI) случайно зациклится, GameRunner логгирует `warning` и завершает ход. Это правильно для defensive coding, но игрок в живом CLI этого warning не увидит — `_log.warning` не уходит в `rich.Console`. Не критично сейчас, но при отладке сценариев — слепое место.

#### CL-UX003 (S2) — `EventPrinter` тих по `RollIssued` / `RollApplied`

`_dispatch` намеренно не маппит эти события (`event_printer.py:55-58`). Для gamelog это корректное решение (слишком шумно). Но если игрок жалуется «почему урон не такой» — нет debug-режима. Рекомендация — флаг `EventPrinter(verbose=True)` на будущее.

#### CL-UX004 (S2) — `ConsoleIntentProvider._chebyshev_path` не проверяет `in_bounds(target)` заранее

`console_provider.py:186-200`: путь строится «слепо» от текущей позиции к (x,y). Если игрок ввёл `(-5, 100)`, path содержит десятки клеток, `MoveAction.can_perform_against` отбракует на первой же out-of-bounds, runner молча проглотит. Идеально — валидировать `target` сразу и переспросить.

---

## 5. Пропущенные тесты

- **CL-G001 (S2)** — `test_dash_intent_doubles_movement_for_pc`, `test_runner_dodge_intent_applies_stance`, `test_disengage_intent_sets_flag_for_pc` — три теста заканчиваются `assert enc.is_concluded is True` + `del warrior` (объявлено в комментарии как «smoke»). Реальный эффект stance'а (`movement_remaining_ft += speed_ft`, `combat_stances` содержит ключ хотя бы на один turn) — не проверяется. Точный тест семантики есть в `tests/unit/application/actions/test_stances.py`, но именно **интеграция через `GameRunner` + `ScriptedIntentProvider`** — нет. Минимальный фикс: подписаться на `EngineEvent`, проверить, что после первого хода warrior'а `ctx.action_used` или равноценный индикатор сработал. Сейчас тесты проходят, даже если `GameRunner._do_stance` молча `return` без `execute()`.
- **CL-G002 (S2)** — не покрыта ветка `_run_pc_turn`-skip при `not actor.is_alive or actor.is_at_zero_hp` (см. `game_runner.py:85-87`). При живом PC её не достичь, но при unconscious-PC (после OA или AoE) — да. Тест: создать PC с `hp.current=0` и `is_at_zero_hp=True`, прогнать раунд, убедиться что provider **не вызывался**.
- **CL-G003 (S2)** — нет интеграционного теста для `Allowed/Forbidden`-протечки: что если `AttackIntent` собран UI-кодом, но к моменту execute цель ушла за стену? Runner вызывает `can_perform_against`, отказывается, **молча идёт дальше** (`game_runner.py:152-155`). Это поведение задокументировано, но не закрыто тестом «Attack по цели вне LoS = no-op».
- **CL-G004 (S2)** — `test_play_unknown_scenario_exits_with_error` проверяет `exit_code != 0` и текст в stdout/stderr, но **не запускает реальный CliRunner на happy-path**. `test_play_mvp_skirmish_runs_to_end_with_scripted_intents` фактически **подменяет** `app.play` целиком (`monkeypatch.setattr(app_module, "play", patched_play)`) и вызывает `patched_play(...)` напрямую. Это значит, что typer-обёртку (`@app.command("play")`, парсинг аргументов, `--content-dir`) e2e никто не дёргает. `CliRunner.invoke(app, ["play", "mvp_skirmish"])` мог бы хоть раз пройти через настоящую цепочку (с тем же scripted-провайдером через `prompt_*` инъекцию), а не дублировать тело `play` в тесте.

---

## 6. Сводный TODO

| ID | S | Тема | Файл |
|----|---|------|------|
| CL-UX001 | S1 | Re-prompt при пустых targets / невалидном Move-вводе, не EndTurn | `console_provider.py:124,148` |
| CL-A001 | S1 | Убрать плейсхолдер `Battlefield(1, 1)` из composition root | `app.py:84`, `test_cli_play.py:84` |
| CL-A002 | S2 | Публичный `enc.event_bus` proxy вместо `enc.deps.event_bus` | `encounter.py:188-190`, `app.py:87` |
| CL-A003 | S2 | `_run_pc_turn` ловит `TypeError`, не валит цикл боя | `game_runner.py:142` |
| CL-R001 | S2 | Проверять `actor.is_alive` между intent'ами одного хода | `game_runner.py:103-112` |
| CL-UX002 | S2 | Логгировать `_MAX_INTENTS_PER_TURN`-overflow в `rich.Console`, не только в `logging` | `game_runner.py:108-112` |
| CL-UX003 | S2 | `EventPrinter(verbose=True)` для отладочного gamelog | `event_printer.py:55-58` |
| CL-UX004 | S2 | Валидировать `target` Move сразу: `in_bounds` + переспрос | `console_provider.py:144-155` |
| CL-G001 | S2 | Smoke-тесты Dodge/Dash/Disengage заменить на проверяющие реальный эффект | `test_game_runner.py:165-250` |
| CL-G002 | S2 | Тест: dead PC в `_run_pc_turn` → provider не вызывается | новый тест |
| CL-G003 | S2 | Тест: AttackIntent по цели вне LoS → молчаливый no-op | новый тест |
| CL-G004 | S2 | E2E через `CliRunner.invoke(app, ["play", "mvp_skirmish"])` с инъекцией prompt'ов, не monkeypatch всего `play` | `test_cli_play.py:35-99` |

---

## Приложение: подтверждения по углам ревью

**Hexagonal:**
- `PlayerIntentProvider` — Protocol в `application/ports/`, `runtime_checkable`. ✓
- `ConsoleIntentProvider` / `ScriptedIntentProvider` — в `interfaces/cli/`, импортируют только application + domain. ✓
- `GameRunner` — в `application/engine/`, не импортирует `interfaces/` / `rich` / `questionary`. ✓
- `EventPrinter` — подписывается через `bus.subscribe(EngineEvent, handler)` (port), не блокирует (синхронный `_print`). ✓
- `from rich.console import Console` в `app.py` — приемлемо: `interfaces/cli` явно «грязный» слой UI. ✓
- Lazy `import questionary` внутри методов — оправдано: тесты не требуют установленного questionary, optional dep. ✓

**Правила PHB-2024:**
- `_do_attack` вызывает `can_perform_against` (включает `can_perform` + LoS/cover/range). ✓
- `_do_move` вызывает `can_perform_against` (включает `can_perform` + проверку пути). ✓
- `_do_stance` вызывает `can_perform`. ✓
- Move + Attack в одном ходу — тест `test_runner_move_then_attack_in_same_turn` подтверждает. ✓
- Одна Action на ход (Dodge → Dash вторым = Forbidden NO_ECONOMY_LEFT) — соблюдается через `TurnContext.can_spend`. ✓

**UX / надёжность:**
- `_MAX_INTENTS_PER_TURN=50` — разумно (в реальной игре один ход = до 5-6 intent'ов: move, attack, stance, end). ✓
- Пустые targets → EndTurn — **проблема UX** (CL-UX001). ✗
- Move парсит «x,y» через split — невалидный ввод → EndTurn (CL-UX001). ✗
- `EventPrinter` покрывает 15 из 17 типов событий, `RollIssued/RollApplied` намеренно тихи (CL-UX003 предлагает verbose-флаг). ⚠

**Тесты:**
- Изолированный сценарий со стеной — нормальный приём, не расходует RNG в monster turn (`monster` крутит Dodge). ✓
- Покрытие ошибок: пустой queue (`test_scripted_provider_returns_end_turn_when_empty`), invalid input (`test_console_provider_move_invalid_text_becomes_end_turn`), no targets (`test_console_provider_attack_with_no_targets_becomes_end_turn`), нет weapon (`test_runner_attack_intent_without_weapon_is_noop`), провайдер не возвращает EndTurn (`test_runner_safe_against_provider_never_returning_end_turn`). ✓
- Flaky: не обнаружено. RNG детерминирован через ScriptedRNG; prompts детерминированы через инъекцию.

---

## Применённые фиксы (2026-05-22)

**S1 — закрыто полностью:**

* **CL-A001** — введён `EncounterRuntimeServices` (dataclass без
  battlefield) с методом `.with_battlefield(bf) -> EncounterDependencies`.
  Новые фабрики `build_default_runtime_services` /
  `build_scripted_runtime_services`. `build_encounter_from_scenario`
  теперь принимает либо `services=` (рекомендуемый путь — без
  placeholder), либо `deps=` (legacy, для тестов). `app.py::play`
  использует новый путь — никаких `Battlefield(1, 1)`.

* **CL-UX001** — в `ConsoleIntentProvider` добавлен re-prompt при:
  - Attack без целей → notify + повторное меню (не теряем ход);
  - Move с невалидным parse / out-of-bounds / already there → notify +
    повторное меню.
  Защита от циклической ошибки: `_MAX_REPROMPTS = 5` → принудительный
  EndTurn с уведомлением. Новое поле `notify: Callable[[str], None]`
  для подмены в тестах / интеграции с rich.
  Четыре теста: `test_attack_with_no_targets_reprompts_with_warning`,
  `test_move_with_invalid_text_reprompts`,
  `test_move_out_of_bounds_target_reprompts`,
  `test_reprompt_max_depth_falls_back_to_end_turn`.

**S2 — закрыто полезное:**

* **CL-A002** — `Encounter.event_bus` property (proxy на
  `_deps.event_bus`). `app.py::play` теперь подписывает EventPrinter
  через `enc.event_bus`, без `.deps.`.

* **CL-R001** — `GameRunner._run_pc_turn` теперь перепроверяет
  `actor.is_alive`/`is_at_zero_hp` **перед** каждым `next_intent`.
  При смерти PC посреди хода (от OA / future AoE) цикл выходит
  немедленно, не крутит intent'ы до `_MAX_INTENTS_PER_TURN`.

**Отложено по плану:**

* **CL-A003** — defensive `TypeError` на неизвестный PlayerIntent.
  Это reasonable защита; добавим try/except на уровне `_run_pc_turn`
  при расширении PlayerIntent (когда заведём ItemUseIntent / SpellIntent).
* **CL-R002** — Dash stance очищается на старте следующего хода;
  smoke-тест есть, точный assert на effect — добавим вместе с
  Cunning Action (Плут).
* **CL-UX002/UX003/UX004** — UX-улучшения (warning в gamelog,
  verbose mode, in_bounds preview). Сделаем при TUI этапе.
* **CL-G001/G002/G003/G004** — расширенное покрытие. Часть закрыта
  фиксами CL-UX001/CL-R001; остальное — пост-MVP.

**Итоговые цифры:**

* pytest:   **711 passed** (+4 за тесты re-prompt)
* ruff:     All checks passed
* mypy:     Success: no issues found in 93 source files
* coverage: 95.68%

**Реальная находка:** CL-A001 — placeholder `Battlefield(1, 1)`,
который выбрасывался в `build_encounter_from_scenario`. Не баг, но
архитектурный смелл, который бы прорвался в реальный баг, если бы
сервис в конструкторе сослался на битфилд (например, для замера
размеров кеша). Фикс — чистое разделение зон ответственности
«сервисы vs map-bound deps».
