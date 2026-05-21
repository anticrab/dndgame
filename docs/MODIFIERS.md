# MODIFIERS — расширяемая система правил-модификаторов

В D&D 5e любое правило, влияющее на бросок, КД, спасбросок,
характеристику, состояние, скорость, восприятие или поведение — это
**модификатор**. Их множество источников: оружие, доспех, заклинания,
особенности класса/расы, состояния, расходники, чит-вмешательство
мастера, специальные условия сценария.

Чтобы добавление нового правила («заклинание Bless даёт +1d4 к спасброскам
союзников», «Талисман Стойкости — +1 к КД на 1 час, 1 раз в день»,
«герой боится воды — помеха на спасброски в воде») было **данными**, а
не правкой кода, нужна единая модель модификаторов. Документ описывает
её.

Источник истины по правилам — Книга Игрока 2024, §«Тесты к20» (стр. 10–13)
и §«Урон и лечение» (стр. 26).

---

## 1. Категории модификаторов

| Категория | Что делает | Пример |
|---|---|---|
| **Numeric bonus / penalty** | прибавляет/вычитает N к броску, КД, спасброску, навыку, скорости, инициативе, HP, damage | +2 к атаке от магического меча; –1 к КД от помехи доспеха без владения |
| **Dice bonus** | добавляет дополнительные кости (например, 1d4) | +1d4 к спасброскам от заклинания Bless |
| **Advantage / Disadvantage** | один бросок с преимуществом/помехой | помеха на дальнобойную атаку в рукопашной |
| **Resistance / Vulnerability / Immunity** | ÷2, ×2, обнуление урона указанного типа | сопротивление огню от Шкуры Дракона |
| **Condition** | накладывает доменное `Condition` | Отравлен, Парализован, Невидимый |
| **Ability score override** | устанавливает значение характеристики | Пояс Силы Облачного великана: STR = 27 |
| **Replacement** | заменяет базовую формулу другой | Защита без доспехов монаха: КД = 10 + DEX + WIS |
| **Trigger override** | разрешает или блокирует действие | «не может произносить заклинания», «не может перемещаться» |

Модификатор может объединять несколько категорий
(Bless = `+1d4` к атакам **и** к спасброскам, на 1 минуту,
требует концентрации). Поэтому модификатор — это **запись с эффектом**,
а не enum.

---

## 2. Доменная модель

### 2.1 `Modifier` value-object

В коде живёт в `domain/values/modifier.py`. Иммутабельный.

```python
@dataclass(frozen=True, slots=True)
class Modifier:
    # КТО создал
    source_id: ModifierSourceId   # "item:talisman-of-fortitude", "spell:bless", "condition:poisoned"
    source_kind: Literal[
        "item", "spell", "feature", "condition",
        "background", "master_intervention", "scenario",
    ]

    # ЧТО делает (одна категория — один Modifier; для составных эффектов
    # источник создаёт несколько Modifier-ов разом)
    effect: ModifierEffect        # см. §2.2 — discriminated union

    # ГДЕ применяется
    target: ModifierTarget        # см. §2.3 — discriminated union

    # КОГДА применяется
    condition: ModifierCondition  # см. §2.4 — Specification

    # КАК ДОЛГО
    duration: ModifierDuration    # см. §2.5

    # КАК СТЭКАЕТСЯ
    stacking: StackingPolicy = StackingPolicy.NORMAL  # см. §2.6

    # СЛУЖЕБНОЕ
    priority: int = 0             # порядок применения при тай-брейке
    name_key: str | None = None   # ключ i18n, для отображения в UI
    notes_key: str | None = None
```

`Modifier` — **полностью сериализуем** (pydantic-эквивалент в DTO).
Сохраняется в `GameState.modifiers: list[Modifier]`.

### 2.2 `ModifierEffect` — discriminated union

```python
ModifierEffect = Annotated[
    NumericBonusEffect
    | DiceBonusEffect
    | AdvantageEffect
    | DamageMultiplierEffect      # resistance/vulnerability/immunity
    | ConditionEffect
    | AbilityOverrideEffect
    | ReplacementEffect
    | TriggerOverrideEffect,
    Field(discriminator="kind"),
]
```

Каждый эффект — отдельная pydantic-модель с `kind: Literal["..."]`.
Новый тип эффекта = новая модель + новая ветка union + регистрация в
`ModifierApplier`. Это растущий, но управляемый список — не «свободные
dict-ы».

### 2.3 `ModifierTarget` — что модификатор затрагивает

```python
ModifierTarget = Annotated[
    AttackRollTarget(weapon_kind=..., damage_type=...)
    | DamageRollTarget(weapon_kind=..., damage_type=...)
    | SavingThrowTarget(ability=..., source_kind=...)
    | AbilityCheckTarget(ability=..., skill=...)
    | InitiativeTarget()
    | ArmorClassTarget()
    | SpeedTarget(movement_kind=...)
    | HitPointsTarget(when="max"|"current"|"temp")
    | DamageTypeTarget(damage_type=...)
    | ActionAvailabilityTarget(action_id=...),
    Field(discriminator="kind"),
]
```

Цель — **семантическая**, не «всё подряд». Поэтому правила могут
эффективно «достать модификаторы, влияющие на этот тип броска»
(например, `collect(target=AttackRollTarget(weapon_kind="melee"))`).

### 2.4 `ModifierCondition` — когда применяется

Использует паттерн **Specification**. Логическая комбинация фактов о
ситуации.

```python
class ModifierCondition(Protocol):
    def applies(self, ctx: ApplyContext) -> bool: ...

# Готовые предикаты:
AlwaysApplies()
TargetIsCreatureKind("undead")
AttackerIsWielding("longsword")
AttackerHasFlag("hero.fears_water")
LocationHasTag("underwater")
TargetIsMarkedBy(creature_id=...)
TargetWithinRange(feet=30)
HasCondition("rage")
And(a, b, ...)
Or(a, b, ...)
Not(x)
```

`ApplyContext` — DTO с актуальной ситуацией (атакующий, цель, локация,
оружие, тип урона, флаги). Predicate возвращает bool — модификатор
применяется или нет.

Большинство модификаторов идут с `AlwaysApplies()` — это базовый случай.
Сложные правила («только против гуманоидов», «только когда атакующий
вооружён двуручным оружием») — комбинируют предикаты.

### 2.5 `ModifierDuration` — как долго живёт

```python
ModifierDuration = Annotated[
    Permanent()                          # пока существо живёт
    | UntilEndOfTurn(creature_id)
    | UntilEndOfNextTurn(creature_id)
    | UntilEndOfRound()
    | UntilEndOfEncounter()
    | UntilEndOfDay()                    # до следующего long rest
    | UntilNextShortRest()
    | UntilNextLongRest()
    | UntilSaveSucceeds(save_dc, ability)
    | UntilDamageTaken()
    | RoundsRemaining(n)
    | UntilTrigger(trigger_id),          # сценарий явно выключит
    Field(discriminator="kind"),
]
```

Движок на `OnRoundEnd`, `OnTurnEnd`, `OnDamageTaken`, и т.д. событиях
вызывает `tick_modifiers(state, event)` — она снимает истёкшие.

### 2.6 `StackingPolicy` — как ведут себя одинаковые

Книга 5e: «бонусы одного типа не стэкаются» (бонусы заклинаний vs бонусы
от предметов и т.д.). Реализуем:

```python
class StackingPolicy(StrEnum):
    NORMAL = "normal"          # стэкается с разнотипными, но не с
                               # модификаторами того же source_id
    REPLACE = "replace"        # перезаписывает все того же типа
                               # (Барбарианский гнев vs Дикий гнев)
    STACK_ALL = "stack_all"    # стэкается со всем (например, +1d4 от Bless
                               # + +1 от магического меча — оба применяются)
    BEST_ONLY = "best_only"    # из всех своих type берёт наибольший
                               # (например, два разных бонуса к КД от
                               # «магии» — берём один)
```

Резолвер модификаторов (`ModifierApplier`) при сборе:
1. Собрать все модификаторы с этим `ModifierTarget` и подходящим
   `ModifierCondition`.
2. Сгруппировать по правилу политики.
3. Применить в порядке `priority`, потом по `source_id` (для
   детерминизма).

---

## 3. Жизненный цикл

```
       ┌────────────────────────────────────────────────┐
       │   Источник создаёт Modifier-ы                  │
       │   (предмет надет, заклинание сотворено, мастер │
       │   ввёл «хитрый бонус», состояние наложено)    │
       └─────────────────────┬──────────────────────────┘
                             │
                             ▼
       ┌────────────────────────────────────────────────┐
       │   Modifier-ы кладутся в GameState.modifiers    │
       │   (или в Creature.modifiers — см. §4)          │
       └─────────────────────┬──────────────────────────┘
                             │
                             ▼
       ┌────────────────────────────────────────────────┐
       │   Правило (attack_roll, save, ...) собирает    │
       │   применимые модификаторы через ModifierApplier│
       └─────────────────────┬──────────────────────────┘
                             │
                             ▼
       ┌────────────────────────────────────────────────┐
       │   Модификаторы применяются к броску            │
       │   (+N, advantage, дополнительные кости, ...)   │
       └─────────────────────┬──────────────────────────┘
                             │
                             ▼
       ┌────────────────────────────────────────────────┐
       │   События движка                               │
       │   tick_modifiers(...) снимает истёкшие         │
       └────────────────────────────────────────────────┘
```

---

## 4. Где живут активные модификаторы

Решено: **на уровне `GameState`**, а не на отдельных `Creature`. Причина —
многие модификаторы зависят от ситуации (PC1 даёт «бонус доблести»
PC2 на её следующий бросок), и хранение в одном месте упрощает аудит
и replay.

```python
class GameState(BaseModel):
    ...
    modifiers: list[Modifier] = []
```

`Creature.modifiers_view(target_creature_id)` — удобный геттер, который
фильтрует `GameState.modifiers` по `ModifierTarget` и
`ModifierCondition`.

Будущая оптимизация: индекс «creature_id → list[modifier_index]» для
ускорения. На MVP — линейный обход (модификаторов всегда < 100).

---

## 5. Конфигурация: добавление новых правил данными

### 5.1 Через содержимое предмета / заклинания / особенности

YAML контента описывает, какие модификаторы создаёт источник:

```yaml
# content/core/items/magic/talisman-of-fortitude.yaml
id: talisman-of-fortitude
name:
  en: "Talisman of Fortitude"
  ru: "Талисман Стойкости"
slot: neck
rarity: uncommon
charges_per_day: 1
on_activate:
  modifiers:
    - effect: { kind: numeric_bonus, value: +1 }
      target: { kind: armor_class }
      condition: { kind: always }
      duration: { kind: rounds_remaining, n: 600 }   # 1 час = 600 раундов
      stacking: best_only
      name_key: "item.talisman.ac_bonus"
    - effect: { kind: numeric_bonus, value: +2 }
      target: { kind: saving_throw, ability: CON }
      condition: { kind: always }
      duration: { kind: rounds_remaining, n: 600 }
      stacking: best_only
      name_key: "item.talisman.save_bonus"
```

При активации предмета `Item.activate(...)` создаёт по этому шаблону
два `Modifier`-объекта и кладёт их в `GameState.modifiers`. Через 600
раундов они снимаются.

### 5.2 Через черту / особенность класса

```yaml
# content/core/features/champion-improved-critical.yaml
id: feature.champion.improved-critical
name:
  en: "Improved Critical"
  ru: "Улучшенный крит"
class: fighter
subclass: champion
level: 3
permanent_modifiers:
  - effect: { kind: trigger_override, trigger: crit_threshold, value: 19 }
    target: { kind: attack_roll }
    condition: { kind: actor_has_feature, feature: feature.champion.improved-critical }
    duration: { kind: permanent }
    stacking: replace
    name_key: "feature.champion.improved-critical.label"
```

### 5.3 Через мастер-вмешательство (сюжетный модификатор)

Мастер через `MasterIntent: apply_modifier` создаёт ad-hoc модификатор
с причиной:

```yaml
# Условный YAML, который мастер «формирует» в чит-консоли:
effect: { kind: advantage }
target: { kind: ability_check, ability: WIS, skill: persuasion }
condition: { kind: target_has_flag, flag: "village.is_hometown" }
duration: { kind: until_end_of_encounter }
stacking: stack_all
name_key: "master.hometown_advantage"
source_kind: master_intervention
notes_key: "master.hometown_advantage.reason"  # «герой родом из этой деревни»
```

### 5.4 Через сценарий (триггер локации)

```yaml
# content/scenarios/hollow-oak-mine/locations/underground-lake.yaml
events:
  - on: enter
    if: { kind: actor_has_flag, flag: "hero.fears_water" }
    then:
      apply_modifier:
        effect: { kind: disadvantage }
        target: { kind: saving_throw, ability: WIS }
        condition: { kind: location_tag, tag: underwater }
        duration: { kind: until_leave_location }
        stacking: stack_all
        name_key: "scenario.hollow_oak.hero_fears_water"
        source_kind: scenario
```

---

## 6. Алгоритм применения

`ModifierApplier` живёт в `application/engine/modifier_applier.py`.

```python
class ModifierApplier:
    def collect(self, target: ModifierTarget, ctx: ApplyContext) -> list[Modifier]:
        """Все модификаторы, чьи target и condition подходят под ctx."""

    def to_roll_adjustments(self, modifiers: list[Modifier]) -> RollAdjustments:
        """Свести список модификаторов в финальные параметры броска:
           - сумма numeric bonus с учётом StackingPolicy
           - список dice bonus (NkM)
           - флаги advantage/disadvantage (с правилом «не складываются»)
           - replacements (override формулы)
        """

    def to_damage_adjustments(self, modifiers: list[Modifier], dmg_type: DamageType) -> DamageAdjustments:
        """Аналог для урона: множители resistance/vulnerability/immunity."""
```

Правила домена (`domain/rules/attack.py`, `save.py`, `damage.py`)
получают `ModifierApplier` как параметр (`DiceRoller` под капотом
тоже его использует для бросков с подсчётом бонусов).

### 6.1 Применение в attack_roll

```python
def attack_roll(
    attacker: Creature, target: Creature, weapon: Weapon,
    *, roller: DiceRoller, applier: ModifierApplier, ctx: ApplyContext,
) -> AttackOutcome:
    # 1. Собрать модификаторы атаки
    attack_mods = applier.collect(
        AttackRollTarget(weapon_kind=weapon.kind), ctx,
    )
    adj = applier.to_roll_adjustments(attack_mods)

    # 2. Свести в один бросок
    roll_ctx = RollContext(
        purpose="attack",
        actor_id=attacker.id, target_id=target.id,
        advantage=adj.advantage,
        disadvantage=adj.disadvantage,
        extra_dice=adj.extra_dice,
    )
    result = roller.roll(weapon.attack_expr + f"+{adj.numeric_total}", roll_ctx)
    ...
```

Та же схема — для `save`, `ability_check`, `damage_roll`, `initiative`,
`speed`, `passive_perception`.

---

## 7. Отображение в UI

UI получает список активных модификаторов на `Character` для
отображения на листе персонажа («Активные эффекты», вкладка Stats). UI
показывает:

- иконку (по `source_kind`);
- локализованное имя (`name_key`);
- продолжительность («осталось 4 раунда», «до конца боя», «до конца
  дня»);
- источник («Талисман Стойкости», «Заклинание Bless»).

`MasterIntervention`-модификаторы по умолчанию **скрыты** от игрока
(см. `MASTER.md` §4, `master_transparency`).

---

## 8. Тестируемость

Модификаторы — чистые данные. Каждое правило тестируется через
`ScriptedRNG` + явный список модификаторов:

```python
def test_attack_with_bless_and_magic_sword() -> None:
    state = make_state()
    state.modifiers.extend([
        bless_modifier(target=character_id),
        magic_sword_attack_bonus(),
    ])
    result = attack_roll(
        attacker, goblin, longsword,
        roller=ComputerDiceRoller(rng=ScriptedRNG([15])),
        applier=ModifierApplier(state),
        ctx=make_ctx(),
    )
    assert result.hit_total == 15 + STR_mod + PB + 1  # +1 от меча
    # 1d4 от Bless добавится отдельной dice
    assert any("bless" in m.source_id for m in result.applied_modifiers)
```

---

## 9. Что НЕ моделируется через `Modifier`

Чтобы не превратить всё в кашу:

- **Постоянные базовые характеристики** (STR/DEX/CON/...) — это `AbilityScore`
  на `Character`, не модификатор. Расовый бонус +2 STR от Голиафа применяется
  как `Character.abilities.adjusted(...)` при создании, не во время игры.
- **Хиты текущие** — это поле `Creature.hp`, изменяемое прямыми
  методами (`take_damage`, `heal`). Урон/лечение не модификаторы (они
  изменяют состояние).
- **Действия Encounter** (двигаться, атаковать) — это `Action`/`Reaction`,
  отдельный реестр.
- **Состояния** — `Condition` имеет свою модель в `domain/conditions/`,
  но **накладывание** состояния — это `ConditionEffect` модификатора
  (модификатор-источник, состояние-следствие).

---

## 10. Расширяемость и будущее

- **Новые эффекты** (например, «теневое крадение» — после атаки в темноте
  становится невидим): добавляется новый `ModifierEffect`-класс + ветка
  union + обработчик в `ModifierApplier`. Все YAML, описывающие новый
  эффект, будут валидироваться pydantic-схемой.
- **Сложные триггер-условия** через `Specification` — комбинируются
  и расширяются без правки ядра.
- **Master-вмешательство «по чувству»** (фамильный кинжал, страх воды)
  — частный случай модификатора с `source_kind: master_intervention` и
  своим `notes_key`. Никаких параллельных систем не требуется.
- **Сценарные локационные эффекты** — через `apply_modifier` в YAML
  триггерах.
- **Хоумбрю-предметы** — пользователь кладёт YAML в `content/homebrew/`,
  сидер подхватывает; никакого кода писать не нужно.

---

## 11. Что отложено

- **Концентрация на заклинаниях**: модификатор от Bless требует, чтобы
  заклинатель удерживал концентрацию. Это специальная отметка
  `requires_concentration_from: creature_id` в `Modifier`. Реализация —
  пост-MVP, когда появятся заклинания концентрации.
- **Triggered modifiers** («когда вас атакуют — +2 к КД на эту атаку»):
  пока не нужны для MVP-классов, добавим с появлением заклинания Shield
  (1-уровневое, для Волшебника пост-MVP).
- **Многоэтапные модификаторы** (Frenzied Rage: каждый ход эффект меняется):
  не требуются для MVP.

Все три случая укладываются в текущую модель — нужны только новые типы
эффектов и условий.
