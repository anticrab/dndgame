# ARCHITECTURE — структура проекта и паттерны

Документ описывает **как** устроен код. **Что** он делает — в
[DESIGN.md](DESIGN.md). Геймплейные решения — в [ROADMAP.md](ROADMAP.md),
[ENGINE.md](ENGINE.md), [UI.md](UI.md), [PROGRESSION.md](PROGRESSION.md),
[MASTER.md](MASTER.md), [I18N.md](I18N.md).

Главный принцип — **гексагональная архитектура** (порты и адаптеры) с
явным разделением на четыре слоя, без зависимостей «изнутри наружу».

```
┌──────────────────────────────────────────────────────────────┐
│ interfaces/      ─ адаптеры на стороне пользователя          │
│   cli/            Typer-команды                              │
│   tui/            Textual UI (2 темы: color, monochrome)     │
│   controllers/    UserInterface-реализации поверх TUI/CLI    │
├──────────────────────────────────────────────────────────────┤
│ application/     ─ use-cases и центральный движок            │
│   engine/         GameEngine (тиковый автомат),              │
│                   DiceRoller, DiceStatistics,                │
│                   master_ops (вмешательство мастера)         │
│   ports/          интерфейсы (Protocol) к внешнему миру:     │
│                   ContentRepository, SaveRepository,         │
│                   UserInterface, RNG, EventBus               │
│   services/       CharacterCreationService, ContentService,  │
│                   SaveService, ScenarioRuntime               │
│   dto/            PlayerCommand, MasterIntent, EngineEvent,  │
│                   *View — pydantic-DTO, JSON-сериализуемые   │
├──────────────────────────────────────────────────────────────┤
│ domain/          ─ чистая модель правил                      │
│   entities/       Creature, Character, Encounter, Location,  │
│                   Item, Spell, Battlefield, Scenario         │
│   values/         AbilityScore, Modifier, DiceExpr, Square,  │
│                   HitPoints, DamageType, Alignment           │
│   rules/          attack_roll, save, damage, ability_check,  │
│                   initiative, proficiency, leveling, rest    │
│   conditions/     базовый Condition + регистр                │
│   actions/        базовый Action + регистр                   │
│   features/       базовый Feature + регистр                  │
│   events.py       доменные события                           │
├──────────────────────────────────────────────────────────────┤
│ infrastructure/  ─ адаптеры наружу                           │
│   db/             SQLite-схема, миграции, репозитории        │
│   content/        YAML-загрузчики, pydantic-схемы, сидер     │
│   rng/            RealRNG, ScriptedRNG                       │
│   ai/             MonsterAI-стратегии                        │
│   events/         InMemoryEventBus                           │
│   i18n/           Babel-обёртка (см. I18N.md)                │
│   logging/        логи и форматтер                           │
└──────────────────────────────────────────────────────────────┘
```

Направление зависимостей: `interfaces → application → domain ← infrastructure`.
`domain` не знает ни про SQLite, ни про CLI, ни про YAML, ни про i18n.
`infrastructure` знает про `domain` (реализует репозитории на его терминах),
но не про `interfaces`.

---

## 1. Используемые паттерны

| Паттерн | Где |
|---|---|
| **Repository** | `application/ports/*Repository` + `infrastructure/db/*RepositoryImpl`. По требованию `req.md`. |
| **Strategy** | `MonsterAI`, `LevelUpStrategy`, `AbilityGenerationStrategy` (Standard/Random/PointBuy), `XpCurve`, `DistanceMetric`. |
| **Factory** | `MonsterFactory.from_id(id)` поверх репозитория. |
| **Builder** | `CharacterBuilder`, `EncounterBuilder`. |
| **Command** | `Action`/`BonusAction`/`Reaction` — объект-команда с `execute`. |
| **Observer / EventBus** | `EventBus.publish(event)` + подписчики: сценарий, состояния, журнал, UI, статистика бросков. |
| **State** | `GameEngine` режимы, `Encounter` (Setup→InProgress→Ended), `Creature.status_tracker`, спасброски от смерти. |
| **Specification** | условия в сценариях (`HasFlag("x") & AbilityCheckPassed("STR", 15)`). |
| **Plugin / Registry** | `FeatureRegistry`, `ConditionRegistry`, `ActionRegistry`, `MonsterAIRegistry`. Регистрация по имени через декоратор. |
| **Adapter** | YAML-схема → доменный объект, CLI-аргументы → команды use-case. |
| **Hexagonal / Ports & Adapters** | базовая макро-структура. |
| **DTO** | `application/dto/` — pydantic-модели для пересечения границы (UI/CLI/будущий сетевой клиент). |

---

## 2. Структура каталогов

```
bmstu/dndgame/
├── pyproject.toml
├── README.md
├── Makefile
├── docs/
│   ├── DESIGN.md
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── ENGINE.md
│   ├── UI.md
│   ├── PROGRESSION.md
│   ├── MASTER.md
│   ├── I18N.md
│   ├── SCENARIO_DEMO.md
│   ├── OPEN_QUESTIONS.md
│   └── ADR/
│       ├── 0001-hexagonal-architecture.md
│       └── 0002-square-grid.md
├── content/
│   ├── core/
│   │   ├── species/*.yaml
│   │   ├── classes/*.yaml
│   │   ├── backgrounds/*.yaml
│   │   ├── items/{weapons,armor,gear,magic}/*.yaml
│   │   ├── spells/*.yaml
│   │   ├── monsters/*.yaml
│   │   ├── features/*.yaml
│   │   ├── sprites/*.yaml
│   │   └── tables/*.yaml
│   ├── scenarios/
│   │   └── hollow-oak-mine/
│   │       ├── scenario.yaml
│   │       ├── locations/*.yaml
│   │       ├── encounters/*.yaml
│   │       └── dialogues/*.yaml
│   └── homebrew/
├── src/
│   └── dnd/
│       ├── __init__.py
│       ├── i18n/
│       │   ├── translator.py
│       │   └── locales/
│       │       ├── messages.pot
│       │       ├── en/LC_MESSAGES/dnd.po
│       │       └── ru/LC_MESSAGES/dnd.po
│       ├── domain/
│       │   ├── values/
│       │   │   ├── ability.py
│       │   │   ├── dice.py
│       │   │   ├── damage.py
│       │   │   ├── square.py
│       │   │   ├── hit_points.py
│       │   │   ├── money.py
│       │   │   ├── alignment.py
│       │   │   └── loc_str.py        # LocStr — bilingual поле
│       │   ├── entities/
│       │   │   ├── creature.py
│       │   │   ├── character.py
│       │   │   ├── monster.py
│       │   │   ├── item.py
│       │   │   ├── spell.py
│       │   │   ├── encounter.py
│       │   │   ├── battlefield.py    # квадратная сетка
│       │   │   ├── location.py
│       │   │   ├── scenario.py
│       │   │   └── game_state.py
│       │   ├── rules/
│       │   │   ├── attack.py
│       │   │   ├── save.py
│       │   │   ├── damage.py
│       │   │   ├── ability_check.py
│       │   │   ├── initiative.py
│       │   │   ├── proficiency.py
│       │   │   ├── leveling.py
│       │   │   ├── distance.py       # Chebyshev / опц. 1-2-1
│       │   │   └── rest.py
│       │   ├── conditions/
│       │   ├── actions/
│       │   ├── features/
│       │   └── events.py
│       ├── application/
│       │   ├── engine/
│       │   │   ├── game_engine.py        # центральный объект
│       │   │   ├── dice_roller.py        # ComputerDiceRoller (default)
│       │   │   ├── dice_stats.py         # DiceStatisticsService
│       │   │   ├── master_ops.py         # реализации MasterIntent (для тестов и будущего UI)
│       │   │   ├── encounter_loop.py
│       │   │   ├── exploration_loop.py
│       │   │   └── scenario_runtime.py   # = AutoGameMaster по факту
│       │   ├── ports/
│       │   │   ├── content_repository.py
│       │   │   ├── save_repository.py
│       │   │   ├── user_interface.py
│       │   │   ├── rng.py
│       │   │   ├── event_bus.py
│       │   │   └── monster_ai.py
│       │   ├── services/
│       │   │   ├── content_service.py
│       │   │   ├── character_creation_service.py
│       │   │   └── save_service.py
│       │   │   # тонкого «GameSession» больше нет — все сценарии входят
│       │   │   # в GameEngine.new_session()/load_session() напрямую
│       │   └── dto/
│       │       ├── player_command.py
│       │       ├── master_intent.py      # есть с MVP, дёргается из тестов
│       │       ├── engine_event.py
│       │       ├── views.py              # *View для UI
│       │       └── envelope.py           # обёртка для будущего транспорта
│       ├── infrastructure/
│       │   ├── db/
│       │   ├── content/
│       │   ├── rng/
│       │   ├── ai/
│       │   ├── events/
│       │   ├── i18n/
│       │   └── logging/
│       └── interfaces/
│           ├── cli/
│           │   ├── app.py
│           │   ├── commands/
│           │   │   ├── character.py
│           │   │   ├── play.py
│           │   │   ├── db.py
│           │   │   ├── content.py
│           │   │   └── settings.py
│           │   └── renderers/
│           ├── tui/
│           │   ├── app.py
│           │   ├── screens/
│           │   │   ├── menu.py
│           │   │   ├── character_creation.py
│           │   │   ├── character_sheet.py
│           │   │   ├── exploration.py
│           │   │   ├── combat.py
│           │   │   ├── inventory.py
│           │   │   ├── journal.py
│           │   │   ├── dice_stats.py
│           │   │   ├── pause.py
│           │   │   ├── settings.py
│           │   │   └── handover.py       # передача управления (hot-seat готовность)
│           │   ├── widgets/
│           │   │   ├── crt_frame.py
│           │   │   ├── battle_map.py     # рендерит квадраты
│           │   │   ├── initiative_strip.py
│           │   │   ├── legend.py
│           │   │   ├── luck_indicator.py
│           │   │   └── sprite.py
│           │   └── themes/
│           │       ├── color.tcss
│           │       └── monochrome.tcss
│           └── controllers/
│               └── ui_user_interface.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── scripts/
    ├── seed_db.py
    └── i18n/
        ├── extract.sh
        ├── update.sh
        └── compile.sh
```

---

## 3. Ключевые интерфейсы (порты)

### 3.1 `ContentRepository`

```python
class ContentRepository(Protocol):
    def get_species(self, species_id: str) -> Species: ...
    def list_species(self) -> list[Species]: ...
    def get_class(self, class_id: str) -> CharacterClass: ...
    def list_classes(self) -> list[CharacterClass]: ...
    def get_background(self, bg_id: str) -> Background: ...
    def get_item(self, item_id: str) -> Item: ...
    def get_spell(self, spell_id: str) -> Spell: ...
    def get_monster(self, monster_id: str) -> Monster: ...
    def get_scenario(self, scenario_id: str) -> Scenario: ...
    def get_sprite(self, sprite_id: str) -> Sprite: ...
    def get_table(self, table_id: str) -> RandomTable: ...
```

Реализаций две: `SqliteContentRepository` (продукт) и
`InMemoryContentRepository` (тесты). YAML-сидер заполняет SQLite при
`dnd db seed`.

### 3.2 `SaveRepository`

```python
class SaveRepository(Protocol):
    def list_saves(self) -> list[SaveMeta]: ...
    def save(self, name: str, state: GameState) -> SaveMeta: ...
    def load(self, save_id: int) -> GameState: ...
    def delete(self, save_id: int) -> None: ...
    def saves_for_scenario(self, scenario_id: str) -> list[SaveMeta]: ...
```

Последний метод нужен для проверки «есть ли сейвы по сценарию» при
попытке его изменить (см. `OPEN_QUESTIONS.md` Q12).

`GameState` сериализуется в JSON BLOB; **история партии** (`GameLog`) —
часть `GameState`, см. `ENGINE.md` §5.

### 3.3 `UserInterface`

Главный порт ввода-вывода. Не знает, CLI это или TUI:

```python
class UserInterface(Protocol):
    # вывод
    def on_event(self, event: EngineEvent) -> None: ...
    def show_text(self, text_key: str, /, **vars: Any) -> None: ...
    def show_view(self, view: AnyView) -> None: ...

    # запросы
    def request_turn_intent(self, ctx: TurnContext) -> TurnIntent: ...
    def request_choice(self, prompt_key: str, options: list[Choice]) -> Choice: ...
    def request_target(self, ctx: TargetContext) -> Target: ...
    def request_confirm(self, prompt_key: str) -> bool: ...
```

`text_key` / `prompt_key` — ключи локализации (см. `I18N.md`).

### 3.4 `RNG`, `EventBus`

`RNG` уже реализован (`RealRNG`, `ScriptedRNG`). Над ним — `DiceRoller`
(см. `ENGINE.md` §7), который ядро правил вызывает напрямую.

`EventBus` — синхронная in-memory publish/subscribe. Подписчики:
- `ScenarioRuntime` (триггеры сценария);
- `DiceStatisticsService` (статистика);
- `UserInterface` (отображение);
- `GameLog` writer (история партии для сейва).

### 3.5 `MonsterAI`

```python
class MonsterAI(Protocol):
    def pick_intent(self, actor: Creature, ctx: TurnContext) -> TurnIntent: ...
```

Реализаций несколько. По умолчанию — `default_brawler` (атакует ближайшую
видимую цель с наименьшим HP).

---

## 4. GameEngine как центр

Подробности — в [ENGINE.md](ENGINE.md). Здесь — место в архитектуре.

`GameEngine` живёт в `application/engine/game_engine.py`. Все сервисы
(`ScenarioRuntime`, `CharacterCreationService`, `SaveService`) — фасады
над движком или его подсистемами, не параллельная иерархия.

Точка композиции — `interfaces/cli/app.py`, она:

1. читает конфиг (`platformdirs` или `--workdir`);
2. инициализирует i18n;
3. создаёт `RNG`, `EventBus`, `ContentRepository`, `SaveRepository`;
4. строит `GameEngine` с зависимостями;
5. создаёт `UserInterface` (CLI или TUI) и подписывает её на события;
6. запускает выбранную команду.

DI — простой: «руками собрать в `main`». Без контейнеров. Это
устраивает учебный проект и держит зависимости видимыми.

---

## 5. DTO и сериализация

Все обмены через границы движка — pydantic-модели:

- `PlayerCommand` — команда от обычного игрока (хочу атаковать, идти,
  использовать предмет, открыть инвентарь).
- `MasterIntent` — команда мастера (см. `MASTER.md`). В MVP не идёт
  снаружи, но тип существует и используется в тестах.
- `EngineEvent` — событие движка наружу.
- `*View` — состояние для рендера (`BattleView`, `CharacterSheetView`,
  ...).
- `Envelope` — обёртка `{type, payload, version, ts}` для будущего
  транспорта.

Все они `model_dump_json()` / `model_validate_json()`. Это даёт:

- сериализацию сейва;
- replay по логу;
- готовность к сети без переделок.

---

## 6. Стек и инструменты

| Назначение | Выбор | Причина |
|---|---|---|
| Управление зависимостями | **uv** (с fallback на pip) | быстрая установка, lock-файл, привычный pyproject. |
| Стандарт пакета | PEP 517 / pyproject.toml, src-layout | стандарт. |
| Версия Python | **3.11+** | `match`, `Self`, `tomllib`, `StrEnum`. |
| CLI | **Typer** | поверх Click, type-hint-friendly, тестируем. |
| Интерактивные промпты | **questionary** | удобный UX в CLI без TUI. |
| TUI | **Textual** | CSS-подобная стилизация → 2 темы без боли. |
| YAML | **PyYAML** + **pydantic v2** | парсинг + валидация. |
| БД | **sqlite3** (stdlib) | требование задачи; явный SQL, явный Repository. |
| Логи | **logging** + **rich** | rich — только в CLI-слое. |
| i18n | **Babel** + **gettext** | `.po`/`.mo`, см. `I18N.md`. |
| Тесты | **pytest**, **pytest-cov**, **hypothesis** | property-based для костей. |
| Линтер/форматер | **ruff** | один инструмент. |
| Типы | **mypy** (strict в domain/application) | защита домена. |
| Pre-commit | **pre-commit** | автозапуск ruff/mypy/pytest-quick. |

---

## 7. Поток типичной сессии

```
1. dnd play
   └─ interfaces/cli/commands/play.py
      └─ compose_root() → GameEngine, UI
         ├─ SaveRepository.list_saves()        (если есть — спросить «продолжить?»)
         ├─ CharacterCreationService.create_party()
         │    └─ UI диалоги + ContentRepository.list_species/classes/...
         ├─ GameEngine.new_session(scenario, party)
         └─ цикл:
            command = UI.request_next_command()
            result  = GameEngine.step(command)
            EventBus → UI.on_event(...)        # перерисовка
            UI.show_view(result.view)
            on END: SaveService.save() и exit к меню
```

В бою цикл такой же — просто `command`-ы исходят из `TurnIntentProvider`
для PC (через UI) или `MonsterAI` для NPC.

---

## 8. Гранулярность модулей и SOLID

- **SRP**: один файл — один доменный объект или одно правило.
- **OCP**: новый класс/раса/состояние — новый YAML + опц. плагин-класс;
  ядро не правим.
- **LSP**: все `Condition` подчиняются единому контракту жизненного
  цикла (`on_apply`, `on_remove`, `tick`); все `Action` имеют единое
  `execute`.
- **ISP**: вместо одного «бога» `UserInterface` — узкие методы. Если
  начнёт распухать — разделим (`InputPort`, `OutputPort`, ...).
- **DIP**: `application` зависит от `Protocol`-интерфейсов; конкретные
  реализации внедряются в `compose_root` в `interfaces/cli/app.py`.

---

## 9. Конфигурация и точки входа

- `pyproject.toml` объявляет console_script `dnd = dnd.interfaces.cli.app:main`.
- Конфигурация — TOML-файл в `~/.config/dnd/config.toml` (через
  `platformdirs`): пути БД, контент, тема, язык, текст-спид.
- Перекрывается переменными среды и флагами CLI (`--workdir`, `--lang`,
  `--theme`).
- Загрузчик контента ищет паки в `content/core` (поставка), затем в
  `<workdir>/content/` (пользовательские).

---

## 10. Тестируемость

- Домен — pure-Python без I/O, тесты быстрые.
- Бросок костей — через DI; в тестах фиксируем `ScriptedRNG([20, 7, 1])`.
- Сценарии — прогоняем через `InMemoryContentRepository` + `RecordingUI`
  (mock-интерфейс с заранее заданными ответами).
- Property-based (hypothesis): кости, расчёт КД, сопротивление/уязвимость.
- Мастер-операции — отдельные юнит-тесты на каждую (`apply_master_intent`
  + проверка лога).

---

## 11. ADR

Решения с обоснованием — в `docs/ADR/NNNN-title.md`. Принятые на текущий
момент:

- [`ADR/0001-hexagonal-architecture.md`](ADR/0001-hexagonal-architecture.md) —
  гексагональная архитектура и SQLite через Repository.
- [`ADR/0002-square-grid.md`](ADR/0002-square-grid.md) — квадратная боевая
  сетка (1 клетка = 5 фут, 8 соседей, Chebyshev-дистанция).

Дополнительные ADR будут заводиться при принятии решений, которые
затрагивают несколько модулей и не очевидны из чтения кода.
