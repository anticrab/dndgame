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

## V2 — боевые проверки (состязания)

`application/engine/skill_actions.py` — действия поверх проверок:

| Действие | Проверка | Эффект при успехе |
|----------|----------|-------------------|
| **Shove** (Толкнуть) | Атлетика актёра vs лучшая из Атлетики/Акробатики цели | Prone |
| **Grapple** (Схватить) | то же состязание | Grappled (скорость 0) |
| **Hide** (Спрятаться) | Скрытность vs пассивная Внимательность врагов | Hidden (преимущество на следующую атаку) |

**Состязание** (`opposed_check_raw`): актёр кидает свою проверку, цель — лучшую
из защитных; побеждает актёр, только если его итог **строго больше** — ничья
остаётся за защищающимся (PHB-2024 стр. 11). Shove/Grapple — в упор (≤5 фт).

**Hide → Hidden**: преимущество на атаку приходит self-модификатором состояния
(`collect_modifiers(ATTACK_ROLL)` — тот же механизм T3), снимается в `attack.py`
после удара. Порог скрытности = макс. пассивная Внимательность врагов рядом.

Интенты `ShoveIntent`/`GrappleIntent`/`HideIntent` → диспатч в `GameRunner.
_do_skill_action`. Новое контест-действие (Disarm, Trip…) = ещё один класс
поверх `opposed_check`, без правки ядра.

### V2-упрощения (осознанные, см. план)

- **Shove** — только Prone (толчок на 5 фт — задел).
- **Grapple** — базовый захват; освобождение (побег повторным состязанием) и
  перетаскивание — задел.
- **Hide/Hidden** — лёгкая версия: преимущество на свою атаку + снятие после
  удара. Полный стелс («не виден» → помеха атакам по тебе, прерывание
  скрытности движением в поле зрения, LoS) — задел.

План этапа: `docs/superpowers/plans/2026-05-27-v-skills-and-checks.md`.
