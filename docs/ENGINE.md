# ENGINE — игровой движок и боевая сетка

Документ описывает **центральный объект игры** — `GameEngine` — и его
ключевую механику: позиционирование на квадратной сетке, цикл боя,
событийную модель и **вмешательство мастера** (направление развития).

Уже зафиксировано в `DESIGN.md`/`ARCHITECTURE.md`: модель правил, паттерны,
слои. Здесь — детали, специфичные для движка.

---

## 1. GameEngine — что это

`GameEngine` (живёт в `application/engine/`) — единая точка управления
жизненным циклом игры. Это **тиковый автомат**.

Терминология:
- **Тик** — атомарный шаг времени для движка. В исследовании = «игрок ввёл
  команду / истёк таймер». В бою = «один интент существа применён».
- **Mode** — режим движка. Машина состояний:
  - `EXPLORATION` — игрок ходит по локациям и взаимодействует.
  - `COMBAT` — пошаговый бой на `Battlefield`.
  - зарезервировано: `DIALOGUE`, `REST`, `MENU`.

```
       new game
           │
           ▼
   ┌─────────────┐ enter combat   ┌──────────┐
   │ EXPLORATION │ ─────────────► │  COMBAT  │
   │             │ ◄───────────── │          │
   └─────────────┘ victory/flee   └──────────┘
           │
           ▼
        end
```

### 1.1 Ответственность

`GameEngine`:
- хранит активный `GameState` (партия, мир, журнал, активный сценарий);
- запускает/останавливает `Encounter`-ы и обновляет `Battlefield`;
- получает интенты от игроков (PC) и `MonsterAI` (NPC);
- применяет правила (через `domain/rules/`), порождает события;
- публикует события в `EventBus` — на них реагируют сценарий, UI, журнал,
  будущий live-мастер.

`GameEngine` **не**:
- не отвечает за вывод (UI слушает события);
- не знает про БД и YAML (контент приходит через `ContentRepository`).

### 1.2 Внешний API

```python
class GameEngine:
    def __init__(
        self,
        content: ContentRepository,
        rng: RNG,
        event_bus: EventBus,
        scenario_runtime: ScenarioRuntime,
        ai_registry: MonsterAIRegistry,
    ) -> None: ...

    # сессия
    def new_session(self, scenario_id: str, party: Party) -> SessionId: ...
    def load_session(self, snapshot: GameSnapshot) -> SessionId: ...
    def snapshot(self) -> GameSnapshot: ...

    # внешний цикл
    def step(self, command: PlayerCommand) -> StepResult: ...
    def state(self) -> EngineStateView: ...

    # вмешательство (пост-MVP, см. §6); сейчас доступен только для тестов
    def apply_master_intent(self, intent: MasterIntent) -> StepResult: ...
```

UI вызывает `step(command)` после каждого ввода, получает `StepResult`
(список событий, новых запросов к игроку, изменение режима) и
перерисовывает.

`PlayerCommand` и `StepResult` — pydantic-DTO, сериализуемые в JSON. Это
даёт нам бесплатный путь к сетевому режиму и к замене UI: ядру всё равно,
кто отправил команду.

### 1.3 Источник интентов

Когда в бою наступает ход существа, движок спрашивает у соответствующего
**провайдера интентов**:

```python
class TurnIntentProvider(Protocol):
    def request_intent(self, ctx: TurnContext) -> TurnIntent: ...
```

- Для **PC** — провайдер реализован через `UserInterface` (CLI/TUI
  спрашивает игрока).
- Для **NPC** — провайдер реализован через `MonsterAI`-стратегию.

В MVP — один локальный игрок. Hot-seat (пост-MVP) — несколько PC, один
локальный UI, между ходами явная передача управления (см. `UI.md`).

---

## 2. Battlefield — поле боя

### 2.1 Сетка: квадратная

Решение: **квадратная сетка, 1 клетка = 5 футов** (стандарт книги).

- Координаты — целые `(x, y)`.
- 8 соседей: 4 ортогональных + 4 диагональных.
- **Дистанция — по правилам книги:** каждая клетка считается 5 футов
  **независимо от диагонали** (Chebyshev). Это упрощение 5e, явно
  допустимое книгой и DM-руководством.
- В будущем альтернативное правило «1-2-1» (по диагонали 7.5 фут) — это
  переключаемая стратегия `DistanceMetric`. Сейчас — только Chebyshev.

### 2.2 Несколько существ на одной клетке

Допустимо по решению архитектора. Правила:

- В одной клетке может стоять любое количество существ.
- Дружественные могут проходить через клетку друг друга свободно.
- Сквозь клетку враждебного — нельзя пройти насквозь (как и в 5e).
- Если в клетке несколько существ, UI рендерит:
  - **small-зум** — символ `+` или цифра «количество» вместо персонажа;
  - **medium/large-зум** — основной спрайт + маленький значок
    «N» в углу;
  - в легенде боя — раскладка «в клетке (3,5): @Аэлар, +Скелет1, +Скелет2».
- Все атаки и эффекты по клетке (`Огненный шар`, область) — задевают
  всех существ в клетке.
- Курсор-выбор цели циклически переключает существ в одной клетке
  (`Tab`).

### 2.3 Координаты и направления

```python
@dataclass(frozen=True, slots=True)
class Square:
    x: int
    y: int

DIRECTIONS_ORTHO = [Square(1,0), Square(0,1), Square(-1,0), Square(0,-1)]
DIRECTIONS_DIAG  = [Square(1,1), Square(-1,1), Square(-1,-1), Square(1,-1)]
DIRECTIONS_8     = DIRECTIONS_ORTHO + DIRECTIONS_DIAG
```

Команды в UI работают по сторонам света и/или по hjkl/стрелкам с
shift-диагоналями.

### 2.4 Что хранит Battlefield

- размеры карты (`width × height` в клетках);
- террейн каждой клетки (`floor`, `wall`, `difficult`, `pit`, `lava`,
  `chest`, `door:open|closed|locked`, ...);
- освещение (`bright`, `dim`, `dark`);
- укрытия по клеткам или по граням клеток (низкий бортик — half cover);
- занятость: `dict[Square, list[CreatureId]]` (множественные существа);
- объекты сценария (триггерные клетки).

Это **value/entity без I/O**. Рендеринг и UI — отдельно.

### 2.5 Алгоритмы

- **Дистанция** — Chebyshev: `max(|dx|, |dy|)`. О(1).
- **Линия видимости** — алгоритм Брезенхэма + проверка на стены и
  тёмные клетки.
- **Зона досягаемости** — для рукопашной атаки оружие с `reach=5ft`
  достаёт до клеток на расстоянии 1; `reach=10ft` — до 2.
- **Поиск пути** — A* по соседям (8 направлений) с учётом
  труднопроходимой местности (стоимость 2). На MVP — без сглаживания.
- **Провоцированная атака** — при перемещении: если существо выходит
  из клетки, соседней врагу (8-соседство), и враг видит его и имеет
  реакцию — событие.

### 2.6 Карта в YAML сценария

```yaml
encounter: gnoll-ambush
map:
  width: 10
  height: 8
  legend:
    .: floor
    "#": wall
    ",": difficult
    "^": trap_dart
    o: chest_closed
    +: door_closed
  grid: |
    ##########
    #........#
    #...,,...#
    #...,,...#
    #.....o..#
    #........#
    #........#
    ##########
spawns:
  pc:      [{ at: [3, 6], who: party }]
  monsters:
    - { at: [1, 4], who: goblin }
    - { at: [8, 4], who: goblin_archer }
```

Точные координаты, никаких «полусдвигов». ASCII-карта в YAML
читается как игровое поле.

---

## 3. Цикл боя

Точное повторение правил книги:

```
ENTER ─► RollInitiative ─► SurpriseCheck ─► [Round]
                                            │
                                            ▼
                            for actor in initiative_order:
                                ─► OnTurnStart (тики состояний)
                                ─► request_intent(actor)
                                ─► apply(intent)
                                ─► OnTurnEnd
                            round += 1; loop or ─► END
```

Каждый переход публикует события:
`InitiativeRolled`, `TurnStarted(actor)`, `MoveExecuted(path)`,
`AttackRolled(actor, target, roll)`, `DamageDealt(...)`,
`ConditionApplied(...)`, `CreatureDowned(...)`, `EncounterEnded(victors)`.

UI рисует анимацию на основе событий (мигание клетки, бегущая полоска
HP). Скорость анимации — параметр UI; движок не ждёт.

---

## 4. Действия — Command-объекты

```python
class Action(Protocol):
    id: str
    name_key: str   # ключ локализации, см. I18N.md

    def can_perform(self, actor: Creature, ctx: TurnContext) -> Availability: ...
    def execute(self, actor: Creature, params: ActionParams, ctx: TurnContext) -> Outcome: ...
```

- `Availability` — результат с причиной отказа (`paralyzed`, `out_of_range`,
  `no_spell_slot`), не голым bool.
- `params` — типизированная DTO (для атаки: цель + оружие; для заклинания:
  цель/область + ячейка).
- Реестр `ActionRegistry` — открытая система: добавил класс — зарегистрировал
  — доступен.

Реакции — отдельный реестр; UI спрашивает у игрока подтверждение в момент
триггера.

---

## 5. EventBus, GameLog, история партии

### 5.1 Контракт EventBus

```python
class EventBus(Protocol):
    def publish(self, event: EngineEvent) -> None: ...
    def subscribe(
        self,
        event_type: type[E],
        handler: Callable[[E], None],
    ) -> Unsubscribe: ...
```

Реализация по умолчанию — `InMemoryEventBus` в `infrastructure/events/`.

### 5.2 Семантика (явный контракт)

1. **Синхронность.** `publish()` обрабатывает событие в текущем потоке,
   возвращает управление после того, как все подписчики отработали.
2. **FIFO порядок.** Все события движка ставятся в **очередь FIFO**. Если
   подписчик внутри своего обработчика делает `bus.publish(other_event)`,
   `other_event` ставится **в хвост** текущей очереди, а не выполняется
   рекурсивно. Это даёт детерминированный обход «волнами».
3. **Подписки во время dispatch.** Изменения списка подписчиков (`subscribe`
   или `unsubscribe`) во время `dispatch` применяются **с следующей**
   публикации, а не задним числом к текущей.
4. **Исключения подписчиков.** Если handler-подписчик кидает исключение —
   оно ловится `EventBus`, логируется как `ERROR` через `logging`, и
   обработка **продолжается** для остальных подписчиков. `publish()`
   снаружи ничего не raise-ит.
5. **Подписчик не получает свои же события.** Тех. деталь:
   `bus.publish(e)` внутри handler-а на `e2` не доставит `e` обратно
   тому же handler-у (если он подписан только на тип `e2`). Никаких
   циклов между «своими» событиями.

Эта семантика тестируется в `tests/unit/application/test_event_bus.py`
(будет добавлен в коммите Test-набора). При нарушении любого пункта —
тест падает; реализация исправляется, а не контракт.

### 5.3 GameLog и сейв

Каждое событие, прошедшее через `EventBus`, пишется в `GameLog`
(append-only список pydantic-моделей `EngineEvent`).

**Решение по сейвам:**
- `GameLog` сериализуется в сейв **целиком**. История партии не теряется.
- Хранение — JSON в BLOB-поле SQLite. Сжатие zlib опционально, если
  лог разрастётся.
- Удалили сейв — потеряли историю (это сознательное решение архитектора,
  см. `OPEN_QUESTIONS.md` Q10).

Это даёт:
- **Replay** — пересоздать UI-картинку по событиям.
- **Тесты** — проверка последовательности событий.
- **Отладку** — `dnd replay save:N` (пост-MVP).
- **Аудит вмешательств мастера** (см. §6).

---

## 6. Вмешательство мастера (направление развития)

Это пост-MVP фича, но архитектура движка **должна позволить** её
добавить без ломающих изменений. Описано подробно в `MASTER.md`;
здесь — только что движок должен уже сейчас поддерживать.

### 6.1 `MasterIntent` — discriminated union DTO

В отличие от `PlayerCommand` (заявка хода обычного игрока),
`MasterIntent` — команда «сверху», которую обрабатывает движок
**в любой момент** (не только в свой ход).

`MasterIntent` — это **discriminated union** на pydantic v2: каждая
операция мастера — отдельная типизированная модель с разделителем `kind`.
Это даёт mypy-полноту, IDE-автокомплит, валидацию по схеме и невозможность
ошибиться с полями payload.

```python
class _MasterIntentBase(BaseModel):
    reason: str                        # обязателен, идёт в лог
    issued_by: PlayerId                # автор вмешательства

class RerollIntent(_MasterIntentBase):
    kind: Literal["reroll"] = "reroll"
    roll_id: UUID

class SetRollIntent(_MasterIntentBase):
    kind: Literal["set_roll"] = "set_roll"
    roll_id: UUID
    raw_value: int                     # новое «выпавшее» d-X значение

class SetHpIntent(_MasterIntentBase):
    kind: Literal["set_hp"] = "set_hp"
    creature_id: CreatureId
    value: int

# ... аналогично для каждой операции из MASTER.md §3.
# Канонический полный список — в MASTER.md §3; ENGINE.md ссылается.

MasterIntent = Annotated[
    RerollIntent | SetRollIntent | SetHpIntent | ...,
    Field(discriminator="kind"),
]
```

Каноничный список **всех** операций мастера, их полей и поведения —
в [`MASTER.md`](MASTER.md) §3. ENGINE.md не дублирует список — он
является источником истины только для контракта `MasterIntent` как
типа и для семантики метода `apply_master_intent`.

Каждое применение пишется в `GameLog` с тегом `master_intervention` и
причиной (`reason`), заданной мастером.

### 6.2 Точки воздействия

`GameEngine` уже сейчас должен моделировать состояние так, чтобы
**снаружи** (через `apply_master_intent`) можно было:

1. **Перебросить любой бросок до момента, пока его результат ещё не
   повлиял на состояние.** Реализуется через двухфазную модель
   `RollIssued` → `RollApplied` (см. §7.4). Между двумя событиями мастер
   может прислать `RerollIntent(roll_id=...)` или
   `SetRollIntent(roll_id=..., raw_value=...)`. Без мастера эти два
   события следуют подряд без зазора.

2. **Менять HP/состояние существа** в любое время. Реализуется уже сейчас:
   `Creature.set_hp(value, source="master")`, метод доступен в ядре
   (для тестов), наружу — только через `apply_master_intent`.

3. **Накладывать преимущество/помеху** на следующий бросок — через
   создание модификатора с `effect: AdvantageEffect` и
   `duration: UntilNextRoll(creature_id)` (см. `MODIFIERS.md`). Очередь
   таких модификаторов живёт в `GameState.modifiers`. Первый же подходящий
   бросок применяет и снимает модификатор.

4. **Начать/закончить бой принудительно**: `ForceStartEncounterIntent`,
   `ForceEndEncounterIntent`.

5. **Спавнить/убирать существ** на карте: `SpawnCreatureIntent`,
   `RemoveCreatureIntent`.

6. **Прочие операции** — полный список в [`MASTER.md`](MASTER.md) §3.

### 6.3 Видимость

`MasterIntent` всегда применяется. Лог содержит запись (с причиной),
которую может видеть мастер. Обычные игроки **по умолчанию не видят**
факта вмешательства — UI игрока показывает «результат». Мастер видит
все вмешательства в своём журнале.

(Альтернатива «всем видно, что мастер вмешался» — пост-MVP опция в
настройках сценария: `master_transparency: hidden | tagged | full`.)

### 6.4 Что значит «заложить без интерфейсов»

По указанию архитектора **не вводим сейчас** портов `GameMaster`,
`MasterUI`, `Transport`. Но:

- В коде уже разделены два DTO — `PlayerCommand` и `MasterIntent` — и
  два метода движка: `step(command)` для обычных команд игрока,
  `apply_master_intent(intent)` для вмешательств мастера. Это один
  канонический путь, без альтернативных «двух веток одного `step()`».
- Все события движка проходят через `EventBus`.
- Все интенты сериализуемы.
- Где-то в `application/engine/master_ops.py` лежит модуль с реализациями
  каждой операции (`reroll`, `set_hp`, ...). Сейчас он вызывается
  только из тестов; в будущем — из UI мастера.

Это даёт возможность подключить мастера потом за **дни**, а не за
**месяцы**, без переписывания ядра.

---

## 7. DiceRoller и статистика бросков

Над портом `RNG` стоит слой **`DiceRoller`** (`application/engine/dice_roller.py`).

### 7.1 Контракт DiceRoller (канон)

```python
class DiceRoller(Protocol):
    def roll(self, expr: DiceExpr, ctx: RollContext) -> EngineRollResult: ...
```

`DiceRoller` живёт в `application/engine/dice_roller.py`. Это **единственная
точка** бросков для правил движка: ни одно правило (`attack_roll`, `save`,
`ability_check`, `damage_roll`) не вызывает `DiceExpr.roll(rng)` напрямую.

Прямой `DiceExpr.roll(rng)` остаётся доступным только для случаев, где
выпуск событий не требуется:

- генерация характеристик при создании персонажа (4d6kh3 в `CharacterBuilder`);
- внутренние unit-тесты домена;
- внутри реализации `ComputerDiceRoller`.

### 7.2 RollContext (DTO)

```python
class RollContext(BaseModel):
    purpose: Literal[
        "attack", "damage", "save", "ability_check",
        "initiative", "hit_dice", "death_save", "loot",
        "stats_gen", "other",
    ]
    actor_id: CreatureId | None = None
    target_id: CreatureId | None = None
    advantage: bool = False
    disadvantage: bool = False
    crit: bool = False
    extra_dice: list[DiceExpr] = []        # для добавочных кубов (Bless +1d4 и т.п.)
    tags: list[str] = []                   # для master_intervention и аудита
```

`extra_dice` — список выражений, которые добавляются к итоговому броску
(см. `MODIFIERS.md` §2.2 «DiceBonusEffect»). Кладёт их `ModifierApplier`
из списка активных модификаторов.

### 7.3 EngineRollResult (DTO)

```python
class EngineRollResult(BaseModel):
    roll_id: UUID                          # для master-перебросов
    expr: str                              # сериализованное DiceExpr
    raw: tuple[int, ...]                   # сырые броски d-X
    kept: tuple[int, ...]
    modifier: int                          # сумма numeric bonus + базовый mod
    extra_dice_rolls: tuple[int, ...] = () # отдельно — кости от extra_dice
    total: int                             # итог с учётом всего
    advantage: bool = False
    disadvantage: bool = False
    crit: bool = False
    context: RollContext
```

`roll_id` — единственная новинка относительно доменного `RollResult`.
Через него мастер делает `MasterIntent: reroll(roll_id)` или
`set_roll(roll_id, new_value)` — пока событие ещё не «применилось»
(см. §6.2 двухфазная модель).

### 7.4 Двухфазная модель бросков (RollIssued → RollApplied)

```
правило вызывает roller.roll(...)
        │
        ▼
  ┌──────────────────────────────────────┐
  │ ComputerDiceRoller:                  │
  │   raw = rng.roll(...)                │
  │   result = EngineRollResult(roll_id) │
  │   bus.publish(RollIssued(result))    │
  └──────────────────────────────────────┘
        │
        │  (между RollIssued и RollApplied —
        │   мастер может вмешаться через
        │   apply_master_intent(reroll/set_roll))
        ▼
  ┌──────────────────────────────────────┐
  │ возвращаемый результат, который      │
  │ правило применяет (attack vs AC,     │
  │ save vs DC, ...)                     │
  │   bus.publish(RollApplied(result))   │
  └──────────────────────────────────────┘
```

Без мастера эти два события следуют сразу одно за другим; всё работает
прозрачно. С мастером — он может вклиниться, и тогда правило получит
изменённый `EngineRollResult` (с тем же `roll_id`, но другим `total`).

### 7.5 Реализации DiceRoller

- **`ComputerDiceRoller`** — использует `RNG`. По умолчанию.
- **`LiveDiceRoller`** — спрашивает значение у игрока через
  `UserInterface.request_dice_input(ctx)` (пост-MVP, для настольных
  партий).

### 7.6 DiceStatisticsService

`DiceStatisticsService` (модуль `application/engine/dice_stats.py`)
слушает `RollIssued`-события и считает:

- среднее по текущей сессии (только d20, только `raw[0]`);
- среднее за всё время по сейву;
- мини-гистограмму по граням 1..20;
- счётчики nat-20 и nat-1.

UI показывает «удачу» (`current_session_avg − 10.5`) рядом с листом
персонажа.

---

## 8. Hot-seat — заложенные инварианты

Сейчас игрок один. Hot-seat — следующий этап. Чтобы не переделывать
ядро:

- В `GameState` партия — список `Character`, каждый со своим
  `controller_id` (сейчас всегда один и тот же).
- `TurnIntentProvider` запросов привязан к `controller_id`. Сейчас
  один провайдер на всех PC; в hot-seat — UI знает, что между ходами
  передаётся управление, и физически блокирует ввод до подтверждения
  передачи (см. `UI.md`).
- Доступ к листу другого PC — read-only в любой момент (UI-вопрос, не
  движка).

---

## 9. Что меняется в коде по сравнению с исходным планом

| Было | Стало |
|---|---|
| Россыпь `CombatService`, `ExplorationService`, `GameSession` | Один `GameEngine` с режимами. Сервисы — фасадные функции внутри. |
| Гексы | **Квадраты**, Chebyshev-дистанция, 8 соседей, несколько существ на клетке. |
| `MonsterAI` обращается к гекс-сетке | `MonsterAI` обращается к квадратной сетке (LoS, дистанция). |
| `GameMaster` как порт сейчас | Сейчас **нет порта**; есть `apply_master_intent` для тестов и под будущий UI. |
| Скрытый RNG | RNG → `DiceRoller` → правила. Статистика бросков. |
| Лог в RAM, сейв = снапшот | Лог пишется в сейв целиком (история партии не теряется). |

Эти правки уже отражены в `ARCHITECTURE.md` (`application/engine/` блок,
дерево каталогов §2, ADR-0002 в §11).

---

## 10. Что отложено

- Большие существа (Large/Huge/Gargantuan) на нескольких клетках.
- Полёт в 3D — на MVP только флаг «летает», без z.
- Туман войны от каждого PC — единый общий вид партии.
- Группы инициативы — каждый бросает индивидуально.
- LiveDiceRoller — режим ввода настоящих кубиков.
- LiveGameMaster — отдельный UI мастера.
