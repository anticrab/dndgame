# P2b — Мультитаргет заклинаний: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать `TargetKind.MULTI` — выбор нескольких целей заклинания как мультимножество выборов (Bless на N союзников, распределение дротиков Magic Missile), плюс обобщённый бафф (numeric + dice модификаторы).

**Architecture:** Цели MULTI — кортеж `target_ids` с возможными дублями (порядок = выборы); хендлеры эффектов уже итерируют цели, поэтому дубль = ещё одно применение. Бафф data-driven: `Spell.buffs: tuple[BuffSpec, ...]` вместо узкого `ac_bonus`. TUI получает режим `MULTI_TARGET` (повтор = повторный выбор цели, без ввода чисел).

**Tech Stack:** Python 3.12, pydantic v2 (frozen), dataclasses (frozen/slots) для domain VO, Textual TUI (Pilot headless tests), pytest, mypy strict, ruff.

**Спек:** `docs/superpowers/specs/2026-05-25-p2b-multitarget-design.md`

**Соглашения проекта:**
- Коммиты: автор `Maxim Lokotkov`, email `anticrab@users.noreply.github.com`. Команда:
  `git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "..."`
- Документация и комментарии — на русском.
- После каждой задачи прогнать: `pytest -q`, `mypy src`, `ruff check src tests`.
- НИКОГДА: `git push`, `git reset --hard`, `git rebase`, `--no-verify`.

---

## Структура файлов

**Изменяются:**
- `src/dnd/domain/values/spell.py` — `BuffSpec` VO; `TargetingSpec.allow_repeat_target`; `Spell.buffs` (вместо `ac_bonus`).
- `src/dnd/infrastructure/content/yaml_spell_repository.py` — парсинг `allow_repeat_target`, `buffs`.
- `src/dnd/application/engine/spells/handlers.py` — `BuffSpellHandler` обобщён; `AttackSpellHandler`/`SaveSpellHandler` собирают модификаторы.
- `src/dnd/application/engine/actions/cast_spell.py` — `CastSpellParams.target_ids`; `_resolve_targets` MULTI; `can_perform_against` MULTI.
- `src/dnd/application/dto/player_intent.py` — `CastSpellIntent.target_ids`.
- `src/dnd/interfaces/tui/screens/battle_modes/protocol.py` — `BattleMode.MULTI_TARGET`; контекст `_multi_max_targets`, `_multi_allow_repeat`.
- `src/dnd/interfaces/tui/screens/battle.py` — wiring MULTI mode.
- `data/content/spells.yaml` — `bless` (новое), `magic_missile` (переопределение), `shield_of_faith` (миграция).
- `docs/SPELLS.md`, `docs/TUI.md`, `docs/ROADMAP.md`.

**Создаются:**
- `src/dnd/interfaces/tui/screens/battle_modes/multi_target_mode.py` — `MultiTargetModeHandler`.
- `tests/integration/engine/test_cast_spell_multi.py` — резолвинг + эффекты MULTI.
- `tests/integration/tui/test_multi_target_mode.py` — pilot-тесты выбора.

**Тесты, которые «морально устареют» и обновляются по ходу:**
- `tests/unit/domain/test_spell.py` (`test_valid_buff_spell` — `ac_bonus`→`buffs`).
- `tests/integration/content/test_yaml_spell_repository.py` (`test_loads_all_spells` +bless; `test_shield_of_faith_buff` — `ac_bonus`→`buffs`).
- `tests/integration/engine/test_cast_spell.py` (`test_magic_missile_*` — урон 3d4+3 single → distributable; см. Task 5).

---

## Task 1 (P2b-1): domain — BuffSpec, allow_repeat_target, Spell.buffs

**Files:**
- Modify: `src/dnd/domain/values/spell.py`
- Test: `tests/unit/domain/test_spell.py`

- [ ] **Step 1: Написать падающие тесты**

В конец `tests/unit/domain/test_spell.py` добавить:

```python
# --- P2b-1: BuffSpec + MULTI targeting -----------------------------------

def test_buffspec_numeric_only_valid() -> None:
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.spell import BuffSpec
    b = BuffSpec(target=ModifierTargetKind.ARMOR_CLASS, numeric_bonus=2)
    assert b.numeric_bonus == 2 and b.dice_bonus is None


def test_buffspec_dice_only_valid() -> None:
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.spell import BuffSpec
    b = BuffSpec(target=ModifierTargetKind.ATTACK_ROLL, dice_bonus="1d4")
    assert b.dice_bonus == "1d4" and b.numeric_bonus == 0


def test_buffspec_both_rejected() -> None:
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.spell import BuffSpec
    with pytest.raises(ValueError):
        BuffSpec(target=ModifierTargetKind.ARMOR_CLASS, numeric_bonus=2, dice_bonus="1d4")


def test_buffspec_neither_rejected() -> None:
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.spell import BuffSpec
    with pytest.raises(ValueError):
        BuffSpec(target=ModifierTargetKind.ARMOR_CLASS)


def test_buff_spell_requires_at_least_one_buff() -> None:
    with pytest.raises(ValueError):
        Spell(
            id=SpellId("x"), name="X", level=1, school="e",
            effect=SpellEffect.BUFF, targeting=TargetingSpec(kind=TargetKind.SINGLE),
            range_ft=60, description="", buffs=(),
        )


def test_multi_targeting_requires_positive_max() -> None:
    with pytest.raises(ValueError):
        TargetingSpec(kind=TargetKind.MULTI, max_targets=0)


def test_multi_targeting_allow_repeat_field() -> None:
    spec = TargetingSpec(kind=TargetKind.MULTI, max_targets=3, allow_repeat_target=True)
    assert spec.allow_repeat_target is True and spec.max_targets == 3
```

Также **обновить морально устаревший** `test_valid_buff_spell` (он использует удаляемое `ac_bonus`):

```python
def test_valid_buff_spell() -> None:
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.spell import BuffSpec
    s = Spell(
        id=SpellId("shield_of_faith"), name="Shield of Faith", level=1,
        school="abjuration", effect=SpellEffect.BUFF,
        targeting=TargetingSpec(kind=TargetKind.SINGLE), range_ft=60,
        description="+2 КД.",
        buffs=(BuffSpec(target=ModifierTargetKind.ARMOR_CLASS, numeric_bonus=2),),
        concentration=True,
    )
    assert s.buffs[0].numeric_bonus == 2 and s.concentration is True
```

- [ ] **Step 2: Прогнать тесты — убедиться, что падают**

Run: `pytest tests/unit/domain/test_spell.py -q`
Expected: FAIL — `ImportError: cannot import name 'BuffSpec'` / `TypeError: ... unexpected keyword argument 'buffs'`.

- [ ] **Step 3: Реализовать**

В `src/dnd/domain/values/spell.py`:

(а) добавить импорт под существующие domain-импорты:

```python
from dnd.domain.values.modifiers import ModifierTargetKind
```

(б) добавить `allow_repeat_target` в `TargetingSpec` (после `length_ft`):

```python
    length_ft: int = 0
    allow_repeat_target: bool = False
```

и расширить `__post_init__` `TargetingSpec` — добавить ветку MULTI В НАЧАЛО проверок:

```python
    def __post_init__(self) -> None:
        if self.kind is TargetKind.MULTI and self.max_targets < 1:
            raise ValueError("MULTI targeting requires max_targets >= 1")
        if self.kind is not TargetKind.AREA:
            return
        if self.shape is None:
            raise ValueError("AREA targeting requires a shape")
        if self.shape is AreaShape.CIRCLE and self.radius_ft <= 0:
            raise ValueError("CIRCLE area requires radius_ft > 0")
        if self.shape in (AreaShape.CONE, AreaShape.LINE) and self.length_ft <= 0:
            raise ValueError(f"{self.shape} area requires length_ft > 0")
```

(в) добавить `BuffSpec` перед классом `Spell`:

```python
@dataclass(frozen=True, slots=True)
class BuffSpec:
    """Один модификатор, накладываемый BUFF-заклинанием на цель.

    Ровно одно из полей задаёт эффект: ``numeric_bonus`` (например, +2 КД у
    Shield of Faith) ИЛИ ``dice_bonus`` (например, +1d4 к атаке/спасброскам у Bless).
    ``target`` — категория броска/значения (:class:`ModifierTargetKind`).
    """

    target: ModifierTargetKind
    numeric_bonus: int = 0
    dice_bonus: str | None = None

    def __post_init__(self) -> None:
        has_numeric = self.numeric_bonus != 0
        has_dice = self.dice_bonus is not None
        if has_numeric == has_dice:
            raise ValueError(
                "BuffSpec требует ровно одно: numeric_bonus ИЛИ dice_bonus"
            )
```

(г) в `Spell`: удалить поле `ac_bonus: int = 0`, добавить:

```python
    buffs: tuple[BuffSpec, ...] = ()       # для BUFF (Shield of Faith, Bless)
```

(д) в `Spell.__post_init__` заменить ветку BUFF:

```python
        elif self.effect is SpellEffect.BUFF and not self.buffs:
            raise ValueError(
                f"BUFF spell {self.id} requires at least one BuffSpec"
            )
```

(е) добавить `BuffSpec` в `__all__`.

- [ ] **Step 4: Прогнать тесты — зелёные**

Run: `pytest tests/unit/domain/test_spell.py -q`
Expected: PASS.

Затем `mypy src` (ожидаемо: ошибки в `handlers.py`/`yaml_spell_repository.py` про `ac_bonus` — их чиним в Task 2/3; на этом шаге допустимо, но лучше прогнать только `mypy src/dnd/domain` → должно быть чисто).

Run: `mypy src/dnd/domain && ruff check src/dnd/domain/values/spell.py tests/unit/domain/test_spell.py`
Expected: чисто.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/domain/values/spell.py tests/unit/domain/test_spell.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(p2b-1): BuffSpec + allow_repeat_target + Spell.buffs (вместо ac_bonus)"
```

---

## Task 2 (P2b-2): YamlSpellRepository — парсинг buffs + allow_repeat_target; миграция Shield of Faith

**Files:**
- Modify: `src/dnd/infrastructure/content/yaml_spell_repository.py`
- Modify: `data/content/spells.yaml` (только `shield_of_faith`)
- Test: `tests/integration/content/test_yaml_spell_repository.py`

- [ ] **Step 1: Обновить spells.yaml — Shield of Faith на buffs**

В `data/content/spells.yaml` заменить блок `shield_of_faith`:

```yaml
- id: shield_of_faith
  name: "Shield of Faith"
  level: 1
  school: abjuration
  effect: buff
  targeting: { kind: single }
  range_ft: 60
  concentration: true
  buffs:
    - { target: armor_class, numeric_bonus: 2 }
  description: "Мерцающее поле даёт цели +2 к КД. Требует концентрации."
```

(удалена строка `ac_bonus: 2`, добавлен блок `buffs`.)

- [ ] **Step 2: Обновить морально устаревший тест + написать новый**

В `tests/integration/content/test_yaml_spell_repository.py` заменить `test_shield_of_faith_buff`:

```python
def test_shield_of_faith_buff() -> None:
    from dnd.domain.values.modifiers import ModifierTargetKind
    s = YamlSpellRepository(_SPELLS).load(SpellId("shield_of_faith"))
    assert s.effect is SpellEffect.BUFF and s.concentration is True
    assert len(s.buffs) == 1
    assert s.buffs[0].target is ModifierTargetKind.ARMOR_CLASS
    assert s.buffs[0].numeric_bonus == 2
```

- [ ] **Step 3: Прогнать тесты — падают**

Run: `pytest tests/integration/content/test_yaml_spell_repository.py::test_shield_of_faith_buff -q`
Expected: FAIL — `AttributeError: 'Spell' object has no attribute 'buffs'` уже исправлено в Task 1, но репозиторий ещё парсит `ac_bonus` → Spell без buffs → `len(s.buffs) == 0` ≠ 1 → AssertionError (или ValueError при загрузке: BUFF без buffs).

- [ ] **Step 4: Реализовать парсинг**

В `yaml_spell_repository.py`:

(а) расширить импорт из domain:

```python
from dnd.domain.values.modifiers import ModifierTargetKind
from dnd.domain.values.spell import (
    AreaShape,
    BuffSpec,
    OriginMode,
    Spell,
    SpellEffect,
    TargetingSpec,
    TargetKind,
)
```

(б) в `_parse`, в конструкторе `TargetingSpec` добавить:

```python
            length_ft=int(tgt.get("length_ft", 0)),
            allow_repeat_target=bool(tgt.get("allow_repeat_target", False)),
        )
```

(в) перед `return Spell(...)` собрать buffs:

```python
        buffs = tuple(
            BuffSpec(
                target=ModifierTargetKind(b["target"]),
                numeric_bonus=int(b.get("numeric_bonus", 0)),
                dice_bonus=b.get("dice_bonus"),
            )
            for b in entry.get("buffs", [])
        )
```

(г) в конструкторе `Spell(...)` заменить `ac_bonus=int(entry.get("ac_bonus", 0)),` на:

```python
            buffs=buffs,
```

- [ ] **Step 5: Прогнать тесты — зелёные**

Run: `pytest tests/integration/content/test_yaml_spell_repository.py -q && mypy src/dnd/infrastructure/content/yaml_spell_repository.py && ruff check src/dnd/infrastructure/content/yaml_spell_repository.py`
Expected: PASS, mypy/ruff чисто.

- [ ] **Step 6: Commit**

```bash
git add src/dnd/infrastructure/content/yaml_spell_repository.py data/content/spells.yaml tests/integration/content/test_yaml_spell_repository.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(p2b-2): YAML парсит buffs + allow_repeat_target; Shield of Faith → buffs"
```

---

## Task 3 (P2b-3): BuffSpellHandler — обобщение (numeric + dice модификаторы)

**Files:**
- Modify: `src/dnd/application/engine/spells/handlers.py`
- Test: `tests/integration/engine/test_cast_spell.py`

- [ ] **Step 1: Написать падающий тест**

В `tests/integration/engine/test_cast_spell.py` добавить (рядом с BUFF-тестами):

```python
def test_buff_handler_applies_dice_bonus_to_attack_and_save() -> None:
    """Обобщённый BuffSpellHandler: dice-бафф к ATTACK_ROLL и SAVING_THROW."""
    from dnd.application.engine.spells.handlers import BuffSpellHandler
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.spell import (
        BuffSpec, Spell, SpellEffect, TargetingSpec, TargetKind,
    )
    _enc, mage, _gob, ctx = _setup([20, 19])
    spell = Spell(
        id=SpellId("bless_like"), name="Bless", level=1, school="enchantment",
        effect=SpellEffect.BUFF,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3),
        range_ft=30, description="", concentration=True,
        buffs=(
            BuffSpec(target=ModifierTargetKind.ATTACK_ROLL, dice_bonus="1d4"),
            BuffSpec(target=ModifierTargetKind.SAVING_THROW, dice_bonus="1d4"),
        ),
    )
    BuffSpellHandler().apply(mage, (mage,), spell, ctx)
    atk = ctx.modifier_applier.collect(
        owner_id=mage.id, target_kind=ModifierTargetKind.ATTACK_ROLL
    )
    save = ctx.modifier_applier.collect(
        owner_id=mage.id, target_kind=ModifierTargetKind.SAVING_THROW
    )
    assert ctx.modifier_applier.to_roll_adjustments(atk).extra_dice == ("1d4",)
    assert ctx.modifier_applier.to_roll_adjustments(save).extra_dice == ("1d4",)
```

- [ ] **Step 2: Прогнать тест — падает**

Run: `pytest tests/integration/engine/test_cast_spell.py::test_buff_handler_applies_dice_bonus_to_attack_and_save -q`
Expected: FAIL — `BuffSpellHandler` всё ещё ссылается на `spell.ac_bonus` (AttributeError) / не создаёт dice-модификаторы.

- [ ] **Step 3: Реализовать обобщение**

В `handlers.py`:

(а) расширить импорт из modifiers:

```python
from dnd.domain.values.modifiers import (
    DiceBonusEffect,
    Modifier,
    ModifierSourceKind,
    ModifierTargetKind,
    NumericBonusEffect,
)
```

(б) заменить тело цикла в `BuffSpellHandler.apply` (часть после установки `source_id`):

```python
        source_id = concentration_source(caster.id)
        for target in targets:
            for buff in spell.buffs:
                effect = (
                    DiceBonusEffect(dice=buff.dice_bonus)
                    if buff.dice_bonus is not None
                    else NumericBonusEffect(value=buff.numeric_bonus)
                )
                ctx.modifier_applier.add(
                    Modifier(
                        source_id=source_id,
                        source_kind=ModifierSourceKind.SPELL,
                        target_kind=buff.target,
                        effect=effect,
                        owner_id=target.id,
                        stack_key=str(spell.id),
                    )
                )
```

(Логика концентрации выше по методу — `remove_by_source` + установка `caster.concentration` — НЕ меняется. `ModifierTargetKind`, `NumericBonusEffect` уже импортированы — проверь, что нет дублей импорта.)

- [ ] **Step 4: Прогнать тесты — зелёные**

Run: `pytest tests/integration/engine/test_cast_spell.py -q && mypy src/dnd/application/engine/spells/handlers.py && ruff check src/dnd/application/engine/spells/handlers.py`
Expected: PASS (вкл. старые BUFF-тесты Shield of Faith — поведение AC +2 сохранено), mypy/ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/engine/spells/handlers.py tests/integration/engine/test_cast_spell.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(p2b-3): BuffSpellHandler — произвольные модификаторы (numeric + dice)"
```

---

## Task 4 (P2b-4): MULTI-резолвинг + target_ids в params/intent

**Files:**
- Modify: `src/dnd/application/engine/actions/cast_spell.py`
- Modify: `src/dnd/application/dto/player_intent.py`
- Test: `tests/integration/engine/test_cast_spell_multi.py` (создать)

- [ ] **Step 1: Создать падающий тест резолвинга**

Создать `tests/integration/engine/test_cast_spell_multi.py`:

```python
"""P2b-4: MULTI targeting — резолвинг мультимножества + валидация."""
from __future__ import annotations

from pathlib import Path

from dnd.application.dto.action import Allowed, Forbidden
from dnd.application.engine.actions.cast_spell import CastSpellAction, CastSpellParams
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.spell import (
    Spell, SpellEffect, TargetingSpec, TargetKind,
)
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_SPELLS = Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"


def _mage() -> Creature:
    c = Creature.create(
        id_="mage", name="Mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30,
    )
    c.spellcasting_ability = Ability.INT
    c.known_spells = (SpellId("magic_missile"),)
    c.spell_slots = {1: 4}
    return c


def _gob(id_: str, x: int, y: int) -> Creature:
    return Creature.create(
        id_=id_, name=id_,
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12, armor_class=13, speed_ft=30,
    )


def _setup(rolls: list[int]) -> tuple[Encounter, Creature, Creature, Creature, object]:
    mage = _mage()
    a, b = _gob("gobA", 3, 2), _gob("gobB", 4, 2)
    bf = Battlefield(8, 8)
    bf.place_creature(mage.id, Square(2, 2))
    bf.place_creature(a.id, Square(3, 2))
    bf.place_creature(b.id, Square(4, 2))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={mage.id: mage, a.id: a, b.id: b},
        factions={
            mage.id: Faction.PARTY, a.id: Faction.MONSTERS, b.id: Faction.MONSTERS,
        },
        deps=deps,
    )
    enc.start()
    for _ in range(12):
        if enc.current_actor_id == mage.id:
            break
        enc.start_turn()
        enc.end_turn()
    assert enc.current_actor_id == mage.id
    ctx = enc.start_turn()
    return enc, mage, a, b, ctx


from dnd.domain.values.square import Square  # noqa: E402


def _mm() -> Spell:
    return Spell(
        id=SpellId("mm"), name="MM", level=1, school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3, allow_repeat_target=True),
        range_ft=120, description="", dice="1d4+1", damage_type=DamageType.FORCE,
    )


class _OneSpellRepo:
    def __init__(self, spell: Spell) -> None:
        self._s = spell
    def contains(self, sid: SpellId) -> bool:
        return sid == self._s.id
    def load(self, sid: SpellId) -> Spell:
        return self._s
    def list_ids(self) -> tuple[SpellId, ...]:
        return (self._s.id,)


def test_resolve_multi_preserves_duplicates_and_order() -> None:
    _enc, mage, a, b, ctx = _setup([20, 19, 19])
    spell = _mm()
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    params = CastSpellParams(
        spell_id=spell.id, target_ids=(a.id, a.id, b.id),
    )
    resolved = action._resolve_targets(spell, mage, params, ctx)
    assert [c.id for c in resolved] == [a.id, a.id, b.id]


def test_multi_empty_targets_forbidden() -> None:
    _enc, mage, _a, _b, ctx = _setup([20, 19, 19])
    spell = _mm()
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=spell.id, target_ids=()), ctx
    )
    assert isinstance(avail, Forbidden)


def test_multi_too_many_forbidden() -> None:
    _enc, mage, a, b, ctx = _setup([20, 19, 19])
    spell = _mm()
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id, b.id, b.id)), ctx
    )
    assert isinstance(avail, Forbidden)  # 4 > max_targets=3


def test_multi_repeat_allowed_ok() -> None:
    _enc, mage, a, _b, ctx = _setup([20, 19, 19])
    spell = _mm()
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id, a.id)), ctx
    )
    assert isinstance(avail, Allowed)  # allow_repeat_target=True


def test_multi_repeat_forbidden_when_disallowed() -> None:
    _enc, mage, a, b, ctx = _setup([20, 19, 19])
    spell = Spell(
        id=SpellId("mm2"), name="MM2", level=1, school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3, allow_repeat_target=False),
        range_ft=120, description="", dice="1d4+1", damage_type=DamageType.FORCE,
    )
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id)), ctx
    )
    assert isinstance(avail, Forbidden)  # дубль при allow_repeat=False
```

- [ ] **Step 2: Прогнать — падает**

Run: `pytest tests/integration/engine/test_cast_spell_multi.py -q`
Expected: FAIL — `CastSpellParams` не имеет `target_ids` (extra="forbid" → ValidationError) и `_resolve_targets` кидает `NotImplementedError`.

- [ ] **Step 3: Реализовать**

(а) В `src/dnd/application/dto/player_intent.py` в `CastSpellIntent` добавить поле (после `target_id`):

```python
    target_id: CreatureId | None = None
    # MULTI (P2b): мультимножество выбранных целей (дубли допустимы, порядок=выборы).
    target_ids: tuple[CreatureId, ...] = ()
    # AoE (P2): точка прицеливания (AT_POINT) или направление (FROM_CASTER).
    target_point: Square | None = None
    direction: Direction | None = None
```

(б) В `cast_spell.py` в `CastSpellParams` добавить аналогично:

```python
    spell_id: SpellId
    target_id: CreatureId | None = None
    target_ids: tuple[CreatureId, ...] = ()
    # AoE (P2): точка прицеливания (AT_POINT) или направление (FROM_CASTER).
    target_point: Square | None = None
    direction: Direction | None = None
```

(в) В `_resolve_targets` заменить хвост `raise NotImplementedError(...)` на:

```python
        # MULTI (P2b): мультимножество выборов — дубли = повторные «попадания».
        # Валидность гарантирует can_perform_against; здесь чистая выборка.
        assert kind is TargetKind.MULTI
        return tuple(ctx.participants[cid] for cid in params.target_ids)
```

(г) В `can_perform_against`, в конце цепочки `if/elif` по `spell.targeting.kind` (после ветки AREA, перед `return Allowed()`), добавить ветку MULTI:

```python
        elif spell.targeting.kind is TargetKind.MULTI:
            spec = spell.targeting
            if not params.target_ids:
                return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
            if len(params.target_ids) > spec.max_targets:
                return Forbidden(
                    reason=ForbiddenReason.CUSTOM,
                    details=f"too many targets (max {spec.max_targets})",
                )
            unique = set(params.target_ids)
            if not spec.allow_repeat_target and len(unique) != len(params.target_ids):
                return Forbidden(
                    reason=ForbiddenReason.CUSTOM,
                    details="repeat targets not allowed",
                )
            actor_pos = ctx.battlefield.position_of(actor.id)
            offensive = spell.effect in (
                SpellEffect.ATTACK, SpellEffect.SAVE, SpellEffect.AUTO
            )
            for cid in unique:
                if cid not in ctx.participants:
                    return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
                target = ctx.participants[cid]
                if offensive:
                    if not target.is_alive:
                        return Forbidden(reason=ForbiddenReason.TARGET_DOWN)
                elif not target.is_alive and not (
                    target.death_saves is not None and not target.death_saves.is_dead
                ):
                    return Forbidden(reason=ForbiddenReason.TARGET_DOWN)
                if actor_pos.distance_to_feet(
                    ctx.battlefield.position_of(cid)
                ) > spell.range_ft:
                    return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
```

- [ ] **Step 4: Прогнать — зелёные**

Run: `pytest tests/integration/engine/test_cast_spell_multi.py -q && mypy src/dnd/application/engine/actions/cast_spell.py src/dnd/application/dto/player_intent.py && ruff check src/dnd/application/engine/actions/cast_spell.py src/dnd/application/dto/player_intent.py tests/integration/engine/test_cast_spell_multi.py`
Expected: PASS, mypy/ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/engine/actions/cast_spell.py src/dnd/application/dto/player_intent.py tests/integration/engine/test_cast_spell_multi.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(p2b-4): MULTI-резолвинг (мультимножество) + target_ids + валидация"
```

---

## Task 5 (P2b-5): Magic Missile → распределяемый MULTI + smoke распределения

**Files:**
- Modify: `data/content/spells.yaml` (`magic_missile`)
- Modify: `tests/integration/engine/test_cast_spell.py` (морально устаревшие MM-тесты)
- Test: `tests/integration/engine/test_cast_spell_multi.py` (smoke распределения)

- [ ] **Step 1: Обновить spells.yaml — Magic Missile**

В `data/content/spells.yaml` заменить блок `magic_missile`:

```yaml
- id: magic_missile
  name: "Magic Missile"
  level: 1
  school: evocation
  effect: auto
  targeting: { kind: multi, max_targets: 3, allow_repeat_target: true }
  range_ft: 120
  dice: "1d4+1"
  damage_type: force
  description: "Три светящихся дротика бьют автоматически (без броска атаки). Каждый — 1d4+1 силового урона; дротики распределяются между целями (можно несколько в одну)."
```

- [ ] **Step 2: Обновить морально устаревшие MM-тесты**

`magic_missile` теперь MULTI (был SINGLE, `3d4+3`). В `tests/integration/engine/test_cast_spell.py` заменить два теста:

```python
def test_magic_missile_auto_damage_consumes_slot() -> None:
    # init x2, 3 дротика по 1d4+1 в одну цель: [4,4,4] → (4+1)*3 = 15 урона.
    enc, mage, gob, ctx = _setup([20, 19, 4, 4, 4])
    mage.spell_slots = {1: 1}
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    out = CastSpellAction(_repo()).execute(
        mage,
        CastSpellParams(
            spell_id=SpellId("magic_missile"),
            target_ids=(gob.id, gob.id, gob.id),
        ),
        ctx,
    )
    assert out.success
    assert sum(d.final_amount for d in dmg) == 15  # 3 дротика × (d4=4 +1)
    assert gob.hit_points.current == 12 - 15 if 12 - 15 > 0 else gob.hit_points.current >= 0
    assert mage.spell_slots == {1: 0}


def test_magic_missile_no_slot_forbidden() -> None:
    _enc, mage, gob, ctx = _setup([20, 19, 4, 4, 4])
    mage.spell_slots = {1: 0}
    avail = CastSpellAction(_repo()).can_perform_against(
        mage,
        CastSpellParams(spell_id=SpellId("magic_missile"), target_ids=(gob.id,)),
        ctx,
    )
    assert isinstance(avail, Forbidden)
```

> Примечание: цель `gob` (12 HP) переживёт не более 12 урона — для чистоты ассерта проверяем сумму `final_amount` событий (они отражают фактический урон, который cap'ится по HP в `take_damage`). Гоблин с 12 HP получит final суммарно ≤ 12. Перепиши ассерт суммы на `raw`-эквивалент: используем поле `raw_amount`.

Уточнённый ассерт суммы (заменяет строку с `final_amount`):

```python
    assert sum(d.raw_amount for d in dmg) == 15  # сырой урон 3 дротиков
    assert len(dmg) == 3                          # три отдельных попадания
```

(убрать предыдущую строку про `gob.hit_points.current == 12 - 15 ...` — она некорректна; оставить только проверку слота и суммы raw + числа событий.)

Итоговый `test_magic_missile_auto_damage_consumes_slot`:

```python
def test_magic_missile_auto_damage_consumes_slot() -> None:
    # init x2, 3 дротика по 1d4+1 в одну цель: d4=[4,4,4] → raw (4+1)*3 = 15.
    enc, mage, gob, ctx = _setup([20, 19, 4, 4, 4])
    mage.spell_slots = {1: 1}
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    out = CastSpellAction(_repo()).execute(
        mage,
        CastSpellParams(
            spell_id=SpellId("magic_missile"),
            target_ids=(gob.id, gob.id, gob.id),
        ),
        ctx,
    )
    assert out.success
    assert len(dmg) == 3                          # три отдельных дротика
    assert sum(d.raw_amount for d in dmg) == 15   # 3 × (d4=4 +1)
    assert mage.spell_slots == {1: 0}
```

- [ ] **Step 3: Написать smoke распределения по двум целям**

В `tests/integration/engine/test_cast_spell_multi.py` добавить:

```python
def test_magic_missile_distributes_across_targets() -> None:
    # 3 дротика 1d4+1: 2 в gobA, 1 в gobB. d4-броски [3,3,2].
    enc, mage, a, b, ctx = _setup([20, 19, 19, 3, 3, 2])
    from dnd.application.dto.engine_event import DamageDealt
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    spell = _mm()
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    out = action.execute(
        mage,
        CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id, b.id)),
        ctx,
    )
    assert out.success
    by_target: dict[CreatureId, int] = {}
    for d in dmg:
        by_target[d.target_id] = by_target.get(d.target_id, 0) + d.raw_amount
    assert by_target[a.id] == (3 + 1) + (3 + 1)   # 2 дротика
    assert by_target[b.id] == (2 + 1)             # 1 дротик
```

- [ ] **Step 4: Прогнать — зелёные**

Run: `pytest tests/integration/engine/test_cast_spell.py tests/integration/engine/test_cast_spell_multi.py -q && ruff check tests/integration/engine/test_cast_spell_multi.py`
Expected: PASS.

> Если упадут другие тесты, использующие `magic_missile` с `target_id` (single) — найди их: `grep -rn "magic_missile" tests/` и обнови на `target_ids=(...)`. Кандидаты: `test_cast_spell_intent.py`, `test_scenario_spells.py`, `test_spell_action_bar.py`. В каждом: заменить `CastSpellParams(... target_id=X)` / интенты с одиночной целью на мультимножество `target_ids=(X,)` ИЛИ переключить тест на другое одиночное заклинание (`fire_bolt`), если суть теста не в MM. Реши по месту, сохраняя смысл теста.

- [ ] **Step 5: Прогнать весь набор — поймать регрессии MM**

Run: `pytest -q`
Expected: PASS. Любые падения из-за смены MM single→multi — починить по принципу из Step 4.

- [ ] **Step 6: Commit**

```bash
git add data/content/spells.yaml tests/integration/engine/
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(p2b-5): Magic Missile → распределяемый MULTI (1d4+1 за дротик)"
```

---

## Task 6 (P2b-6): Bless + сбор модификаторов в спелл-хендлерах (атака/спасбросок)

**Files:**
- Modify: `data/content/spells.yaml` (добавить `bless`)
- Modify: `src/dnd/application/engine/spells/handlers.py` (`AttackSpellHandler`, `SaveSpellHandler`)
- Modify: `tests/integration/content/test_yaml_spell_repository.py` (`test_loads_all_spells` +bless)
- Test: `tests/integration/engine/test_cast_spell_multi.py`

- [ ] **Step 1: Добавить Bless в spells.yaml**

В конец `data/content/spells.yaml` добавить:

```yaml
# --- мультитаргет-бафф (этап P2b) ---
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

- [ ] **Step 2: Обновить test_loads_all_spells (+bless)**

В `tests/integration/content/test_yaml_spell_repository.py` в `test_loads_all_spells` добавить `SpellId("bless")` в ожидаемый set:

```python
    assert ids == {
        SpellId("fire_bolt"), SpellId("sacred_flame"), SpellId("magic_missile"),
        SpellId("cure_wounds"), SpellId("shield_of_faith"),
        SpellId("fireball"), SpellId("burning_hands"), SpellId("lightning_bolt"),
        SpellId("bless"),
    }
```

- [ ] **Step 3: Написать падающий тест «Bless +1d4 к спасброску»**

В `tests/integration/engine/test_cast_spell_multi.py` добавить (Bless'нутая цель кидает спелл-сейв с extra-кубом):

```python
def test_bless_adds_d4_to_spell_save() -> None:
    """Bless на цели → её спасбросок от спелла включает +1d4 (extra_dice)."""
    from dnd.application.engine.spells.handlers import BuffSpellHandler, SaveSpellHandler
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.spell import BuffSpec
    # init x2, далее SaveSpellHandler: урон d8 + спасбросок d20 + bless d4.
    # rolls: [20,19] init; затем урон=5(d8), save d20=10, bless-куб d4=4.
    enc, mage, a, _b, ctx = _setup([20, 19, 19, 5, 10, 4])
    bless = Spell(
        id=SpellId("bless"), name="Bless", level=1, school="enchantment",
        effect=SpellEffect.BUFF,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3),
        range_ft=30, description="", concentration=True,
        buffs=(BuffSpec(target=ModifierTargetKind.SAVING_THROW, dice_bonus="1d4"),),
    )
    BuffSpellHandler().apply(mage, (a,), bless, ctx)
    # SAVING_THROW-модификатор на a зарегистрирован:
    mods = ctx.modifier_applier.collect(
        owner_id=a.id, target_kind=ModifierTargetKind.SAVING_THROW
    )
    assert ctx.modifier_applier.to_roll_adjustments(mods).extra_dice == ("1d4",)
    # Теперь a кидает спелл-сейв против урон-заклинания — extra_dice должны учесться.
    save_spell = Spell(
        id=SpellId("sf"), name="SF", level=0, school="evocation",
        effect=SpellEffect.SAVE, targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=60, description="", dice="1d8", damage_type=DamageType.RADIANT,
        save_ability=Ability.DEX, save_for_half=False,
    )
    captured: list[object] = []
    orig_roll = ctx.dice_roller.roll
    def _spy(expr: object, rc: object) -> object:
        captured.append(rc)
        return orig_roll(expr, rc)  # type: ignore[arg-type]
    ctx.dice_roller.roll = _spy  # type: ignore[method-assign]
    SaveSpellHandler().apply(mage, (a,), save_spell, ctx)
    # среди RollContext'ов должен быть SAVE с extra_dice=("1d4",)
    from dnd.domain.values.roll_purpose import RollPurpose
    save_ctxs = [rc for rc in captured if getattr(rc, "purpose", None) is RollPurpose.SAVE]
    assert save_ctxs and save_ctxs[0].extra_dice == ("1d4",)
```

- [ ] **Step 4: Прогнать — падает**

Run: `pytest "tests/integration/engine/test_cast_spell_multi.py::test_bless_adds_d4_to_spell_save" -q`
Expected: FAIL — `SaveSpellHandler` строит `RollContext(purpose=SAVE, ...)` без `extra_dice` (модификаторы не собираются).

- [ ] **Step 5: Реализовать сбор модификаторов в спелл-хендлерах**

В `handlers.py`:

(а) `SaveSpellHandler.apply` — перед броском спасброска собрать `SAVING_THROW`-модификаторы цели и прокинуть. Заменить блок `save_roll = ...`:

```python
            save_mod = target.abilities.modifier(spell.save_ability)
            save_mods = ctx.modifier_applier.collect(
                owner_id=target.id, target_kind=ModifierTargetKind.SAVING_THROW
            )
            save_adj = ctx.modifier_applier.to_roll_adjustments(save_mods)
            save_roll = ctx.dice_roller.roll(
                DiceExpr.parse(f"d20{save_mod + save_adj.numeric_bonus:+d}"),
                RollContext(
                    purpose=RollPurpose.SAVE,
                    actor_id=target.id,
                    advantage=save_adj.advantage,
                    disadvantage=save_adj.disadvantage,
                    extra_dice=save_adj.extra_dice,
                    tags=("spell_save",),
                ),
            )
```

(б) `AttackSpellHandler.apply` — перед броском спелл-атаки собрать `ATTACK_ROLL`-модификаторы кастера. Заменить блок `roll = ...`:

```python
            atk_bonus = caster.spell_attack_bonus()
            atk_mods = ctx.modifier_applier.collect(
                owner_id=caster.id, target_kind=ModifierTargetKind.ATTACK_ROLL
            )
            atk_adj = ctx.modifier_applier.to_roll_adjustments(atk_mods)
            roll = ctx.dice_roller.roll(
                DiceExpr.parse(f"d20{atk_bonus + atk_adj.numeric_bonus:+d}"),
                RollContext(
                    purpose=RollPurpose.ATTACK,
                    actor_id=caster.id,
                    target_id=target.id,
                    advantage=atk_adj.advantage,
                    disadvantage=atk_adj.disadvantage,
                    extra_dice=atk_adj.extra_dice,
                    tags=("spell_attack",),
                ),
            )
```

(`ModifierTargetKind` уже импортирован в Task 3.)

- [ ] **Step 6: Прогнать — зелёные**

Run: `pytest tests/integration/engine/test_cast_spell_multi.py tests/integration/engine/test_cast_spell.py tests/integration/content/test_yaml_spell_repository.py -q && mypy src/dnd/application/engine/spells/handlers.py && ruff check src/dnd/application/engine/spells/handlers.py tests/integration/engine/test_cast_spell_multi.py`
Expected: PASS, mypy/ruff чисто.

- [ ] **Step 7: Прогнать весь набор**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add data/content/spells.yaml src/dnd/application/engine/spells/handlers.py tests/integration/
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(p2b-6): Bless + спелл-хендлеры собирают ATTACK_ROLL/SAVING_THROW модификаторы"
```

---

## Task 7 (P2b-7): TUI — BattleMode.MULTI_TARGET + handler + wiring

**Files:**
- Modify: `src/dnd/interfaces/tui/screens/battle_modes/protocol.py`
- Create: `src/dnd/interfaces/tui/screens/battle_modes/multi_target_mode.py`
- Modify: `src/dnd/interfaces/tui/screens/battle.py`
- Test: `tests/integration/tui/test_multi_target_mode.py` (создать)

- [ ] **Step 1: Добавить enum + контекст-поля в protocol.py**

В `protocol.py`:

(а) в `BattleMode` добавить:

```python
class BattleMode(Enum):
    NORMAL = "normal"
    MOVE = "move"
    TARGET = "target"
    AREA = "area"   # выбор зоны AoE-заклинания (P2)
    MULTI_TARGET = "multi_target"   # выбор нескольких целей (P2b)
```

(б) в `ModeScreenContext` (после блока AREA) добавить:

```python
    # MULTI_TARGET mode (P2b): лимит выборов и разрешены ли повторы.
    _multi_max_targets: int
    _multi_allow_repeat: bool
```

- [ ] **Step 2: Написать падающие unit-тесты handler'а**

Создать `tests/integration/tui/test_multi_target_mode.py`:

```python
"""P2b-7: MultiTargetModeHandler — выбор мультимножества целей с клавиатуры."""
from __future__ import annotations

from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.multi_target_mode import (
    MultiTargetModeHandler,
)


class _Screen:
    """Минимальный мок ModeScreenContext для MULTI_TARGET."""
    def __init__(self, max_targets: int, allow_repeat: bool) -> None:
        self._current_actor_position = Square(2, 2)
        self._reachable_targets = [
            (CreatureId("A"), Square(3, 2)),
            (CreatureId("B"), Square(4, 2)),
        ]
        self._participants = {}  # type: ignore[var-annotated]
        self._multi_max_targets = max_targets
        self._multi_allow_repeat = allow_repeat


def test_pick_three_distinct_no_repeat() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=2, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "space")          # add A (cursor at idx0)
    h.on_key(screen, "tab")            # cursor → B
    h.on_key(screen, "space")          # add B
    h.on_key(screen, "enter")          # confirm
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("B"))


def test_no_repeat_ignores_duplicate() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "space")          # add A
    h.on_key(screen, "space")          # повтор A игнорируется (no-repeat)
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"),)


def test_repeat_allows_same_target_twice() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A снова (repeat ok)
    h.on_key(screen, "tab")
    h.on_key(screen, "space")          # B
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("A"), CreatureId("B"))


def test_max_targets_caps_picks() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=2, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # сверх лимита → игнор
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("A"))


def test_backspace_removes_last_pick() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    h.on_key(screen, "backspace")      # снять последнее A
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"),)


def test_enter_with_no_picks_does_not_confirm() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "enter")
    assert h.confirmed_picks is None


def test_escape_cancels() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "escape")
    assert h.cancelled is True


def test_overlay_shows_counts() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    data = h.overlay()
    assert "осталось" in data.hint.lower() or "выбери" in data.hint.lower()
    # выбранная клетка A подсвечена
    assert screen._reachable_targets[0][1] in data.highlights
```

- [ ] **Step 3: Прогнать — падает**

Run: `pytest tests/integration/tui/test_multi_target_mode.py -q`
Expected: FAIL — модуль `multi_target_mode` не существует.

- [ ] **Step 4: Реализовать MultiTargetModeHandler**

Создать `src/dnd/interfaces/tui/screens/battle_modes/multi_target_mode.py`:

```python
"""MultiTargetModeHandler — inline MULTI_TARGET mode (этап P2b).

Выбор нескольких целей заклинания как **мультимножество**: Tab/Shift+Tab
циклят кандидатов, Space добавляет одно «попадание» текущей цели (повтор —
повторным Space, если spell разрешает повторы), Backspace снимает последнее,
Enter подтверждает набор, Esc отменяет. Никакого ввода чисел — повторы
задаются повторным выбором; на экране счётчик попаданий ✦×N и остаток.
"""
from __future__ import annotations

from collections import Counter

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.protocol import (
    ModeScreenContext,
    OverlayData,
)


class MultiTargetModeHandler:
    def __init__(self) -> None:
        self._targets: list[tuple[CreatureId, Square]] = []
        self._idx: int = 0
        self._actor_pos: Square = Square(0, 0)
        self._participants: dict[CreatureId, Creature] = {}
        self._max: int = 1
        self._allow_repeat: bool = False
        self._picks: list[CreatureId] = []
        self.confirmed_picks: tuple[CreatureId, ...] | None = None
        self.cancelled: bool = False

    def on_enter(self, screen: ModeScreenContext) -> None:
        self._targets = list(screen._reachable_targets)
        self._actor_pos = screen._current_actor_position
        self._participants = screen._participants
        self._max = screen._multi_max_targets
        self._allow_repeat = screen._multi_allow_repeat
        self._idx = 0
        self._picks = []
        self.confirmed_picks = None
        self.cancelled = False

    def on_exit(self, screen: ModeScreenContext) -> None:
        self._targets = []
        self._participants = {}
        self._picks = []

    def on_key(self, screen: ModeScreenContext, key: str) -> bool:
        if not self._targets:
            return False
        if key == "tab":
            self._idx = (self._idx + 1) % len(self._targets)
            return True
        if key == "shift+tab":
            self._idx = (self._idx - 1) % len(self._targets)
            return True
        if key == "space":
            self._add_current()
            return True
        if key == "backspace":
            if self._picks:
                self._picks.pop()
            return True
        if key == "enter":
            if self._picks:
                self.confirmed_picks = tuple(self._picks)
            return True
        if key == "escape":
            self.cancelled = True
            return True
        return False

    def _add_current(self) -> None:
        if len(self._picks) >= self._max:
            return
        cid = self._targets[self._idx][0]
        if not self._allow_repeat and cid in self._picks:
            return
        self._picks.append(cid)

    def overlay(self) -> OverlayData:
        if not self._targets:
            return OverlayData()
        counts = Counter(self._picks)
        highlights: dict[Square, str] = {}
        for i, (cid, sq) in enumerate(self._targets):
            if i == self._idx:
                highlights[sq] = "reverse bold"
            elif cid in counts:
                highlights[sq] = "green bold"
            else:
                highlights[sq] = "bold"
        cur_id, cur_sq = self._targets[self._idx]
        picked_str = ", ".join(
            f"{cid} {'✦' * counts[cid]}" for cid in counts
        ) or "—"
        remaining = self._max - len(self._picks)
        hint = (
            f"MULTI: [{picked_str}] — выбери ещё {remaining} (макс {self._max}) · "
            f"Tab цель · Space добавить · Bksp снять · Enter каст · Esc отмена · "
            f"осталось {remaining}"
        )
        return OverlayData(cursor=cur_sq, highlights=highlights, hint=hint)


__all__ = ["MultiTargetModeHandler"]
```

- [ ] **Step 5: Прогнать unit-тесты handler'а — зелёные**

Run: `pytest tests/integration/tui/test_multi_target_mode.py -q && mypy src/dnd/interfaces/tui/screens/battle_modes/multi_target_mode.py && ruff check src/dnd/interfaces/tui/screens/battle_modes/multi_target_mode.py tests/integration/tui/test_multi_target_mode.py`
Expected: PASS, mypy/ruff чисто.

- [ ] **Step 6: Commit (handler отдельно)**

```bash
git add src/dnd/interfaces/tui/screens/battle_modes/protocol.py src/dnd/interfaces/tui/screens/battle_modes/multi_target_mode.py tests/integration/tui/test_multi_target_mode.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(p2b-7a): MultiTargetModeHandler + BattleMode.MULTI_TARGET"
```

- [ ] **Step 7: Wiring в battle.py — поля контекста + enter_mode + on_key + submit + trigger**

В `src/dnd/interfaces/tui/screens/battle.py`:

(а) импорт handler'а (рядом с другими battle_modes-импортами, ~строка 75-79):

```python
from dnd.interfaces.tui.screens.battle_modes.multi_target_mode import (
    MultiTargetModeHandler,
)
```

(б) в `__init__` рядом с `_pending_area_*` (~строка 195) добавить поля контекста MULTI:

```python
        # Контекст для MultiTargetModeHandler: лимит выборов и повторы.
        self._multi_max_targets: int = 1
        self._multi_allow_repeat: bool = False
```

(в) в `enter_mode` (~строка 344) добавить ветку:

```python
        elif mode is BattleMode.AREA:
            self._mode_handler = AreaModeHandler()
        elif mode is BattleMode.MULTI_TARGET:
            self._mode_handler = MultiTargetModeHandler()
```

(г) в строке отрисовки cursor (~строка 371) включить MULTI_TARGET туда же, где TARGET/AREA:

```python
        if self._mode in (
            BattleMode.TARGET, BattleMode.AREA, BattleMode.MULTI_TARGET
        ) and data.cursor is not None:
```

(д) в `on_key` добавить ветку обработки (после блока `elif isinstance(h, AreaModeHandler):`, ~строка 453):

```python
        elif isinstance(h, MultiTargetModeHandler):
            if h.cancelled:
                self._pending_ability = None
                self.enter_mode(BattleMode.NORMAL)
                return
            if h.confirmed_picks is not None:
                self._submit_multi_intent(h.confirmed_picks)
                self.enter_mode(BattleMode.NORMAL)
                return
```

(е) добавить метод `_submit_multi_intent` (рядом с `_submit_area_intent`, ~строка 472):

```python
    def _submit_multi_intent(self, picks: tuple[CreatureId, ...]) -> None:
        """Построить CastSpellIntent для подтверждённого набора целей (P2b)."""
        ab = self._pending_ability
        spell = self._spell_by_ability.get(ab.id) if ab is not None else None
        self._pending_ability = None
        if spell is None:
            return
        self._put_intent(
            CastSpellIntent(spell_id=spell.id, target_ids=picks)
        )
```

(ж) добавить helper-листер кандидатов для MULTI (рядом с `_list_spell_targets`, ~строка 541). Он НЕ зовёт `can_perform_against` (та для MULTI требует уже собранный target_ids), а фильтрует по фракции/дальности/жизни напрямую:

```python
    def _list_multi_candidates(
        self,
        actor: Creature,
        encounter: Encounter,
        spell: Spell,
    ) -> list[CreatureId]:
        """Кандидаты для MULTI-заклинания: враги для урона (ATTACK/SAVE/AUTO),
        союзники+сам для heal/buff. Фильтр по дальности и жизни напрямую
        (per-target can_perform_against для MULTI не применим — он работает с
        целым target_ids)."""
        offensive = spell.effect in (
            SpellEffect.ATTACK, SpellEffect.SAVE, SpellEffect.AUTO
        )
        actor_faction = encounter.factions.get(actor.id)
        bf = encounter.battlefield
        actor_pos = bf.position_of(actor.id)
        result: list[CreatureId] = []
        for cid, cr in encounter.participants.items():
            if not cr.is_alive:
                continue
            other_faction = encounter.factions.get(cid)
            if offensive:
                if cid == actor.id or other_faction == actor_faction:
                    continue
                if other_faction is Faction.NEUTRAL:
                    continue
            elif other_faction != actor_faction:
                continue
            if actor_pos.distance_to_feet(bf.position_of(cid)) > spell.range_ft:
                continue
            result.append(cid)
        return result
```

(з) в `_trigger_ability` добавить ветку MULTI ПЕРЕД блоком AREA (т.е. сразу после получения `area_spell`/перед `if area_spell ... AREA`). Точнее — после строки `area_spell = self._spell_by_ability.get(ab.id)`:

```python
        area_spell = self._spell_by_ability.get(ab.id)
        if area_spell is not None and area_spell.targeting.kind is TargetKind.MULTI:
            candidates = self._list_multi_candidates(actor, encounter, area_spell)
            if not candidates:
                self.log_widget.write(
                    f"[bold]No targets in reach for {area_spell.name}.[/]"
                )
                return
            bf = encounter.battlefield
            self._current_battlefield = bf
            self._reachable_targets = [(cid, bf.position_of(cid)) for cid in candidates]
            self._multi_max_targets = area_spell.targeting.max_targets
            self._multi_allow_repeat = area_spell.targeting.allow_repeat_target
            self._pending_ability = ab
            self.enter_mode(BattleMode.MULTI_TARGET)
            return
        if area_spell is not None and area_spell.targeting.kind is TargetKind.AREA:
            ...  # существующий блок AREA без изменений
```

- [ ] **Step 8: Написать pilot-тест полного цикла (TUI)**

В `tests/integration/tui/test_multi_target_mode.py` добавить pilot-тест по образцу существующих TUI-тестов. Сначала посмотреть паттерн запуска приложения:

Run: `sed -n '1,60p' tests/integration/tui/test_spell_action_bar.py`

Затем добавить тест, который: запускает BattleScreen с магом, знающим `magic_missile` (MULTI allow_repeat), жмёт hotkey заклинания → режим MULTI_TARGET → Space, Space (или Tab+Space) → Enter → проверяет, что в очередь интентов положен `CastSpellIntent` с `target_ids` длины 2-3. Использовать существующий harness (`async with app.run_test() as pilot:` + `await pilot.press(...)`). Конкретные id хоткея и способ инспекции очереди интентов взять из `test_spell_action_bar.py` (там уже есть рабочий каркас для заклинаний в TUI).

Шаблон (адаптировать под фактический harness из test_spell_action_bar.py):

```python
import pytest


@pytest.mark.asyncio
async def test_multi_target_pilot_distributes() -> None:
    # harness: построить app c магом (known_spells=[magic_missile]) и 2 врагами
    # в range; запустить, нажать hotkey заклинания, выбрать цели, подтвердить.
    # Затем проверить, что положенный CastSpellIntent имеет target_ids длиной >= 2.
    ...
```

> Реализатору: если устойчивый pilot-harness для заклинаний громоздок, ограничься надёжной проверкой через прямой вызов `_trigger_ability` + симуляцию `on_key` на собранном BattleScreen (как делают unit-тесты выше) ИЛИ полноценным pilot — на твоё усмотрение, но цикл «hotkey → MULTI_TARGET → выбор → Enter → CastSpellIntent.target_ids» должен быть покрыт интеграционно. Не оставляй `...`-заглушку в финальном коде.

- [ ] **Step 9: Прогнать TUI + весь набор**

Run: `pytest tests/integration/tui/test_multi_target_mode.py -q`
Expected: PASS.

Run: `pytest -q && mypy src && ruff check src tests`
Expected: PASS, mypy strict чисто, ruff чисто.

- [ ] **Step 10: Commit**

```bash
git add src/dnd/interfaces/tui/screens/battle.py tests/integration/tui/test_multi_target_mode.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(p2b-7b): wiring MULTI_TARGET в BattleScreen (_submit_multi_intent + кандидаты)"
```

---

## Task 8 (P2b-8): Документация + ROADMAP + финальный аудит

**Files:**
- Modify: `docs/SPELLS.md`, `docs/TUI.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Прочитать текущие доки**

Run: `sed -n '1,40p' docs/SPELLS.md; echo ===; grep -n "MULTI\|мультитаргет\|P2b\|AREA\|BattleMode" docs/TUI.md docs/ROADMAP.md`

- [ ] **Step 2: Обновить SPELLS.md**

Добавить раздел про мультитаргет (формат на основе фактической структуры файла):
- модель целей MULTI = мультимножество `target_ids` (дубли = повторные попадания);
- поля `targeting.max_targets`, `targeting.allow_repeat_target`;
- обобщённый бафф: `buffs: [{ target, numeric_bonus | dice_bonus }]` (заменил `ac_bonus`);
- примеры: Bless (multi, no-repeat, +1d4 attack/save, концентрация), Magic Missile (multi, allow_repeat, 1d4+1 за дротик — распределение);
- как Bless влияет на броски (через ModifierApplier: weapon-атаки + спелл-атаки/спасброски).

- [ ] **Step 3: Обновить TUI.md**

Добавить описание `BattleMode.MULTI_TARGET`: Tab/Shift+Tab цикл, Space добавить попадание (повтор = повторный Space), Backspace снять, Enter каст, Esc отмена; счётчик ✦×N + остаток; повторы — выбором, не вводом чисел.

- [ ] **Step 4: Обновить ROADMAP.md**

Отметить P2b выполненным; кратко перечислить доставленное (MULTI targeting, обобщённый buff, Bless, распределяемый Magic Missile, TUI MULTI_TARGET). Отметить отложенное (если есть): upcasting Bless/MM, реакция-каст.

- [ ] **Step 5: Прогнать весь набор (sanity после доков — изменений кода нет)**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/SPELLS.md docs/TUI.md docs/ROADMAP.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "docs(p2b): мультитаргет, обобщённый buff, MULTI_TARGET в SPELLS/TUI/ROADMAP"
```

- [ ] **Step 7: Финальный независимый аудит**

Запустить независимый аудит-субагент (general-purpose) на дельту этапа P2b. Дать ему: список коммитов P2b (`git log --oneline` от первого P2b-коммита), спек `docs/superpowers/specs/2026-05-25-p2b-multitarget-design.md`, и попросить классифицировать находки CRITICAL/MAJOR/MINOR/NIT. Особое внимание:
- корректность распределения урона Magic Missile (дубли в `target_ids`);
- liveness/range-валидация MULTI в `can_perform_against` (нет ли обхода через `execute`);
- что concentration-логика Bless не сломала per-caster source (срыв при падении кастера);
- что Bless реально применяет +1d4 (extra_dice доходит до DiceRoller) на всех релевантных бросках;
- что миграция `ac_bonus`→`buffs` не оставила «мёртвых» ссылок (`grep -rn ac_bonus src tests`).

Проверить результаты аудита самостоятельно (не доверять summary вслепую), применить фиксы CRITICAL/MAJOR, MINOR — по решению. Каждый фикс — отдельный коммит `fix(p2b-audit): ...`.

---

## Self-Review (выполнено при написании плана)

**1. Покрытие спека:**
- §3.1 allow_repeat_target → Task 1 ✓
- §3.2 BuffSpec → Task 1 ✓
- §3.3 Spell.buffs (удаление ac_bonus) → Task 1 ✓
- §3.4 YAML парсинг → Task 2 ✓
- §4.1 target_ids в params/intent → Task 4 ✓
- §4.2 _resolve_targets MULTI → Task 4 ✓
- §4.3 can_perform_against MULTI → Task 4 ✓
- §5.1 BuffSpellHandler обобщение → Task 3 ✓
- §5.2 сбор модификаторов в спелл-хендлерах → Task 6 ✓
- §6.1 Bless → Task 6 ✓; §6.2 Shield миграция → Task 2 ✓; §6.3 Magic Missile → Task 5 ✓
- §7 TUI MULTI_TARGET → Task 7 ✓
- §8 тесты → распределены по задачам ✓
- §10 инварианты → покрыты тестами Task 1/4/5/6/7 ✓

**2. Placeholder-скан:** единственный `...` — в Step 8 Task 7 (pilot-шаблон) с явной инструкцией «не оставляй заглушку»; это осознанная развилка реализатора (полный pilot vs прямой вызов), а не недосказанность остального плана. Все code-шаги — полные.

**3. Консистентность типов:** `BuffSpec(target, numeric_bonus, dice_bonus)`, `TargetingSpec.allow_repeat_target`, `Spell.buffs`, `CastSpellParams.target_ids`/`CastSpellIntent.target_ids`, `MultiTargetModeHandler.confirmed_picks: tuple[CreatureId,...]`, `_multi_max_targets`/`_multi_allow_repeat`, `_submit_multi_intent`, `_list_multi_candidates` — имена единообразны во всех задачах. `ModifierTargetKind` значения (`armor_class`, `attack_roll`, `saving_throw`) совпадают с domain enum.

**Замечание реализатору:** порядок ScriptedRNG-бросков в тестах (`_setup([...])`) — первые два значения это инициатива (20,19). При 3 участниках в `test_cast_spell_multi` может потребоваться третье init-значение (19) — учтено в фикстуре `_setup` (rolls начинаются с трёх init). Если число бросков не сойдётся, скорректируй хвост списка по фактическим запросам DiceRoller (это нормальная отладка ScriptedRNG, не дефект плана).
