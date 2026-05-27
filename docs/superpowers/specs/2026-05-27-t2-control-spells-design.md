# T2 — контроль-заклинания волшебника: дизайн

> Этап серии T (волшебник). Предшественник — T1 (ядро класса + `roll_saving_throw`).
> Цель T2 — «интересные» заклинания контроля поля боя: **Sleep** (Усыпление) и
> **Hold Person** (Удержание личности), плюс правка техдолга по уровням
> evocation-заклинаний. Принцип проекта: реестры/хендлеры, не switch; domain не
> зависит от application; событийная связность; техдолг гасим сразу.

## 1. Проблема и мотивация

Заклинания P1/P2 умеют только урон/лечение/бафф. Нет «контроля» — состояний,
которые держатся **во времени** и снимаются по событию. Состояния на `Creature`
сейчас — это голый `set[ConditionId]` без длительности и триггеров снятия.

Контроль-заклинания требуют трёх разных правил снятия:

| Заклинание  | Состояние    | Гейт наложения        | Снятие                                            |
|-------------|--------------|-----------------------|---------------------------------------------------|
| Sleep       | Unconscious  | HP-пул 5d8 (без save) | при получении **любого урона** (пробуждение)      |
| Hold Person | Paralyzed    | спасбросок WIS        | повторный спасбросок WIS в **конце своего хода**; срыв **концентрации** кастера |

Это общий механизм «состояние до момента X», который также лёг в основу T3
(боевые условия). Реализуем его один раз — событийной службой.

## 2. Решения (зафиксированы с пользователем)

- **Инфраструктура эффектов:** отдельная application-служба `OngoingEffectTracker`,
  подписанная на шину (а НЕ точечные хуки в `Encounter`). Расширяемо, готовит
  длительности для T3.
- **Sleep:** каноничный HP-пул 5d8 (2024), усыпляет по возрастанию текущего HP;
  без спасброска; пробуждение от урона.
- **Режим исполнения:** inline.

## 3. Архитектура

### 3.1 Расширение `Spell` (domain/values/spell.py)

Новый тип эффекта и поля (заклинание остаётся данными):

```python
class SpellEffect(StrEnum):
    ...
    CONTROL = "control"   # наложение состояния (± длительность/снятие)

@dataclass(frozen=True, slots=True)
class Spell:
    ...
    condition: ConditionId | None = None        # CONTROL: какое состояние
    hp_pool_dice: str | None = None             # CONTROL: пул хитов (Sleep "5d8")
    condition_ends_on_damage: bool = False      # CONTROL: снять при уроне (Sleep)
    condition_repeat_save: bool = False         # CONTROL: повторный спасбросок в конце хода (Hold Person)
```

Валидация `__post_init__` для `CONTROL`:

- `condition` обязателен;
- ровно один гейт: `hp_pool_dice` **xor** `save_ability`
  (пул-механика против спасброска-резиста);
- `condition_repeat_save=True` требует `save_ability` (есть что перебрасывать);
- `hp_pool_dice` валидируется как `DiceExpr` (через parse в репозитории, не в domain).

`ConditionId` уже живёт в `domain/values/ids` → импорт в `spell.py` слой не
нарушает (guard-тест проходит).

### 3.2 События (application/dto/engine_event.py)

```python
@dataclass(frozen=True)
class ConditionApplied(EngineEvent):
    caster_id: CreatureId
    target_id: CreatureId
    spell_id: SpellId | None              # None — состояние не от заклинания (задел)
    conditions: frozenset[ConditionId]    # фактически наложенные (с implies)
    ends_on_damage: bool
    repeat_save_ability: Ability | None   # есть → повторный спасбросок в конце хода
    save_dc: int | None
    concentration: bool

@dataclass(frozen=True)
class ConditionRemoved(EngineEvent):
    target_id: CreatureId
    conditions: frozenset[ConditionId]
    reason: str          # "damage" | "save" | "concentration_ended" | "manual"
```

`ConditionApplied` несёт всю мету снятия → `OngoingEffectTracker` восстанавливает
эффект из события, не завязываясь на внутренности хендлера.

### 3.3 `ControlSpellHandler` (application/engine/spells/handlers.py)

Регистрируется в `default_spell_effect_registry` на `SpellEffect.CONTROL`.
Сигнатура `apply(caster, targets, spell, ctx)` — как у прочих хендлеров.

- **Ветка пула** (`spell.hp_pool_dice is not None`, Sleep):
  1. бросок пула (`DiceExpr.parse(spell.hp_pool_dice)`, purpose=UTILITY);
  2. кандидаты = `targets`, у кого `is_alive and not is_at_zero_hp`,
     отсортированы по `hit_points.current` ↑;
  3. пока `pool >= cand.current_hp`: `ConditionService.apply_with_implies`,
     `pool -= cand.current_hp`, копим фактически наложенный набор;
     иначе стоп (книга: первый, на кого не хватило, не засыпает);
  4. на каждого наложенного — `publish(ConditionApplied(...))`.
- **Ветка спасброска** (`spell.save_ability is not None`, Hold Person):
  для каждой цели `roll_saving_throw(target, save_ability, dc, ctx)`;
  провал → `apply_with_implies` + `publish(ConditionApplied(...))`;
  успех → ничего (для лога — `SpellResisted`, см. ниже, опционально).
- Концентрация: если `spell.concentration` и хоть кого-то задели —
  `caster.concentration = spell.id` (как в BuffSpellHandler). При смене
  концентрации прежний эффект снимается через `ConcentrationBroken` (см. 3.4).

`apply_with_implies` уже отдаёт `ConditionApplyResult.applied` — именно этот
набор кладём в событие (его же будем снимать).

### 3.4 `OngoingEffectTracker` (новый: application/engine/effects/ongoing_effect_tracker.py)

Application-служба. Держит список активных эффектов и снимает по триггерам.

```python
@dataclass(frozen=True, slots=True)
class OngoingConditionEffect:
    caster_id: CreatureId
    target_id: CreatureId
    spell_id: SpellId | None
    conditions: frozenset[ConditionId]
    ends_on_damage: bool
    repeat_save_ability: Ability | None
    save_dc: int | None
    concentration: bool

class OngoingEffectTracker:
    def __init__(self, participants, event_bus, *, dice_roller, modifier_applier): ...
    def subscribe(self) -> None:
        # ConditionApplied → _on_applied (записать)
        # TurnEnded        → _on_turn_ended (повторный спасбросок)
        # DamageDealt      → _on_damage (пробуждение)
        # ConcentrationBroken → _on_concentration_broken (снять каст)
```

Логика триггеров:

- `_on_turn_ended(actor)` — для эффектов с `repeat_save_ability` на этом actor:
  `roll_saving_throw(...)`; успех → `_remove(effect, reason="save")`.
- `_on_damage(target, final_amount>0)` — для эффектов с `ends_on_damage` на цели:
  `_remove(effect, reason="damage")`.
- `_on_concentration_broken(caster, spell)` — снять эффекты с этим `caster`+`spell`.
- `_remove(effect, reason)` — снять **ровно** `effect.conditions` у цели
  (`creature.remove_condition` по каждому id), удалить эффект из списка,
  `publish(ConditionRemoved(target, conditions, reason))`.

**Спасбросок без боевого `ctx`.** `roll_saving_throw` сейчас принимает полный
`TurnContext`, но использует из него только `dice_roller` и `modifier_applier`.
Выделяем low-level обёртку (без протечки боевого контекста за пределы хода):

```python
def roll_saving_throw_raw(
    actor, ability, *, dc, dice_roller, modifier_applier,
    tags=("saving_throw",),
) -> bool: ...
# roll_saving_throw(..., ctx=...) делегирует в raw, передавая ctx.dice_roller / ctx.modifier_applier
```

`OngoingEffectTracker` получает `dice_roller` + `modifier_applier` в конструкторе
и зовёт `roll_saving_throw_raw` на `TurnEnded`. Существующий вызов в
`SaveSpellHandler` не меняется (через `roll_saving_throw(ctx=...)`).

**Ограничение (осознанное):** снятие снимает сохранённый набор `conditions`
безусловно; если два эффекта наложили одно состояние, снятие первого уберёт
общее. Для MVP-боёв допустимо; отмечено в доке и ROADMAP как задел.

### 3.5 Wiring

- `OngoingEffectTracker` создаётся в composition при сборке боя (рядом с
  `XpAwardService`) и `.subscribe()`. Получает `participants` энкаунтера.
- В CLI (`interfaces/cli/app.py`) и TUI (`interfaces/tui/app.py`) — подписка
  по аналогии с XP/level-up wiring.
- **Пропуск хода инкапаситированных:** проверить, что `Encounter`/`GameRunner`/
  `SimpleMonsterAI` пропускают ход актёра с `INCAPACITATED` (Paralyzed/Unconscious
  его implies). Если нет — добавить guard (актёр под Incapacitated не получает
  действий; ход сразу завершается). Спасбросок Hold Person в конце такого хода
  всё равно срабатывает (TurnEnded публикуется).

### 3.6 Контент и правка техдолга (data/content/spells.yaml)

- **Новые заклинания:**
  - `sleep` — level 1, school enchantment, effect control, targeting AREA
    circle radius_ft 5 origin at_point, range 90, condition unconscious,
    hp_pool_dice "5d8", condition_ends_on_damage true.
  - `hold_person` — level 2, school enchantment, effect control, targeting
    SINGLE, range 60, condition paralyzed, save_ability WIS, concentration true,
    condition_repeat_save true.
- **Фикс уровней (техдолг P2):** `fireball` 1→**3**, `lightning_bolt` 1→**3**,
  `burning_hands` остаётся **1** (проверить — должно быть 1). Теперь у мага L1
  (ячейки только 1-го круга) Fireball/Lightning Bolt известны, но не кастуются
  до появления ячеек 3-го круга — `can_perform_against` это уже отсекает
  (`no spell slot of level N`).
- `mage_apprentice.known_spells` += `sleep`, `hold_person`.

### 3.7 Рендер (UI)

- CLI `event_printer.py`: `ConditionApplied` → `💤 goblin засыпает (Unconscious)` /
  `🔒 orc парализован (Hold Person)`; `ConditionRemoved` → `goblin просыпается`
  / `orc стряхивает удержание`. Тексты bilingual через i18n-механику проекта.
- TUI bridge: `ConditionApplied`/`ConditionRemoved` → рефреш карты/инициативы
  (состояние влияет на бейджи существа).

## 4. Расширяемость

- Новый контроль-спелл = строка YAML (`effect: control` + поля). Хендлер один.
- Новый триггер снятия = новый флаг в `Spell`/`ConditionApplied` + ветка в
  `OngoingEffectTracker` (open/closed на уровне триггеров; не switch по спеллам).
- T3 переиспользует трекер для длительностей (раунды/конец боя) и авто-провалов.

## 5. Тестирование

- **Юнит `ControlSpellHandler`:** пул-ветка (порядок по HP, остановка пула,
  кого усыпило); save-ветка (провал→состояние, успех→чисто); концентрация
  выставляется.
- **Юнит `OngoingEffectTracker`:** запись по `ConditionApplied`; снятие по
  `TurnEnded`+успешный спасбросок; снятие по `DamageDealt`; снятие по
  `ConcentrationBroken`; набор снятых состояний == наложенному.
- **Интеграция:** cast sleep по 2 гоблинам → оба Unconscious; урон по одному →
  он просыпается, второй спит. Cast hold person → Paralyzed; конец его хода,
  успешный спасбросок → свободен; срыв концентрации кастера → свободен.
- **Контент-тест:** `sleep`/`hold_person` парсятся; уровни fireball=3,
  lightning_bolt=3, burning_hands=1.
- **e2e-смок:** маг усыпляет гоблина в `mage_skirmish`-подобной сцене, бой
  сходится (`ScriptedRNG`).
- Регрессия: полный `pytest -q` + `mypy strict` + `ruff` + guard слоёв.

## 6. Инварианты

1. `condition is not None` ⟺ `effect is CONTROL` (валидация Spell).
2. CONTROL: ровно один из `hp_pool_dice` / `save_ability`.
3. `OngoingEffectTracker` снимает **ровно** наложенный набор состояний.
4. Инкапаситированный актёр не совершает действий (но TurnEnded публикуется →
   повторный спасбросок отыгрывается).
5. domain не импортирует application (guard-тест зелёный); `ConditionId` — domain.
6. Backward-compat: новые поля `Spell` имеют дефолты; существующие заклинания
   (ATTACK/SAVE/AUTO/HEAL/BUFF) не затронуты.

## 7. Декомпозиция (для плана)

- **T2-1** `SpellEffect.CONTROL` + поля `Spell` + валидация + YAML-parse + тесты.
- **T2-2** события `ConditionApplied` / `ConditionRemoved`.
- **T2-3** `roll_saving_throw_raw` обёртка + `OngoingEffectTracker` (запись +
  3 триггера снятия) + тесты.
- **T2-4** `ControlSpellHandler` (пул + save ветки, публикация события) + регистрация.
- **T2-5** wiring (composition + CLI/TUI subscribe) + пропуск хода инкапаситированных.
- **T2-6** контент: `sleep`, `hold_person`, фикс уровней, `known_spells`; рендер CLI/TUI.
- **T2-7** e2e-смок + доки (SPELLS.md, CONDITIONS/DYING ссылки, ROADMAP T2 ✅).

## 8. Отложено (в T3/далее)

- Тип существа (humanoid) → ограничение целей Hold Person; «снять Sleep действием
  союзника»; длительность в раундах/минутах (1 мин) и конец-боя-сброс.
- Стэкинг разных эффектов на одно состояние (см. 3.4).
- Авто-провалы спасбросков под Paralyzed/Unconscious, авто-крит в упор,
  cross-creature преимущество — этап **T3**.
