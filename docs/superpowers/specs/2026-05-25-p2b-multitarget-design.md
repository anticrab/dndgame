# P2b — мультитаргет заклинаний (мультимножество выборов)

**Дата:** 2026-05-25
**Этап:** P2b (линия заклинаний; продолжение P1 single/self + P2 AoE)
**Статус:** дизайн одобрен, спек на ревью

## 1. Цель

Реализовать `TargetKind.MULTI` — выбор игроком нескольких целей заклинания.
Модель — **мультимножество из N «попаданий»** (а не просто N разных целей):
заклинание задаёт лимит `max_targets` и флаг `allow_repeat_target`. Если повторы
разрешены, одну цель можно выбрать несколько раз — **повторным выбором этой
цели в UI, без ввода чисел**. Это одной механикой покрывает оба классических
случая:

* **Bless** — до 3 *разных* союзников, каждому +1d4 к броскам атаки и
  спасброскам (концентрация). `allow_repeat=False`.
* **Magic Missile** — 3 дротика, можно несколько в одну цель; распределение
  урона. `allow_repeat=True`.

Распределение «само» вытекает из того, что хендлеры эффектов уже итерируют
`for target in targets`: кортеж целей с дублями → дубль = ещё одно применение
эффекта (ещё один дротик/бросок).

## 2. Принципы (project-wide)

* Расширяемость через данные/реестры, не switch — Spell остаётся data-driven;
  никаких новых веток-исключений в `CastSpellAction`.
* Гасить техдолг сразу: обобщаем модель баффа (а не плодим узкие поля),
  мигрируем `ac_bonus` в новый формат, доводим Bless до полной работоспособности
  (атака И спасброски), без «полуготовых» эффектов.
* `domain` не зависит от `application` (guard-тест `tests/unit/test_layering.py`).
  Новые типы (`BuffSpec`) живут в `domain/values/spell.py`.

## 3. Изменения данных (domain)

### 3.1 `TargetingSpec` (`domain/values/spell.py`)

Добавить поле:

```python
allow_repeat_target: bool = False  # MULTI: можно ли класть >1 «попадания» в одну цель
```

`__post_init__`: для `kind=MULTI` требовать `max_targets >= 1`. `allow_repeat`
осмыслен только при MULTI (для прочих видов оставляем дефолт `False`, не
валидируем строго — поле просто игнорируется).

### 3.2 `BuffSpec` — новый VO (`domain/values/spell.py`)

Обобщаем бафф: вместо одиночного `Spell.ac_bonus: int` — кортеж описаний
модификаторов.

```python
@dataclass(frozen=True, slots=True)
class BuffSpec:
    """Один модификатор, который BUFF-заклинание накладывает на цель.

    Ровно одно из полей задаёт эффект: numeric_bonus (например, +2 КД у
    Shield of Faith) или dice_bonus (например, +1d4 к атаке/спасброскам у Bless).
    """
    target: ModifierTargetKind          # из domain.values.modifiers
    numeric_bonus: int = 0
    dice_bonus: str | None = None        # сериализованный DiceExpr, напр. "1d4"

    def __post_init__(self) -> None:
        has_numeric = self.numeric_bonus != 0
        has_dice = self.dice_bonus is not None
        if has_numeric == has_dice:      # ни одного или оба
            raise ValueError("BuffSpec требует ровно одно: numeric_bonus ИЛИ dice_bonus")
```

`import` — `from dnd.domain.values.modifiers import ModifierTargetKind` (domain→domain, guard не нарушается).

### 3.3 `Spell` (`domain/values/spell.py`)

* Удалить поле `ac_bonus: int = 0`.
* Добавить `buffs: tuple[BuffSpec, ...] = ()`.
* `__post_init__`: для `SpellEffect.BUFF` требовать `len(self.buffs) >= 1`
  (вместо прежней проверки `ac_bonus > 0`).

### 3.4 YAML-репозиторий заклинаний

`YamlSpellRepository` должен парсить:

* `targeting.allow_repeat_target: bool` (опционально, дефолт False);
* `buffs:` — список объектов `{ target, numeric_bonus?, dice_bonus? }`;
  `target` — строковое значение `ModifierTargetKind` (`armor_class`,
  `attack_roll`, `saving_throw`, ...).

Старое поле `ac_bonus` в YAML **удаляется** (мигрируем контент, не оставляем
shim).

## 4. Резолвинг целей (`CastSpellAction`)

### 4.1 Параметры/интент

`CastSpellParams` (`application/engine/actions/cast_spell.py`) и `CastSpellIntent`
(`application/dto/player_intent.py`) получают новое поле:

```python
target_ids: tuple[CreatureId, ...] = ()   # MULTI: мультимножество выборов (порядок=выборы, дубли допустимы)
```

(Существующие `target_id` / `target_point` / `direction` сохраняются для
SINGLE/AREA.)

### 4.2 `_resolve_targets` — ветка MULTI

Заменить `raise NotImplementedError` на:

```python
if kind is TargetKind.MULTI:
    return tuple(ctx.participants[cid] for cid in params.target_ids)
```

Возвращается кортеж **с дублями в исходном порядке** — хендлеры применят
эффект по разу на каждый элемент (дубль = ещё одно попадание). Валидность
гарантирует `can_perform_against` (см. 4.3), здесь — чистая выборка.

### 4.3 `can_perform_against` — ветка MULTI

Добавить (после SINGLE/AREA):

```python
elif spell.targeting.kind is TargetKind.MULTI:
    spec = spell.targeting
    if not params.target_ids:
        return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
    if len(params.target_ids) > spec.max_targets:
        return Forbidden(reason=ForbiddenReason.CUSTOM,
                         details=f"too many targets (max {spec.max_targets})")
    if not spec.allow_repeat_target and len(set(params.target_ids)) != len(params.target_ids):
        return Forbidden(reason=ForbiddenReason.CUSTOM,
                         details="repeat targets not allowed")
    actor_pos = ctx.battlefield.position_of(actor.id)
    offensive = spell.effect in (SpellEffect.ATTACK, SpellEffect.SAVE, SpellEffect.AUTO)
    for cid in set(params.target_ids):       # проверяем уникальные
        if cid not in ctx.participants:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        target = ctx.participants[cid]
        # liveness — как в SINGLE (audit MAJOR-2)
        if offensive:
            if not target.is_alive:
                return Forbidden(reason=ForbiddenReason.TARGET_DOWN)
        elif not target.is_alive and not (
            target.death_saves is not None and not target.death_saves.is_dead
        ):
            return Forbidden(reason=ForbiddenReason.TARGET_DOWN)
        if actor_pos.distance_to_feet(ctx.battlefield.position_of(cid)) > spell.range_ft:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
```

## 5. Хендлеры эффектов

### 5.1 `BuffSpellHandler` — обобщение (`application/engine/spells/handlers.py`)

Сейчас вшит `ARMOR_CLASS` + `NumericBonusEffect(value=spell.ac_bonus)`. Заменить
на цикл по `spell.buffs`: для каждой цели и каждого `BuffSpec` собрать `Modifier`
с эффектом по типу:

```python
for target in targets:
    for buff in spell.buffs:
        effect = (
            DiceBonusEffect(dice=buff.dice_bonus)
            if buff.dice_bonus is not None
            else NumericBonusEffect(value=buff.numeric_bonus)
        )
        ctx.modifier_applier.add(Modifier(
            source_id=source_id,
            source_kind=ModifierSourceKind.SPELL,
            target_kind=buff.target,
            effect=effect,
            owner_id=target.id,
            stack_key=str(spell.id),
        ))
```

Логика концентрации (снятие прежнего concentration-source, установка
`caster.concentration`) сохраняется как есть. `source_id` для concentration —
`concentration_source(caster.id)`; для не-concentration баффов — `str(spell.id)`
(на будущее; текущие баффы все concentration).

### 5.2 Спелловые броски читают модификаторы (чтобы Bless работал везде)

`AttackAction` уже собирает `ATTACK_ROLL`-модификаторы и прокидывает
`extra_dice` (`attack.py:271`) — значит Bless'нутый союзник, атакующий
**оружием**, уже получает +1d4. Чтобы Bless работал и на спелл-атаках/спасбросках,
добавить сбор модификаторов в спелл-хендлеры:

* `AttackSpellHandler`: при броске спелл-атаки собрать `ATTACK_ROLL`-модификаторы
  кастера (`collect(owner_id=caster.id, target_kind=ATTACK_ROLL)` →
  `to_roll_adjustments` → `RollContext(numeric/extra_dice)`).
* `SaveSpellHandler`: при спасброске цели собрать её `SAVING_THROW`-модификаторы
  (`collect(owner_id=target.id, ...)`), прокинуть `extra_dice` и `numeric_bonus`
  в `RollContext`.

Это доводит Bless до полной работоспособности (атака+спасбросок), без
полуготового эффекта. (Death-saves вне зоны — отдельная механика, не трогаем.)

## 6. Контент (`data/content/spells.yaml`)

### 6.1 Bless (новое)

```yaml
- id: bless
  name: "Bless"
  level: 1
  school: enchantment
  effect: buff
  targeting: { kind: multi, max_targets: 3, allow_repeat_target: false }
  range_ft: 30
  concentration: true
  buffs:
    - { target: attack_roll, dice_bonus: "1d4" }
    - { target: saving_throw, dice_bonus: "1d4" }
  description: "Благословить до трёх существ: пока держится концентрация, каждое добавляет 1d4 к броскам атаки и спасброскам."
```

### 6.2 Shield of Faith — миграция на `buffs`

```yaml
  buffs:
    - { target: armor_class, numeric_bonus: 2 }
```
(удалить `ac_bonus: 2`.)

### 6.3 Magic Missile — переопределить как распределяемый MULTI

```yaml
- id: magic_missile
  effect: auto
  targeting: { kind: multi, max_targets: 3, allow_repeat_target: true }
  range_ft: 120
  dice: "1d4+1"        # за один дротик
  damage_type: force
  description: "Три светящихся дротика бьют автоматически. Каждый — 1d4+1 силового урона; дротики распределяются между целями (можно несколько в одну)."
```
(было: single, `3d4+3`.)

## 7. TUI — `BattleMode.MULTI_TARGET`

Новый режим-хендлер `interfaces/tui/screens/battle_modes/multi_target_mode.py`
(по образцу `TargetModeHandler` / `AreaModeHandler`):

* вход — когда выбранное заклинание имеет `targeting.kind is MULTI`
  (аналогично тому, как SINGLE → TARGET, AREA → AREA);
* **навигация:** Tab / Shift+Tab — циклить кандидатов (живые существа в range;
  для offensive — враги, для heal/buff — союзники, переиспользовать логику
  `_list_spell_targets`);
* **выбор:** Space — добавить одно «попадание» текущей цели. Если
  `allow_repeat=False` и цель уже выбрана — игнор. Если `allow_repeat=True`
  — добавляется ещё одно попадание;
* **снятие:** Backspace — снять последнее добавленное попадание;
* **остаток:** добавлять можно, пока `len(picks) < max_targets`;
* **подтверждение:** Enter — подтвердить текущий набор (отдельно от Space, чтобы
  «добавить» и «подтвердить» не конфликтовали); авто-подтверждение при
  достижении максимума опционально. Esc — отмена (очистить состояние, вернуться
  в NORMAL);
* **хинт-счётчик** (наглядно, без чисел-ввода):
  `Bless: [Aelar ✦, Borin ✦] — выбери ещё 1 (3 макс)` /
  `Magic Missile: [гоблин A ✦✦, гоблин B ✦] — 0 осталось`;
* **превью:** выбранные цели подсвечены, рядом число попаданий (✦×N).

Хендлер хранит `picks: list[CreatureId]` (список = мультимножество с порядком),
по подтверждении отдаёт его в `BattleScreen`.

### 7.1 Wiring в `BattleScreen` (`battle.py`)

* `_trigger_ability`: если spell.targeting.kind is MULTI → войти в MULTI_TARGET
  mode с нужным списком кандидатов и спецификацией (max/allow_repeat);
* по подтверждении — `_submit_multi_intent(picks)` строит
  `CastSpellIntent(spell_id=..., target_ids=tuple(picks))` (по образцу
  `_submit_area_intent`);
* `spell_ability._factory` / `Ability.requires_target`: MULTI не использует
  одиночный `requires_target` (как и AREA) — маршрутизация по `targeting.kind`
  в BattleScreen, фабрика интента для MULTI собирается в `_submit_multi_intent`,
  не через `_factory(target_id)`.

## 8. Тесты

**domain:**
* `BuffSpec.__post_init__`: ровно одно из numeric/dice (оба/ни одного → ValueError).
* `Spell` BUFF требует `len(buffs) >= 1`.
* `TargetingSpec` MULTI: `max_targets >= 1`.

**application — резолвинг:**
* MULTI: `_resolve_targets` возвращает мультимножество с дублями в порядке.
* `can_perform_against` MULTI: пусто → Forbidden; превышение `max_targets` →
  Forbidden; дубли при `allow_repeat=False` → Forbidden; дубли при
  `allow_repeat=True` → Allowed; цель вне range → OUT_OF_RANGE; мёртвая
  offensive-цель → TARGET_DOWN.

**application — эффекты:**
* Magic Missile: 3 дротика по 2 целям (например (A,A,B)) → A получает 2 броска
  урона, B — 1 (распределение). ScriptedRNG, проверка суммарного урона/событий.
* Bless: после каста на союзника его **weapon-атака** (через AttackAction)
  получает +1d4 (extra_dice в RollContext) — проверка, что бонус-кость
  применилась.
* Bless: спелл-сейв Bless'нутой цели (`SaveSpellHandler`) включает +1d4
  (extra_dice) — после доработки 5.2.
* BuffSpellHandler generalized: Shield of Faith (numeric AC +2) и Bless
  (dice attack/save) дают корректные `Modifier`'ы (target_kind, effect-тип).
* Концентрация: новый concentration-бафф снимает прежний (per-caster source) —
  регрессия не сломана.

**content:**
* `spells.yaml` грузится; `bless` присутствует; `magic_missile` — MULTI
  allow_repeat dice `1d4+1`; `shield_of_faith` — buffs[armor_class +2].
  (Обновить «морально устаревший» тест количества/полей заклинаний.)

**TUI (pilot, headless):**
* MULTI_TARGET: выбрать 3 разные цели для Bless → подтверждение шлёт
  `CastSpellIntent.target_ids` из 3 id.
* MULTI_TARGET с allow_repeat: дважды выбрать одну цель + раз другую →
  `target_ids == (A, A, B)`; счётчик показывает ✦✦/✦.
* Backspace снимает последнее попадание; Esc отменяет и чистит состояние.

**регрессия:** весь набор (≈1246+) зелёный; mypy strict; ruff.

## 9. Декомпозиция задач

* **P2b-1** — `TargetingSpec.allow_repeat_target` + `BuffSpec` VO + `Spell.buffs`
  (удалить `ac_bonus`), domain-тесты.
* **P2b-2** — `YamlSpellRepository`: парсинг `allow_repeat_target` + `buffs`;
  миграция Shield of Faith на `buffs`; тест загрузки.
* **P2b-3** — `BuffSpellHandler` обобщённый (numeric + dice модификаторы);
  тесты Shield of Faith + общая форма.
* **P2b-4** — `target_ids` в `CastSpellParams`/`CastSpellIntent`;
  `_resolve_targets` MULTI + `can_perform_against` MULTI; тесты резолвинга.
* **P2b-5** — Magic Missile → MULTI distributable (YAML) + smoke распределения
  урона.
* **P2b-6** — Bless в YAML + сбор `ATTACK_ROLL`/`SAVING_THROW` модификаторов в
  спелл-хендлерах (5.2); тесты «+1d4 реально применяется» (weapon-атака + спелл-сейв).
* **P2b-7** — TUI `BattleMode.MULTI_TARGET` + хендлер + wiring в BattleScreen
  (`_submit_multi_intent`); pilot-тесты.
* **P2b-8** — docs `SPELLS.md` (мультитаргет, распределение, Bless) + `TUI.md`
  (MULTI_TARGET режим) + `ROADMAP.md`; финальный независимый аудит.

## 10. Инварианты

1. `target_ids` непуст и `len ≤ max_targets`; при `allow_repeat=False` — без
   дублей (проверка в `can_perform_against`).
2. Порядок и дубли `target_ids` сохраняются в резолвинге → корректное
   распределение (Magic Missile).
3. `BuffSpec` — ровно один эффект (numeric XOR dice).
4. Одна концентрация на кастера (per-caster source) — не регрессирует.
5. `domain` не импортирует внешние слои (guard-тест).
6. Backward-compat: SELF/SINGLE/AREA-заклинания не затронуты; миграция
   `ac_bonus`→`buffs` не меняет поведение Shield of Faith.
