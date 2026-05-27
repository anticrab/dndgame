# Состояния (Conditions) и их боевые эффекты

Состояния — это плагины (`domain/conditions/`): класс, реализующий протокол
`Condition`, зарегистрированный в `ConditionRegistry`. На существе они хранятся
как множество `Creature.conditions: set[ConditionId]` (без длительности — это
факт «есть/нет», PHB-2024 стр. 27 «без накопления»). Длительность контроль-
эффектов держит `OngoingEffectTracker` (см. `docs/SPELLS.md`, этап T2).

## Контракт `Condition` (`domain/conditions/base.py`)

| Поле/метод | Назначение |
|------------|------------|
| `id` | стабильный `ConditionId` (`"poisoned"`, `"prone"`, …) |
| `implies` | какие состояния активируются каскадом (Unconscious → Incapacitated + Prone) |
| `provides_modifiers(owner_id)` | self-модификаторы носителя на его броски |
| `grants_advantage_to_attackers` | T3: атаки по носителю — с преимуществом |
| `melee_advantage_ranged_disadvantage` | T3: Prone — adv в упор ≤5 фт, иначе disadv |
| `auto_fail_saves` | T3: спасброски этих характеристик авто-проваливаются |

## Применение в бою — `ConditionService` (этап T3)

`ConditionService` — мост между декларативными данными состояний и бросками
(чистые чтения на момент броска; никакого учёта при apply/remove):

- **`collect_modifiers(creature, target_kind)`** — собирает `provides_modifiers`
  активных состояний носителя. `attack.py` подмешивает их в сбор `ATTACK_ROLL`,
  `saving_throw` — в `SAVING_THROW`. **Фикс T3:** до этого `provides_modifiers`
  нигде не вызывались — помехи Poisoned/Frightened/Prone не работали.
- **`incoming_attack_adjustment(target, *, distance_ft, attack_kind)` → (adv, disadv)** —
  cross-creature: преимущество/помеха атакующему от состояний цели. `attack.py`
  подмешивает в бросок атаки.
- **`auto_fails_save(creature, ability)` → bool** — авто-провал спасброска
  (приоритетнее любых преимуществ — `roll_saving_throw` сразу возвращает False).

## Боевые данные базовых состояний

| Состояние | self-помеха | атакам по нему | авто-провал спасбр. | прочее |
|-----------|-------------|----------------|---------------------|--------|
| Poisoned | атака, проверки | — | — | |
| Frightened | атака, проверки | — | — | не сближается с источником |
| Prone | свои атаки | adv в упор / disadv в дали | — | движение ×2 |
| Incapacitated | — | — | — | нет действий/реакций; пропуск хода |
| Stunned | — | advantage | STR, DEX | implies Incapacitated |
| Paralyzed | — | advantage | STR, DEX | авто-крит в упор; implies Incapacitated |
| Unconscious | — | advantage | STR, DEX | авто-крит в упор; implies Incapacitated + Prone |
| Invisible | — | — | — | задел (cross-creature не реализован) |

## Прочие боевые правила T3

- **Авто-крит в упор** (`attack.py`): попадание melee ≤5 фт по беспомощной цели
  (0 HP **или** Paralyzed/Unconscious) — критическое (PHB-2024 стр. 27, 367).
- **Dodge** (`saving_throw.py`): атаки по dodger'у — с помехой (уже было);
  dodger получает **преимущество на спасброски Ловкости** (PHB-2024 стр. 22),
  если дееспособен (авто-провал DEX под Paralyzed/Unconscious приоритетнее).
- **Инкапаситированный актёр** не совершает действий — guard в `GameRunner`/
  `SimpleMonsterAI`; ход сразу завершается (но `TurnEnded` публикуется, поэтому
  повторный спасбросок Hold Person в конце такого хода отыгрывается).

## Расширяемость

Новое состояние с боевым эффектом = его dataclass с нужными значениями полей
(данные, не switch). `attack.py`/`saving_throw` агностичны к конкретным
состояниям — спрашивают `ConditionService`.

## Отложено (T4/далее)

Petrified/Blinded/Restrained-контент (данные можно объявить как у прочих);
cover/невидимость как источники adv/disadv; reach-оружие и «в упор» для
авто-крита (сейчас «в упор» = distance ≤5); стэкинг одного состояния от двух
источников (снятие одним эффектом убирает общее).
