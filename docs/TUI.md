# TUI — Textual-приложение

Документ фиксирует **архитектуру** TUI (этап J ROADMAP §8) и границу
«что входит в MVP J, что — пост-MVP». Бизнес-логика описана в
`docs/ENCOUNTER.md` / `docs/ACTIONS.md`; визуальный язык, спрайты,
темы и локализация — в `docs/UI.md` и `docs/ui_mockups/`. Этот файл —
**связующее звено** между ними и реализацией в
`src/dnd/interfaces/tui/`.

См. также: `docs/ARCHITECTURE.md` §4 (порты/адаптеры), аудит 15 CL-*
(почему оба UI висят на одном `PlayerIntentProvider`).

---

## 0. Рекомендуемый шрифт терминала

ASCII-арт карты, инициативы и боксов рассчитан на **JetBrains Mono**
(или любой моноширинный шрифт со стабильной шириной для unicode
box-drawing символов: `╔═╗║╚╝┌─┐│└┘`). Установите его системно и
выберите в настройках вашего терминала:

* macOS Terminal / iTerm2 → Preferences → Profiles → Text → Font →
  JetBrains Mono.
* gnome-terminal → Preferences → Profile → Text → Custom font →
  JetBrains Mono.
* Windows Terminal → Settings → Profile → Appearance → Font face →
  JetBrains Mono.

Без моноширинного шрифта рамки и сетка карты будут «плыть»:
Textual рендерит CSS `border: round` через box-drawing символы,
которые требуют equal-width glyph'ов.

## 1. Цель этапа J (MVP)

Сделать TUI, через который реально проходится сценарий `mvp_skirmish`
(и любой другой YAML-сценарий из `data/content/scenarios.yaml`),
**без потери ни одной существующей возможности CLI**:

* Attack / Move / Dodge / Dash / Disengage / End turn.
* Live-обновление карты, лога, очерёдности инициативы, статуса PC.
* Две темы (`color` по умолчанию, `monochrome`).
* Запускаемый headless через `textual.pilot.Pilot` — основа для e2e
  тестов.

Чего **нет** в MVP J (по плану — этап K и далее):

* Анимация атаки (UI mockup C.2). Только статичная перерисовка после
  каждого RollApplied.
* Спрайты medium/large зума (UI mockup §4, B.2/B.3). На MVP — только
  small (1 клетка = 1 ячейка).
* Hot-seat, мастер-панель, level-up overlay, death-save overlay
  (UI.md §8, mockup C.5/C.6).
* Локализация (etap I18N). Все строки — `en`, как и в CLI.
* Inventory / Character sheet экраны (mockup §02).

---

## 2. Принципы (инвариант)

| # | Инвариант | Обоснование |
|---|---|---|
| 1 | `application/` и `domain/` НЕ импортируют `textual`. | Hexagonal. UI — адаптер, не правила. |
| 2 | TUI висит на тех же портах, что CLI: `PlayerIntentProvider`, `EventBus.subscribe`. | Один движок, два фронта. Подтверждено аудитом 15. |
| 3 | `GameRunner.run()` остаётся **синхронным**. | Не переписываем application под async ради UI. Адаптер «синхронизирует» сам. |
| 4 | Тесты TUI запускаются через `textual.pilot.Pilot` (headless), без реального TTY. | Совместимость с CI; ScriptedRNG детерминирует исход. |
| 5 | Цвета — только через CSS-переменные в `.tcss` (см. UI.md §3.3). | Тема — одна точка истины; без хардкода в виджетах. |
| 6 | `import textual` — **только в `interfaces/tui/`**. Никаких lazy-импортов в `composition.py` / `interfaces/cli/`. | Чёткая граница; CLI не зависит от textual. |

Инвариант 6 уточнение: `dnd play --tui` живёт в `interfaces/cli/app.py`,
импорт `dnd.interfaces.tui` происходит **внутри функции `play`**, не
на уровне модуля. Тогда `dnd play --no-tui` не тащит textual в память
и не падает, если textual не установлен.

---

## 3. Структура каталога

```
src/dnd/interfaces/tui/
  __init__.py           — публичный API (TuiApp, run_tui)
  app.py                — TuiApp(textual.App), маршрутизация экранов
  themes/
    color.tcss          — основная тема (UI.md §3.1)
    monochrome.tcss     — bw-тема для скриншотов / colorblind (UI.md §3.2)
  screens/
    battle.py           — BattleScreen — основной экран боя
    target_picker.py    — модальный экран выбора цели атаки
    move_picker.py      — модальный экран выбора клетки движения
    end_screen.py       — модальный экран Victory / Defeat / Draw
  widgets/
    map_widget.py       — MapWidget: ASCII-карта (small-zoom)
    log_widget.py       — LogWidget: журнал событий (RichLog)
    status_widget.py    — StatusWidget: HP/AC/Init/economy PC
    initiative_widget.py — InitiativeWidget: список инициативы
  bridge/
    intent_provider.py  — TuiIntentProvider — адаптер PlayerIntentProvider
    event_renderer.py   — EventRenderer — подписчик EncounterEvent → виджеты
    runner_worker.py    — обёртка для запуска GameRunner в треде
```

**Никаких** других файлов в `interfaces/tui/` на этапе J.

---

## 4. Архитектура: «два потока, один движок»

Главная архитектурная задача — соединить:

* **синхронный** `GameRunner.run(encounter)`, который опрашивает
  `PlayerIntentProvider.next_intent` (блокирующий вызов);
* **асинхронный** Textual event loop, который рисует UI и собирает
  ввод.

Решение — **threaded worker**:

```
┌─ Main thread (Textual event loop) ──────────────────────────────┐
│                                                                  │
│   TuiApp                                                         │
│    └─ BattleScreen                                               │
│         ├─ MapWidget                                             │
│         ├─ StatusWidget        ◄── update_from_event()           │
│         ├─ InitiativeWidget         (post_message via            │
│         ├─ LogWidget                 app.call_from_thread)       │
│         └─ Bindings: a/m/d/h/g/q                                 │
│                                                                  │
└──┬───────────────────────────────────────────┬───────────────────┘
   │ events  (textual.Message via              │ intents
   │  call_from_thread)                        │  (queue.Queue.put)
   ▼                                           ▲
┌─ Worker thread (GameRunner.run) ─────────────┴──────────────────┐
│                                                                  │
│   GameRunner ─► TuiIntentProvider.next_intent(actor, ctx, enc)  │
│                  │                                               │
│                  └─ blocks on intent_queue.get()                 │
│                                                                  │
│   EncounterEvent ─► EventRenderer.handle(event)                  │
│                      └─ app.call_from_thread(widget.refresh, ...)│
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Контракт.**

* `intent_queue: queue.Queue[PlayerIntent]` — TUI кладёт, провайдер
  забирает. Один pending intent максимум; провайдер блокируется на
  `get()` без таймаута (бой не «деградирует» от долгого размышления
  игрока).
* `EventRenderer` подписан на `EventBus` синхронно (как и
  `EventPrinter` в CLI), но каждое обновление виджета делается через
  `app.call_from_thread(widget.method, ...)`. Это thread-safe API
  Textual для записи из не-event-loop треда.
* Worker thread демонический (`daemon=True`); если Textual закрылся
  (`Ctrl+C` / `Q`), worker умирает вместе с процессом, encounter не
  «дописывается».

**Завершение.** GameRunner возвращается из `run()` после
`EncounterEnded`. EventRenderer ловит это событие и переключает
TuiApp на `EndScreen`. Игрок жмёт «Quit» — приложение закрывается.

---

## 5. Адаптер PlayerIntentProvider — TuiIntentProvider

Контракт `PlayerIntentProvider` (см. `application/ports/player_intent_provider.py`):

```python
def next_intent(self, actor, ctx, encounter) -> PlayerIntent: ...
```

Реализация TUI:

```python
class TuiIntentProvider:
    """Адаптер: ждёт, пока главный тред Textual положит intent в очередь."""

    def __init__(self, intent_queue: queue.Queue[PlayerIntent],
                 turn_signal: Callable[[Creature, TurnContext, Encounter], None]):
        self._queue = intent_queue
        self._turn_signal = turn_signal  # call_from_thread(BattleScreen.set_turn, ...)

    def next_intent(self, actor, ctx, encounter):
        self._turn_signal(actor, ctx, encounter)
        return self._queue.get()  # blocks worker thread
```

Главный тред (Textual):

* `BattleScreen.set_turn(actor, ctx, encounter)` — обновляет
  StatusWidget «active actor», MapWidget «cursor near actor», блок
  ActionsWidget по `ctx.action_used / bonus_used / movement_remaining`.
* Игрок нажимает клавишу действия → BattleScreen открывает picker (если
  нужен) → формирует `PlayerIntent` → `intent_queue.put(intent)`.

PC- vs monster-turn: для не-PARTY actor'а `BattleScreen.set_turn`
скрывает action-меню, показывает «… AI thinking». GameRunner вызывает
`take_monster_turn` в worker-треде; `TuiIntentProvider.next_intent`
вообще не дёргается (его зовёт только `_run_pc_turn`).

---

## 6. Виджеты — минимальный набор (J MVP)

### 6.1 MapWidget (Static / Canvas)

* Small-zoom: 1 клетка = 1 ячейка терминала (UI mockup B.1).
* Символы: `@` PC, `g` enemy, `n` neutral, `#` wall, `,` difficult,
  `.` floor, `+` closed door, `=` low cover, `H` high cover, `_` pit,
  `[X]` cursor.
* Стек существ: символ старшего по приоритету (PC > friendly > enemy
  > neutral) + цифра, если их > 1 (`@2`). В J MVP стек редок — гарант
  `Battlefield.creatures_at(square)`.
* Подсветка через CSS-классы:
  - `.cell-pc`, `.cell-enemy`, `.cell-wall`, `.cell-difficult`,
    `.cell-cursor`.

### 6.2 StatusWidget (Static)

Формат строки (80×24):
```
{name}  HP {cur}/{max}  AC {ac}  Init {init}  | act:{Y|N} bonus:{Y|N} react:{Y|N}  spd:{ft}
```

* Обновление — на каждое `TurnStarted` (новый actor) и каждое
  `DamageDealt` / `HealingApplied` (HP актуального актора в фокусе).

### 6.3 LogWidget (RichLog)

* Формат строк — тот же, что у `EventPrinter` в CLI (см.
  `interfaces/cli/event_printer.py`). На MVP **переиспользуем
  `EventPrinter` как форматтер**: подаём ему `rich.console.Console` с
  буфером, забираем строки, шлём в `RichLog`. Это исключает
  расхождение «лог в CLI ≠ лог в TUI».

### 6.4 InitiativeWidget (ListView / Static)

* Список `{n} {marker} {name} {init}` для каждого живого участника.
* Маркер `▶` у текущего; `✗` у мертвых.
* Перерисовка на `InitiativeRolled` (старт), `TurnStarted`,
  `CreatureDowned`.

### 6.5 ActionsWidget

* Реализуется через `BINDINGS` BattleScreen + Footer Textual.
* Привязки:
  - `a` — Attack (открывает TargetPicker)
  - `m` — Move (открывает MovePicker)
  - `d` — Dodge
  - `h` — Dash (не путать с глифом `H` высокого cover на карте)
  - `g` — Disengage
  - `e` — End turn
  - `q` — Quit (мгновенно; confirm-диалог — пост-MVP).
* После EncounterEnded BattleScreen помечает себя `_concluded`;
  все action-handlers сразу выходят без putного intent'а — клавиши
  «не реагируют». Фокус переходит на EndScreen (§6.8).

### 6.8 EndScreen (модальный)

Точка фокуса после `EncounterEnded` (TUI.md §3, §4). Показывает:
* вердикт — «PARTY WINS» / «MONSTERS WINS» / «DRAW»;
* номер раунда;
* список survivors (либо «No survivors»).

Binding: `Enter` / `Esc` / `Q` → `app.exit()`. Закрытие EndScreen
автоматически закрывает приложение — TUI MVP не предполагает
переход в новый бой (нужен главное меню — пост-MVP).

### 6.6 TargetPicker (ModalScreen)

* Получает на вход `actor` + список валидных целей (тех же, что
  `_list_reachable_hostiles` в CLI).
* `Tab` / `Shift+Tab` циклит, `Enter` подтверждает, `Esc` отменяет.
* Возвращает `AttackIntent(target_id=...)` или `None` (отмена).

### 6.7 MovePicker (ModalScreen)

* Курсор по карте (`←↑↓→`), `Enter` подтверждает клетку.
* Path-preview: chebyshev-путь от actor к курсору (тот же
  `_chebyshev_path` из CLI, перенесённый в общий helper).
* `Esc` отменяет.

---

## 7. Темы

Две `.tcss`-таблицы (`UI.md §3.1`/§3.2):

```css
/* color.tcss */
$pc-fg: ansi_bright_yellow;
$enemy-fg: ansi_red;
$friendly-fg: ansi_cyan;
$wall-fg: white 50%;
$dim-fg: white 30%;
$effect-fg: ansi_magenta;
$object-fg: ansi_blue;

.cell-pc       { color: $pc-fg; text-style: bold; }
.cell-enemy    { color: $enemy-fg; }
.cell-friendly { color: $friendly-fg; }
.cell-wall     { color: $wall-fg; }
.cell-difficult{ color: $dim-fg; }
.cell-cursor   { background: $effect-fg; color: black; }
```

```css
/* monochrome.tcss */
$pc-fg: white;
$enemy-fg: white;
$wall-fg: white 60%;
...

.cell-pc       { text-style: bold; }
.cell-enemy    { text-style: reverse; }
.cell-wall     { color: $wall-fg; }
.cell-difficult{ text-style: italic; color: $dim-fg; }
.cell-cursor   { text-style: reverse bold; }
```

Выбор темы — `dnd play --tui --theme color|monochrome` (default
`color`). Hot-reload через `app.refresh_css()` — не входит в MVP J.

---

## 8. Точка входа

`dnd play [scenario_id] [--tui|--no-tui] [--theme color|monochrome]`

* Default: `--no-tui` (как сейчас) — CLI. Меняем default на
  `--tui` **после** J-аудита и подтверждения играбельности.
* `--no-tui` оставляем для скриптов, CI, и для пользователей в SSH без
  поддержки TUI.

```python
@app.command("play")
def play(scenario_id, content_dir, tui=False, theme="color"):
    repo = ...
    scenario = ...
    services = build_default_runtime_services()
    encounter = build_encounter_from_scenario(scenario, content=repo, services=services)

    if tui:
        from dnd.interfaces.tui import run_tui
        run_tui(encounter=encounter, theme=theme)
    else:
        # текущий CLI-путь
        ...
```

`run_tui` собирает `intent_queue`, `TuiIntentProvider`,
`EventRenderer`, `TuiApp` и запускает её. Внутри `TuiApp.on_mount`
поднимается worker-thread с `GameRunner.run`. Worker завершается —
EventRenderer переключает на EndScreen.

---

## 9. Тестирование

### 9.1 Unit (виджеты, рендер карты)

* `tests/unit/interfaces/tui/test_map_widget.py` — стабильный
  ASCII-рендер карты по `Battlefield` + позициям существ.
* `tests/unit/interfaces/tui/test_event_renderer.py` — рендерер
  раскладывает события по правильным виджетам (моки виджетов).

### 9.2 Integration (TuiIntentProvider)

* `tests/integration/tui/test_intent_provider.py` — providers
  блокируется на пустой очереди; разблокируется при `put(intent)`;
  возвращает intent правильно типизированный.

### 9.3 E2E (Pilot)

* `tests/e2e/test_tui_play.py` — запуск `TuiApp` в headless через
  `App.run_test(...)`:
  1. Сценарий `mvp_skirmish` с ScriptedRNG (фиксированные ролы для
     детерминизма).
  2. Pilot жмёт `a` → Tab → Enter → `e` (атаковать первую цель и
     закончить ход).
  3. Дать пройти ещё несколько ходов AI.
  4. Дождаться EndScreen с `winners is Faction.PARTY`.

Headless TUI работает без TTY (`width=80, height=24` явно
указываются). Это критично для CI.

---

## 10. Open questions / решения, отложенные после J MVP

| ID | Вопрос | Решение к этапу J |
|---|---|---|
| TUI-O1 | Hot-seat: несколько PC, передача управления через PIN. | Не делаем; контракт `PlayerIntentProvider.next_intent` уже принимает `actor` — расширение прозрачное (UI.md §8). |
| TUI-O2 | i18n (UI.md §6, I18N.md). | Не делаем; все строки `en`. После K/L. |
| TUI-O3 | Анимация атаки (UI mockup C.2). | Не делаем; после MVP — модальный transient overlay на 600 ms. |
| TUI-O4 | Спрайты medium/large зума. | Не делаем; small-zoom покрывает все мокапы Раздела A.1. |
| TUI-O5 | Master live-panel. | Заложен в архитектуре (`MasterIntent` уже discriminated union); экран добавляется отдельно после level-up / inventory. |
| TUI-O6 | Hot-reload `.tcss` при смене темы в рантайме. | Не делаем; `--theme` только при старте. |

Эти отложенные пункты **не блокируют MVP**, но не должны требовать
ломающих изменений в архитектуре «два потока, один движок» (§4)
и в адаптере провайдера (§5).

---

## 11. Definition of Done — этап J

* `pip install -e .` ставит `textual>=0.78,<1.0`.
* `dnd play --tui mvp_skirmish` запускает Textual-приложение,
  сценарий проходится клавиатурой до Victory или Defeat.
* `dnd play --tui --theme monochrome` рисует ту же сцену в bw-теме.
* Headless e2e-тест проходит сценарий через Pilot и
  подтверждает `winners is Faction.PARTY` детерминированно.
* `mypy src/` чистый, `ruff check` чистый, **никакой `import textual`
  вне `src/dnd/interfaces/tui/`**.
* J-аудит закрыт без S0; S1, если найдены, — фиксы отдельным
  коммитом `fix(audit-NN)`.
