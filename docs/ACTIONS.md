# Система действий (Actions)

Документ описывает контракты подсистемы «Действия» — что такое
``Action``, как устроена экономика действий, как действие проходит
путь от запроса игрока/AI до публикации событий и мутации поля боя.

Связанные документы:

* ``docs/ENGINE.md`` §4 — общая идея Command-объектов.
* ``docs/MODIFIERS.md`` — как действия модифицируют броски.
* ``docs/VISIBILITY.md`` — что доступно атакующему через LoS/cover.
* ``docs/TARGETING.md`` — выбор целей.
* «Книга Игрока 2024» стр. 21–27 (раунд, ход, экономика, движение,
  атака, укрытие).

---

## 1. Экономика действий (PHB-2024 стр. 21)

В каждый свой **ход** существо может выполнить **по одному** из:

* **Action** (основное действие): Attack, Cast a Spell, Dash, Disengage,
  Dodge, Help, Hide, Influence, Magic, Ready, Search, Study, Utilize +
  специальные классовые/особые действия.
* **Bonus Action**: только если фича/заклинание/оружие явно её даёт.
* **Reaction**: одна в раунд, **между** ходами (по триггеру). Самые
  частые — Opportunity Attack и активация Ready.

Плюс:

* **Movement**: бюджет в футах = ``speed`` существа; можно разбивать
  движение между атаками и другими актами.
* **Object interaction**: одна свободная (открыть дверь, поднять
  предмет, переключить рычаг) в ход; вторая стоит Action.
* **Свободные действия речи** — без бюджета (PHB-2024 стр. 22).

В нашем движке это **`ActionEconomyCost` enum**:

| Значение | Смысл | Бюджет на ход |
|---|---|---|
| `ACTION` | основное действие | 1 |
| `BONUS_ACTION` | бонусное действие | 1 |
| `REACTION` | реакция | 1 (на раунд, не на ход) |
| `MOVEMENT` | стоит футов из движения | переменный |
| `FREE` | свободное (object interaction, речь) | 1 для object interaction, ∞ для речи |

Конкретное действие выбирает один из этих cost'ов; смешанные
(«Action + Bonus Action одновременно») — невозможны в книге.

---

## 2. Action Protocol

```python
class Action(Protocol):
    id: ActionId                  # 'attack', 'dash', 'dodge', ...
    name_key: str                 # ключ локализации, см. I18N.md
    economy_cost: ActionEconomyCost

    def can_perform(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability: ...

    def execute(
        self, actor: Creature, params: ActionParams, ctx: TurnContext
    ) -> ActionOutcome: ...
```

**`can_perform`** — pure-функция (без побочных эффектов). Возвращает
**типизированный результат**:

* `Allowed()` — действие можно выполнить;
* `Forbidden(reason)` — нельзя, с конкретной причиной (paralyzed,
  no_economy_left, out_of_targets, ...). UI показывает локализованное
  объяснение.

**`execute`** — выполняет действие. **Не валидирует повторно** то, что
проверил `can_perform`: вызывающий обязан вызвать `can_perform` до
`execute` (договорённость, проверяется юнит-тестом-симулятором).
Возвращает `ActionOutcome` с:

* списком событий (`EngineEvent`), уже опубликованных в шину;
* состоянием экономики, обновлённым после действия;
* флагом `consumed_action_economy: ActionEconomyCost` — что именно
  потратилось (для движка хода).

Внутри `execute` действие **само** публикует события через
`ctx.event_bus.publish(...)`. Этот подход даёт прозрачность для
подписчиков (журнал, UI, статистика) без необходимости движку хода
переоткрывать «что произошло».

---

## 3. TurnContext

Контейнер всего, что нужно действию для работы и проверки. **Mutable**
(меняется по ходу выполнения действия — например, `movement_used_ft`
после Move).

```python
@dataclass
class TurnContext:
    actor_id: CreatureId
    battlefield: Battlefield
    dice_roller: DiceRoller
    modifier_applier: ModifierApplier
    condition_service: ConditionService
    event_bus: EventBus
    rng: RNG

    # Экономика хода:
    action_used: bool = False
    bonus_action_used: bool = False
    reaction_used: bool = False      # на раунд (сбрасывается раз в раунд)
    movement_remaining_ft: int       # инициализируется speed * 1.0
    free_object_interaction_used: bool = False

    # Информация о ходе:
    round_number: int                # 1, 2, 3...
    turn_number_in_round: int        # 0..N-1 в порядке инициативы

    # Журнал текущего хода (необязательно, для UI/анализа):
    actions_taken: list[ActionOutcome] = field(default_factory=list)
```

Helper-методы:

* `can_spend(cost: ActionEconomyCost) -> bool` — есть ли бюджет.
* `spend(cost: ActionEconomyCost) -> None` — потратить, иначе
  `ValueError` (контракт: вызывающий уже проверил через `can_spend`).
* `spend_movement(feet: int) -> None` — отдельно для движения.
* `start_new_round() -> None` — сброс reaction_used и накопленных
  на ход счётчиков (вызывается из движка между раундами).

**Не**-задача TurnContext — собственно бросать кости, проверять LoS,
применять модификаторы. Эти задачи делегируются полям-зависимостям
(``dice_roller``, ``modifier_applier``, ``battlefield``).

---

## 4. Контракт `ActionAvailability`

Discriminated union (как ``MasterIntent``):

```python
class Allowed(BaseModel):
    kind: Literal["allowed"]

class Forbidden(BaseModel):
    kind: Literal["forbidden"]
    reason: ForbiddenReason          # enum
    details: str = ""                # опционально, для редких кейсов
```

`ForbiddenReason` — закрытый enum: ``NO_ECONOMY_LEFT``,
``INCAPACITATED``, ``NO_VALID_TARGETS``, ``OUT_OF_RANGE``,
``NO_LINE_OF_SIGHT``, ``TARGET_HAS_TOTAL_COVER``,
``NOT_ENOUGH_MOVEMENT``, ``CONDITION_BLOCKS_ACTION``,
``CUSTOM`` (для контента).

Не используем строки/исключения для отказов — это часть UX (UI
покажет локализованное «не могу: цель за полной защитой»).

---

## 5. ActionOutcome

```python
class ActionOutcome(BaseModel):
    success: bool                    # действие реализовано (не «попало по цели»)
    events_published: tuple[str, ...]  # event_type строки для аудита
    consumed: ActionEconomyCost
    movement_spent_ft: int = 0
    notes: str = ""                  # свободные комментарии для лога
```

Поле ``success`` — это «удалось ли начать выполнение», а не «нанесли
ли урон». Атака с промахом → ``success=True`` (атака произошла, просто
не попала). ``success=False`` зарезервирован для:

* действие прервано вмешательством мастера (`MasterIntent`);
* runtime-условия, которые `can_perform` не успел проверить (редкость).

Конкретные числовые результаты (damage, save DC, итог save'а) — в
**событиях**. ``ActionOutcome`` — это «расписка», что действие
завершилось, а не его содержимое. Подписчики читают события для
содержимого.

---

## 6. Жизненный цикл действия

```
[выбор действия игроком/AI]
        │
        ▼
ctx ← TurnContext(...)
        │
        ▼
action.can_perform(actor, ctx) → Allowed | Forbidden
        │
   ┌────┴────┐
Forbidden    Allowed
   │            │
   ▼            ▼
[UI показывает причину]   action.execute(actor, params, ctx)
                              │
                              ├─► event_bus.publish(events...)
                              ├─► ctx.spend(consumed_cost)
                              ├─► (опционально) ctx.spend_movement(...)
                              ▼
                          ActionOutcome
```

**Никаких** «двойных вычислений»: всё, что прошло `can_perform`,
выполняется в `execute` без повторной проверки. Если изменилось
состояние между этими вызовами — это контрактная ошибка вызывающего.

---

## 7. Что НЕ делает Action

* **Не управляет ходом**. Кто следующий ходит, когда раунд кончается
  — это `Encounter` (этап F).
* **Не решает за UI**. Action ничего не «спрашивает» у игрока. Если
  нужны параметры (цель, выбор оружия) — они уже в `params` от
  composition root (UI/AI собрал).
* **Не пишет журнал партии напрямую**. Журнал подписан на события
  (GameLog в `infrastructure/`).
* **Не сериализует себя**. Это задача сейв-репозитория, который видит
  `id` действия и параметры.

---

## 8. План реализации (этапы E1…E6)

* **E1** — фундамент: DTO, Protocol, TurnContext, без конкретных
  действий. **Этот коммит.**
* **E2** — `AttackAction` (melee + ranged через ActionParams): бросок
  d20 + модификаторы → cover/LoS из Battlefield → DamageRoll → события
  AttackRolled / DamageDealt / AttackResolved.
* **E3** — `MoveAction`: путь по клеткам, difficult_terrain ×2,
  проверка `passable`, провоцированные атаки (через reaction соседей).
* **E4** — `DodgeAction`, `DashAction`, `DisengageAction` (stance-like).
* **E5** — `HelpAction`, `SearchAction` (advantage-grant и
  perception-check).
* **E6** — `OpportunityAttack` (reaction-action, использует логику E2).

Каждый этап — отдельный коммит с тестами + независимый агент-аудит,
как мы делали для Battlefield.
