# Encounter (бой)

Документ описывает контракты подсистемы «Бой» — что такое
``Encounter``, как устроены инициатива и цикл раундов, как
очищаются per-creature состояния между ходами/раундами и как
определяется конец боя.

Связанные документы:

* ``docs/ENGINE.md`` §3 (цикл боя — высокоуровневый);
* ``docs/ACTIONS.md`` (контракт действий, на котором строится ход);
* «Книга Игрока 2024» стр. 21–22 (раунд, ход, инициатива; PHB-2024
  стр. 27 — death saves и «Огромный урон»).

---

## 1. Состав

``Encounter`` — **mutable entity** уровня application. Владеет:

* ``participants: dict[CreatureId, Creature]`` — все участники
  (живые и мёртвые); identity ссылок не теряется при смерти;
* ``factions: dict[CreatureId, Faction]`` — `PARTY` / `MONSTERS` /
  `NEUTRAL`;
* ``battlefield: Battlefield`` — поле боя (мутабельное);
* ``initiative_order: tuple[InitiativeEntry, ...]`` — порядок ходов
  после броска инициативы;
* счётчики: ``round_number`` (1, 2, …), ``current_turn_index``
  (позиция в ``initiative_order``).

Зависимости (внешние сервисы) собраны в
``EncounterDependencies``: ``dice_roller``, ``modifier_applier``,
``condition_service``, ``event_bus``, ``rng``. Группировка нужна
для краткости конструктора; сама `Encounter` обращается к полям
напрямую.

---

## 2. Инициатива

PHB-2024 стр. 22 («Инициатива»):

* каждый бросает **d20 + DEX modifier**;
* applicable модификаторы (Alert feat, Bardic Inspiration и пр.)
  попадают через ``ModifierApplier`` с ``ModifierTargetKind.INITIATIVE``;
* tie-break: сначала выше DEX score; затем — порядок ввода (стабильно).

**Алгоритм** ``Encounter.start()``:

1. Для каждого живого participant бросить через ``DiceRoller`` с
   ``RollPurpose.INITIATIVE`` (бросок проходит «двухфазную»
   модель — `RollIssued` → `RollApplied` через шину).
2. Собрать ``InitiativeEntry(creature_id, total, d20_raw, dex_score)``.
3. Отсортировать по: ``-total, -d20_raw, -dex_score, insertion_order``.
4. Опубликовать ``InitiativeRolled(order)`` с финальным порядком.
5. Установить ``round_number=1``, ``current_turn_index=0``.

Мёртвые participant'ы в initiative не попадают. Если existo упало
в 0 HP **после** броска инициативы, оно остаётся в ordere, но его
ход пропускается (см. §3.3).

---

## 3. Жизненный цикл

```
Encounter.start()
    │
    ▼
 InitiativeRolled
    │
    ▼  ┌───────────────────────────────────────────┐
    │  │ Round n                                     │
    │  ▼                                              │
    │  RoundStarted(n)                                │
    │  │                                              │
    │  for entry in initiative_order:                 │
    │     ▼                                            │
    │     start_turn(actor)                            │
    │       ├─► clear actor.combat_stances             │
    │       ├─► reset ctx fields (action/bonus/move)   │
    │       ├─► (round start? clear actor.reaction)    │
    │       └─► publish TurnStarted(actor)              │
    │     ▼                                            │
    │     (game loop / AI / player executes actions)   │
    │     ▼                                            │
    │     end_turn(actor)                              │
    │       ├─► publish TurnEnded(actor)               │
    │       └─► check is_concluded → EncounterEnded    │
    │     ▼                                            │
    │  RoundEnded(n)                                   │
    │  │                                              │
    │  n += 1, loop                                    │
    └───────────────────────────────────────────┘
```

### 3.1 start_turn(actor)

* Сброс `actor.combat_stances`:
  * `DODGING`, `DISENGAGED` — живут «до начала следующего хода
    владельца» (PHB-2024 стр. 22), точно соответствует сейчас;
  * `DASHING` — маркер потраченного действия, на бюджет уже не влияет.
* Создание свежего `TurnContext` с обнулёнными счётчиками экономики
  и `movement_remaining_ft = actor.speed_ft`.
* Если это **первый ход actor'а в раунде** (`round_started_for_actor`),
  на самом деле — старт нового раунда: сброс `actor.reaction_used`
  тоже происходит на `RoundStarted` (см. §3.5), не на каждом ходу.
* Публикация `TurnStarted(actor_id, round_number)`.

### 3.2 end_turn(actor)

* Публикация `TurnEnded(actor_id, round_number)`.
* Проверка `is_concluded`:
  * если одна сторона полностью downed — публикация `EncounterEnded`,
    цикл прерывается.

### 3.3 Пропуск хода

* Если existo `is_at_zero_hp` или имеет `UNCONSCIOUS` — `start_turn`
  всё равно публикуется (для UI), но `TurnContext` создаётся с
  блокирующими полями (например, `action_used=True`). На MVP —
  публикуем `TurnStarted` и сразу `TurnEnded`, игровой цикл пропускает
  такого actor'а через `is_skipped` флаг (или AI просто не делает
  действий).

### 3.4 Death saves (отложено)

PHB-2024 стр. 27. PC, упавшие в 0 HP, бросают death save на старте
хода. В MVP отлагаем — оба типа participant (PC и monster) при 0 HP
считаются «вне боя» (`is_at_zero_hp`). Полные death saves — после
Character.

### 3.5 RoundStarted

* `round_number` инкрементируется ДО публикации `RoundStarted` (кроме
  первого раунда, который ставится в `start()`).
* Для каждого живого participant — `creature.reaction_used = False`.
* `current_turn_index = 0`.

---

## 4. EncounterDependencies

Группировка зависимостей. Также **передаётся в `TurnContext`** при
создании каждого хода — `TurnContext` ничего не знает про
`Encounter` (зависимость идёт «вниз»: Encounter → TurnContext, не
наоборот).

---

## 5. Faction и условие победы

```python
class Faction(StrEnum):
    PARTY = "party"
    MONSTERS = "monsters"
    NEUTRAL = "neutral"
```

`Encounter.is_concluded`:

* Жива хотя бы одна не-NEUTRAL фракция, у которой есть `is_alive`
  participants. Если живых из `PARTY` нет → MONSTERS победили.
* Если живых из `MONSTERS` нет → PARTY победили.
* Если жива только NEUTRAL — fluke; считаем `EncounterEnded`
  с `winners=None`.

`EncounterEnded` event несёт:

* `winners: Faction | None`
* `round_number`
* `survivors_by_faction: dict[Faction, tuple[CreatureId, ...]]`

---

## 6. Provoked → OpportunityAttack

PHB-2024 стр. 22. Когда `MoveAction` публикует
`OpportunityAttackProvoked`, нужен **handler**, который решит,
выполнять ли реакцию. Это политика — UI спрашивает игрока, AI —
сам атакует, тестовый мок — игнорирует.

`Encounter` принимает аргументом ``reaction_policy: Callable[[OpportunityAttackProvoked, Encounter], None]``.
По умолчанию — `auto_react_policy`, которая вызывает
`OpportunityAttack.execute` через стандартные `AttackParams` (Жёсткая
зависимость от Character/Weapon вытаскивается из `Creature` через
`default_melee_attack` helper — будет в Character этапе).

В MVP можно ограничиться `noop_policy` (просто публикует событие),
а сам auto-react добавится в Character — у monster'а есть
`default_attack_profile`.

---

## 7. Что НЕ делает Encounter

* Не выбирает действия — это UI / AI.
* Не валидирует actions — это сам Action.
* Не моделирует **between**-rounds эффекты длительностью N rounds
  (Bless 1 minute, Hold Person concentration) — это `Modifier`
  с time scope; Encounter только тикает счётчиком раундов и
  публикует RoundStarted/RoundEnded.
* Не сохраняет себя — это `SaveRepository` (snapshot Encounter
  + Battlefield).

---

## 8. План реализации

* **F1** — этот: Encounter с initiative; `InitiativeRolled` event;
  Faction.
* **F2** — lifecycle (`TurnStarted`, `TurnEnded`, `RoundStarted`,
  `RoundEnded`); очистка stances и reactions.
* **F3** — `EncounterEnded` + условие победы.
* **F4** — `reaction_policy` для OpportunityAttackProvoked.

Аудит — после всех четырёх (`docs/audit/13_encounter.md`).
