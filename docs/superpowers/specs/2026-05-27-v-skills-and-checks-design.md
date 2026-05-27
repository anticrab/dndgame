# V — навыки и проверки характеристик: дизайн

> Фундамент для исследования мира (X) и закрытие отложенного: R2-навыки,
> Fast Hands/Second-Story (T4). Принцип: навыки — данные/реестр (не switch);
> domain не зависит от application; гасим техдолг. Зеркалит T1 (спасброски).

## 1. Решения (зафиксированы с пользователем)

- Объём: **фундамент + боевые проверки** (Shove / Grapple / Hide). Декомпозиция:
  **V1 — фундамент** (Skill + проверки + пассивные), **V2 — боевые проверки**
  (состязания + Grappled/Hidden + действия).
- Владение навыками — **данными шаблона/класса** (по аналогии с T1
  saving-throw-proficiencies). Полноценный выбор навыков — в создании
  персонажа (W).
- Режим: inline.

## 2. V1 — фундамент: навыки, проверки, пассивные значения

### 2.1 Domain (`domain/values/skill.py`)

```python
class Skill(StrEnum):
    ACROBATICS = "acrobatics"      # DEX
    ANIMAL_HANDLING = "animal_handling"  # WIS
    ARCANA = "arcana"              # INT
    ATHLETICS = "athletics"        # STR
    DECEPTION = "deception"        # CHA
    HISTORY = "history"            # INT
    INSIGHT = "insight"            # WIS
    INTIMIDATION = "intimidation"  # CHA
    INVESTIGATION = "investigation"  # INT
    MEDICINE = "medicine"          # WIS
    NATURE = "nature"              # INT
    PERCEPTION = "perception"      # WIS
    PERFORMANCE = "performance"    # CHA
    PERSUASION = "persuasion"      # CHA
    RELIGION = "religion"          # INT
    SLEIGHT_OF_HAND = "sleight_of_hand"  # DEX
    STEALTH = "stealth"            # DEX
    SURVIVAL = "survival"          # WIS

SKILL_ABILITY: dict[Skill, Ability] = { ... }  # навык → характеристика (данные)
```

Новый навык = член enum + строка в `SKILL_ABILITY`. `ConditionId`-стиль не
нужен — это закрытый список PHB.

### 2.2 Domain (`Creature`)

По аналогии с `saving_throw_proficiencies`:
```python
skill_proficiencies: frozenset[Skill] = frozenset()
skill_expertise: frozenset[Skill] = frozenset()   # ×2 prof (Плут/Бард)
```

### 2.3 Application (`engine/ability_check.py`, зеркало `saving_throw.py`)

- `skill_bonus(actor, skill)` = `abilities.modifier(SKILL_ABILITY[skill])`
  `+ prof` (если в `skill_proficiencies`) `+ prof ещё раз` (если в
  `skill_expertise`).
- `ability_check_bonus(actor, ability)` = голый модификатор характеристики
  (для проверок без навыка, напр. сырая Сила).
- `roll_ability_check_raw(actor, *, ability, skill=None, dc, dice_roller,
  modifier_applier, condition_service=None, tags=("ability_check",))` → bool:
  `d20 + bonus + adjustments ≥ dc`. `bonus` = skill_bonus (если skill задан)
  иначе ability_check_bonus. `adjustments` — из `modifier_applier.collect(
  ABILITY_CHECK)` + `condition_service.collect_modifiers(ABILITY_CHECK)`
  (Poisoned/Frightened уже дают помеху — T3); advantage/disadvantage агрегируются.
- `roll_ability_check(actor, ..., ctx)` → делегирует в raw (как у спасбросков).
- `passive_score(actor, skill)` = `10 + skill_bonus(actor, skill)` плюс
  модификаторы (numeric из ABILITY_CHECK) и **±5** за advantage/disadvantage
  (PHB-2024 стр. 11). Пассивная Внимательность = `passive_score(actor,
  PERCEPTION)`.

> Возвращаем `bool` (успех/провал vs DC) как у спасбросков; «степень успеха»
> и сырое значение — задел (для X-челленджей можно вернуть результат-структуру
> позже; пока bool достаточно).

### 2.4 Источник владений (данные)

- `MonsterTemplate`: `skill_proficiencies: tuple[str, ...] = ()`,
  `skill_expertise: tuple[str, ...] = ()`; `builder` кладёт во `frozenset[Skill]`.
- `ClassProgression`: опц. `skill_proficiencies` (базовые навыки класса) —
  парсинг в `YamlClassRepository`; `LevelUpService`/builder проставляет. Полный
  выбор «N навыков из списка класса» — в W (создание персонажа).
- Демо-PC (воин/плут/маг) получают пару профильных навыков для наглядности.

### 2.5 Тесты V1

- `skill_bonus` (владение → +prof; экспертиза → +2×prof; без владения → только
  mod). `passive_score` (10 + бонус; ±5 при adv/disadv). `roll_ability_check`
  (DC успех/провал; Poisoned → помеха через collect_modifiers). Контент-тест:
  у класса/шаблона парсятся навыки. Все навыки имеют запись в `SKILL_ABILITY`
  (полнота enum).

## 3. V2 — боевые проверки (состязания)

### 3.1 Состязание (opposed check) — helper

`engine/ability_check.py`: `opposed_check(actor, actor_skill, target,
target_skills, *, ctx) -> bool` — актёр кидает свою проверку, цель кидает
лучшую из своих; True, если actor ≥ target (ничья — победа защищающегося,
PHB-2024). Переиспользует `roll_ability_check_raw` для обеих сторон.

### 3.2 Новое состояние Grappled

`domain/conditions/builtin.py`: `GrappledCondition` (PHB-2024 стр. 368) —
скорость 0; не даёт cross-creature преимуществ сам по себе. Поля T3 — дефолтные
(нет). Зарегистрировать в `register_default_conditions`. (Speed=0 → MoveAction
уже не сможет двигаться при скорости 0? — проверить; иначе добавить guard.)

### 3.3 Действия (Action + Intent, в реестр через GameRunner)

- **ShoveAction** (часть Атаки/действие): Athletics актёра vs лучшее из
  Athletics/Acrobatics цели → при успехе **Prone** (есть) ИЛИ толчок на 5 фт
  (выбор — пока Prone как дефолт; толчок — задел). Цель в пределах 5 фт.
- **GrappleAction**: Athletics vs Athletics/Acrobatics → **Grappled** на цель.
  Освобождение (побег) — повторное состязание; для V2 — базовый захват +
  снятие действием (escape) опционально/задел.
- **HideAction** (Stealth): проверка Скрытности vs пассивная Внимательность
  ближайших врагов → ставит лёгкое состояние **Hidden** (флаг): преимущество на
  следующую атаку и помеха атакам по тебе, спадает при атаке/обнаружении.
  Полная механика «невидим/не виден» — упрощение (помечаем); переиспользует
  cross-creature-поля состояния (как Invisible-задел).

> V2-упрощения (осознанные, в доку): Shove = только Prone (толчок-на-5-фт —
> задел); Grapple-escape — базовый; Hide/Hidden — лёгкая версия (без полного
> LoS/«не виден»). Fast Hands (T4, Плут-Вор) теперь выразим: бонусное действие
> = Sleight of Hand-проверка/использование предмета — подключим в W/T-добивке.

### 3.4 Тесты V2

- `opposed_check` (актёр выигрывает/проигрывает/ничья). Shove → цель Prone
  (по успеху), промах → без эффекта. Grapple → Grappled (speed 0 → не двигается).
  Hide → Hidden-флаг → атака с преимуществом (через cross-creature). e2e-смок:
  плут прячется → бьёт с преимуществом.

## 4. Расширяемость

- Навык/проверка — данные (`Skill` + `SKILL_ABILITY`); сервис агностичен.
- Состязания — общий helper; новые «контест»-действия (Disarm, Trip…) = новый
  Action поверх `opposed_check`, без правок ядра.
- Состояния (Grappled/Hidden) — через существующий `ConditionService` (T3-поля).

## 5. Инварианты

1. domain не импортирует application; `Skill`/`SKILL_ABILITY` — данные в domain.
2. Бонус навыка: mod (+prof если владеет) (+prof если экспертиза) — экспертиза
   только поверх владения.
3. adv+disadv=обычный — единое место (RollContext/DiceRoller), не дублируем.
4. Backward-compat: новые поля Creature/Template — дефолты пустые; существующие
   существа не меняются.
5. Пассивное значение: 10 + бонус ±5 (adv/disadv), без броска.

## 6. Декомпозиция (план)

- **V1-1** `Skill` + `SKILL_ABILITY` (domain) + тест полноты.
- **V1-2** `Creature.skill_proficiencies/expertise` + `skill_bonus`/
  `ability_check_bonus`.
- **V1-3** `roll_ability_check[_raw]` + `roll_ability_check(ctx)` + тесты
  (включая помеху от состояний).
- **V1-4** `passive_score` + пассивная Внимательность.
- **V1-5** источник владений: Template + ClassProgression парсинг + builder +
  демо-контент.
- **V1-6** доки (SKILLS.md, ABILITIES/PROGRESSION ссылки, ROADMAP).
- **V2-1** `opposed_check` + тесты.
- **V2-2** `GrappledCondition` (+ speed-0 guard в Move).
- **V2-3** Shove/Grapple Action+Intent + GameRunner + тесты.
- **V2-4** Hide → Hidden (лёгкая) + cross-creature advantage + e2e-смок.
- **V2-5** доки + аудит-смок.

## 7. Отложено (W/X/далее)

- Выбор «N навыков из списка класса» при создании (W).
- Tool proficiencies; «степень успеха»/возврат сырого результата проверки.
- Полный стелс (LoS «не виден», прерывание скрытности движением в поле зрения).
- Shove-толчок на 5 фт (сейчас Prone); полный Grapple-escape/перетаскивание.
