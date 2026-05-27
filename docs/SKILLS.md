# Навыки и проверки характеристик (этап V)

Навыки и проверки характеристик по PHB-2024. Фундамент для исследования мира
(этап X) и боевых состязаний (V2). Зеркалит модель спасбросков (T1, см.
`saving_throw.py`).

## Модель

- **Навык — это данные.** `domain/values/skill.py`: `Skill` (StrEnum, 18 навыков)
  + `SKILL_ABILITY: dict[Skill, Ability]` — какой характеристикой управляется
  навык. Новый навык/хоумрул = член enum + строка в маппинге; switch по навыкам
  в коде нет — потребители спрашивают маппинг.
- **Владение и Экспертиза — поля существа.** `Creature.skill_proficiencies:
  frozenset[Skill]` (бросок +`proficiency_bonus`), `Creature.skill_expertise:
  frozenset[Skill]` (ещё +`proficiency_bonus`, ×2 итого; Плут/Бард). Экспертиза
  считается только поверх владения. По умолчанию пусто — обычные монстры не
  меняются (backward-compat).

## Бонус проверки

`application/engine/ability_check.py`:

| Функция | Что считает |
|---------|-------------|
| `ability_check_bonus(actor, ability)` | голая проверка характеристики = только модификатор |
| `skill_bonus(actor, skill)` | mod характеристики навыка (+prof если владеет) (+prof если Экспертиза) |

## Бросок проверки

`roll_ability_check_raw(actor, *, skill=None, ability=None, dc, dice_roller,
modifier_applier, condition_service=None)` → `bool`: `d20 + бонус + adjustments`
≥ `dc`. Ровно одно из `skill`/`ability`. `roll_ability_check(..., ctx)` —
обёртка для боевого `TurnContext`.

Помехи и преимущество приходят данными состояний через
`ConditionService.collect_modifiers(actor, ABILITY_CHECK)` (T3): Отравлённый
(Poisoned) и Напуганный (Frightened) дают помеху на проверки. advantage+disadvantage
сводятся к обычному броску в едином месте (`RollContext`/`DiceRoller`), здесь не
дублируется.

## Пассивные значения

`passive_score(actor, skill, *, modifier_applier=None, condition_service=None)` =
`10 + бонус навыка` (+ numeric-модификаторы, **±5** за преимущество/помеху —
PHB-2024 стр. 11). Без броска. **Пассивная Внимательность** =
`passive_score(actor, Skill.PERCEPTION)` — порог обнаружения для скрытности.

## Источник владений (данные)

Владение навыками задаётся данными, не кодом:

- `data/content/classes.yaml` — `skill_proficiencies` у класса (профильные навыки
  для демо/дефолта). Парсится в `ClassProgression.skill_proficiencies`.
- `MonsterTemplate.skill_proficiencies` / `skill_expertise` (`tuple[str, ...]`) —
  владения конкретного шаблона.
- `builder.build_creature` объединяет навыки класса И шаблона в
  `Creature.skill_proficiencies`. `LevelUpService` добавляет навыки класса
  (объединением, не затирая выбранные).

Полноценный выбор «N навыков из списка класса» — в создании персонажа (этап W).

## V2 — боевые проверки (планируется)

Состязания (`opposed_check`), состояния Grappled/Hidden, действия Shove/Grapple/
Hide. См. план `docs/superpowers/plans/2026-05-27-v-skills-and-checks.md`.
