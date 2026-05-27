# V — навыки и проверки характеристик Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Навыки (18) и проверки характеристик: data-driven `Skill` + служба `roll_ability_check` (зеркало спасбросков), пассивные значения; затем боевые проверки на состязаниях — Shove/Grapple/Hide.

**Architecture:** Навык — данные (`Skill` StrEnum + `SKILL_ABILITY` mapping). Служба `ability_check.py` зеркалит `saving_throw.py` (d20 + бонус + adjustments; помехи/преимущество от состояний через `ConditionService.collect_modifiers(ABILITY_CHECK)`). Состязания — общий `opposed_check`. Боевые действия (Shove/Grapple/Hide) — `Action`+`Intent` поверх проверок; Grappled/Hidden — состояния через `ConditionService`.

**Tech Stack:** Python 3.12, frozen dataclasses (domain), pydantic v2, pytest, mypy strict, ruff. Guard `tests/unit/test_layering.py`. Коммиты: `Maxim Lokotkov` / `anticrab@users.noreply.github.com`. Доки/комментарии — русский.

**CI-гейты (гонять ВСЕ после каждого task):** `python3 -m ruff check src tests` · `python3 -m ruff format --check src tests` · `python3 -m mypy src` (нужны стабы: `pip install --break-system-packages ".[dev]"`, иначе `import yaml`-ignore'ы дадут ложный результат) · `python3 -m pytest -q`. После `ruff format` — перепроверять mypy (перенос строки сдвигает `# type: ignore`).

---

## Карта файлов

| Файл | Изменение |
|------|-----------|
| `src/dnd/domain/values/skill.py` | **Create** — `Skill` + `SKILL_ABILITY` |
| `src/dnd/domain/entities/creature.py` | поля `skill_proficiencies`/`skill_expertise` |
| `src/dnd/application/engine/ability_check.py` | **Create** — `skill_bonus`/`ability_check_bonus`/`roll_ability_check[_raw]`/`passive_score`/`opposed_check` |
| `src/dnd/application/dto/templates.py` | `MonsterTemplate.skill_proficiencies/skill_expertise` |
| `src/dnd/domain/values/class_progression.py` | опц. `skill_proficiencies` |
| `src/dnd/infrastructure/content/yaml_class_repository.py` | парс `skill_proficiencies` |
| `src/dnd/application/engine/builder.py` | проводка навыков из template/класса |
| `data/content/monsters.yaml`, `classes.yaml` | демо-навыки |
| `src/dnd/domain/conditions/builtin.py` | `GrappledCondition`, `HiddenCondition`, `_self_advantage` |
| `src/dnd/application/engine/actions/move.py` | guard speed-0 при Grappled |
| `src/dnd/application/engine/actions/skill_actions.py` | **Create** — Shove/Grapple/Hide |
| `src/dnd/application/dto/player_intent.py` | `ShoveIntent`/`GrappleIntent`/`HideIntent` |
| `src/dnd/application/engine/game_runner.py` | dispatch новых intent'ов |
| `src/dnd/application/engine/actions/attack.py` | снятие Hidden после атаки |
| `docs/SKILLS.md`, `docs/CONDITIONS.md`, `docs/ROADMAP.md` | доки |

Все новые поля Creature/Template — с дефолтами (backward-compat). `Skill`/
`SKILL_ABILITY` — данные в domain (слой не нарушается).

---

# V1 — фундамент: навыки, проверки, пассивные

## Task V1-1: `Skill` + `SKILL_ABILITY`

**Files:** Create `src/dnd/domain/values/skill.py`; Test `tests/unit/domain/test_skill.py`.

- [ ] **Step 1: Падающий тест**

```python
"""Skill — 18 навыков + маппинг на характеристику (V1)."""
from __future__ import annotations

from dnd.domain.values.ability import Ability
from dnd.domain.values.skill import SKILL_ABILITY, Skill


def test_all_skills_have_ability() -> None:
    # У каждого навыка есть управляющая характеристика.
    assert set(SKILL_ABILITY) == set(Skill)
    assert all(v in Ability for v in SKILL_ABILITY.values())


def test_known_mappings() -> None:
    assert SKILL_ABILITY[Skill.ATHLETICS] is Ability.STR
    assert SKILL_ABILITY[Skill.STEALTH] is Ability.DEX
    assert SKILL_ABILITY[Skill.PERCEPTION] is Ability.WIS
    assert SKILL_ABILITY[Skill.PERSUASION] is Ability.CHA
    assert SKILL_ABILITY[Skill.ARCANA] is Ability.INT


def test_eighteen_skills() -> None:
    assert len(Skill) == 18
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/domain/test_skill.py -q` → FAIL (нет модуля).

- [ ] **Step 3: Реализовать**

Create `src/dnd/domain/values/skill.py`:
```python
"""Навыки D&D 5e (PHB-2024) — данные: навык → управляющая характеристика.

Навык — закрытый список из книги. Расширение/хоумрул = новый член enum +
строка в SKILL_ABILITY. Никаких switch по навыкам в коде — потребители
(ability_check) спрашивают этот маппинг.
"""
from __future__ import annotations

from enum import StrEnum

from dnd.domain.values.ability import Ability


class Skill(StrEnum):
    ACROBATICS = "acrobatics"
    ANIMAL_HANDLING = "animal_handling"
    ARCANA = "arcana"
    ATHLETICS = "athletics"
    DECEPTION = "deception"
    HISTORY = "history"
    INSIGHT = "insight"
    INTIMIDATION = "intimidation"
    INVESTIGATION = "investigation"
    MEDICINE = "medicine"
    NATURE = "nature"
    PERCEPTION = "perception"
    PERFORMANCE = "performance"
    PERSUASION = "persuasion"
    RELIGION = "religion"
    SLEIGHT_OF_HAND = "sleight_of_hand"
    STEALTH = "stealth"
    SURVIVAL = "survival"


SKILL_ABILITY: dict[Skill, Ability] = {
    Skill.ACROBATICS: Ability.DEX,
    Skill.ANIMAL_HANDLING: Ability.WIS,
    Skill.ARCANA: Ability.INT,
    Skill.ATHLETICS: Ability.STR,
    Skill.DECEPTION: Ability.CHA,
    Skill.HISTORY: Ability.INT,
    Skill.INSIGHT: Ability.WIS,
    Skill.INTIMIDATION: Ability.CHA,
    Skill.INVESTIGATION: Ability.INT,
    Skill.MEDICINE: Ability.WIS,
    Skill.NATURE: Ability.INT,
    Skill.PERCEPTION: Ability.WIS,
    Skill.PERFORMANCE: Ability.CHA,
    Skill.PERSUASION: Ability.CHA,
    Skill.RELIGION: Ability.INT,
    Skill.SLEIGHT_OF_HAND: Ability.DEX,
    Skill.STEALTH: Ability.DEX,
    Skill.SURVIVAL: Ability.WIS,
}

__all__ = ["SKILL_ABILITY", "Skill"]
```

- [ ] **Step 4: Зелёно + коммит**

Run: `python3 -m pytest tests/unit/domain/test_skill.py -q` → PASS.
```bash
git add src/dnd/domain/values/skill.py tests/unit/domain/test_skill.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v1): Skill (18 навыков) + SKILL_ABILITY (данные)"
```

## Task V1-2: поля Creature + `skill_bonus`/`ability_check_bonus`

**Files:** Modify `creature.py`; Create `ability_check.py`; Test `tests/unit/application/test_ability_check.py`.

- [ ] **Step 1: Падающий тест**

```python
"""skill_bonus / ability_check_bonus (V1)."""
from __future__ import annotations

from dnd.application.engine.ability_check import ability_check_bonus, skill_bonus
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.skill import Skill


def _c() -> Creature:
    return Creature.create(
        id_=CreatureId("c"), name="c",
        abilities=AbilityScores.of(str_=16, dex=14, con=12, int_=10, wis=10, cha=8),
        max_hp=10, armor_class=12, speed_ft=30, proficiency_bonus=2,
    )


def test_skill_bonus_plain_is_ability_mod() -> None:
    # Атлетика (STR 16 → +3), без владения = только модификатор.
    assert skill_bonus(_c(), Skill.ATHLETICS) == 3


def test_skill_bonus_proficient_adds_prof() -> None:
    c = _c()
    c.skill_proficiencies = frozenset({Skill.ATHLETICS})
    assert skill_bonus(c, Skill.ATHLETICS) == 3 + 2  # +prof


def test_skill_bonus_expertise_doubles_prof() -> None:
    c = _c()
    c.skill_proficiencies = frozenset({Skill.ATHLETICS})
    c.skill_expertise = frozenset({Skill.ATHLETICS})
    assert skill_bonus(c, Skill.ATHLETICS) == 3 + 2 * 2  # +2×prof


def test_ability_check_bonus_raw() -> None:
    # Голая проверка Силы — только модификатор (без навыка/владения).
    assert ability_check_bonus(_c(), Ability.STR) == 3
```

- [ ] **Step 2: Запустить — падает** (`ImportError`).

- [ ] **Step 3: Поля Creature**

В `creature.py` рядом с `saving_throw_proficiencies` добавить (импорт `Skill`
из `dnd.domain.values.skill` в шапку):
```python
    skill_proficiencies: frozenset[Skill] = field(default_factory=frozenset)
    """Навыки с владением (+ proficiency_bonus). Пусто у обычных монстров."""
    skill_expertise: frozenset[Skill] = field(default_factory=frozenset)
    """Навыки с Экспертизой (× 2 proficiency_bonus, Плут/Бард). Только поверх
    владения."""
```

- [ ] **Step 4: Создать `ability_check.py` (часть 1)**

Create `src/dnd/application/engine/ability_check.py`:
```python
"""Проверки характеристик и навыков (V) — зеркало saving_throw.py.

Бонус навыка: модификатор управляющей характеристики (+ proficiency_bonus при
владении, ещё + proficiency_bonus при Экспертизе). Проверка — d20 + бонус +
adjustments (модификаторы/помехи от состояний через ConditionService).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.modifiers import ModifierTargetKind
from dnd.domain.values.skill import SKILL_ABILITY

if TYPE_CHECKING:
    from dnd.application.engine.condition_service import ConditionService
    from dnd.application.engine.modifier_applier import ModifierApplier
    from dnd.application.engine.turn_context import TurnContext
    from dnd.application.ports.dice_roller import DiceRoller
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability
    from dnd.domain.values.skill import Skill


def ability_check_bonus(actor: Creature, ability: Ability) -> int:
    """Бонус голой проверки характеристики — только модификатор (без навыка)."""
    return actor.abilities.modifier(ability)


def skill_bonus(actor: Creature, skill: Skill) -> int:
    """Бонус проверки навыка: mod (+prof если владеет) (+prof если Экспертиза)."""
    bonus = actor.abilities.modifier(SKILL_ABILITY[skill])
    if skill in actor.skill_proficiencies:
        bonus += actor.proficiency_bonus
    if skill in actor.skill_expertise:
        bonus += actor.proficiency_bonus
    return bonus


__all__ = ["ability_check_bonus", "skill_bonus"]
```

- [ ] **Step 5: Зелёно + коммит**

Run: `python3 -m pytest tests/unit/application/test_ability_check.py -q && python3 -m mypy src` → PASS.
```bash
git add src/dnd/domain/entities/creature.py src/dnd/application/engine/ability_check.py tests/unit/application/test_ability_check.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v1): Creature.skill_proficiencies/expertise + skill_bonus/ability_check_bonus"
```

## Task V1-3: `roll_ability_check[_raw]`

**Files:** Modify `ability_check.py`; Test (дописать) `test_ability_check.py`.

- [ ] **Step 1: Падающий тест** (дописать)

```python
def test_roll_ability_check_dc() -> None:
    from dnd.application.engine.ability_check import roll_ability_check_raw
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.entities.battlefield import Battlefield

    deps, _b, _ = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=[10])
    c = _c()  # Атлетика +3 (STR16)
    c.skill_proficiencies = frozenset({Skill.ATHLETICS})  # +2 → итог +5
    # d20=10 + 5 = 15 >= 15 → успех.
    assert roll_ability_check_raw(
        c, skill=Skill.ATHLETICS, dc=15,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
    ) is True


def test_roll_ability_check_poisoned_disadvantage() -> None:
    from dnd.application.engine.ability_check import roll_ability_check_raw
    from dnd.application.engine.condition_service import ConditionService
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.conditions.builtin import POISONED, register_default_conditions
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.battlefield import Battlefield

    reg = ConditionRegistry()
    register_default_conditions(reg)
    deps, _b, _ = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=[18, 3])
    c = _c()
    c.apply_condition(POISONED)  # помеха на ABILITY_CHECK → 2 d20, берём 3
    # d20=3 + 3(STR) = 6 < 12 → провал (без помехи 18 → успех).
    assert roll_ability_check_raw(
        c, ability=Ability.STR, dc=12,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
        condition_service=ConditionService(reg),
    ) is False
```

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать**

В `ability_check.py` добавить:
```python
def roll_ability_check_raw(
    actor: Creature,
    *,
    skill: Skill | None = None,
    ability: Ability | None = None,
    dc: int,
    dice_roller: DiceRoller,
    modifier_applier: ModifierApplier,
    condition_service: ConditionService | None = None,
    tags: tuple[str, ...] = ("ability_check",),
) -> bool:
    """Проверка d20 + бонус + adjustments ≥ dc. Ровно одно из skill/ability.
    Помехи/преимущество от состояний — через ConditionService (Poisoned/
    Frightened дают помеху на ABILITY_CHECK)."""
    if skill is not None:
        bonus = skill_bonus(actor, skill)
    elif ability is not None:
        bonus = ability_check_bonus(actor, ability)
    else:  # pragma: no cover - защита контракта
        raise ValueError("roll_ability_check_raw: нужно skill ИЛИ ability")
    mods = list(
        modifier_applier.collect(
            owner_id=actor.id, target_kind=ModifierTargetKind.ABILITY_CHECK
        )
    )
    if condition_service is not None:
        mods += condition_service.collect_modifiers(
            actor, ModifierTargetKind.ABILITY_CHECK
        )
    adj = modifier_applier.to_roll_adjustments(mods)
    roll = dice_roller.roll(
        DiceExpr.parse(f"d20{bonus + adj.numeric_bonus:+d}"),
        RollContext(
            purpose=RollPurpose.ABILITY_CHECK, actor_id=actor.id,
            advantage=adj.advantage, disadvantage=adj.disadvantage,
            extra_dice=adj.extra_dice, tags=tags,
        ),
    )
    return roll.total >= dc


def roll_ability_check(
    actor: Creature,
    *,
    skill: Skill | None = None,
    ability: Ability | None = None,
    dc: int,
    ctx: TurnContext,
    tags: tuple[str, ...] = ("ability_check",),
) -> bool:
    """Проверка в контексте хода — делегирует в raw."""
    return roll_ability_check_raw(
        actor, skill=skill, ability=ability, dc=dc,
        dice_roller=ctx.dice_roller, modifier_applier=ctx.modifier_applier,
        condition_service=ctx.condition_service, tags=tags,
    )
```
Обновить `__all__`: добавить `"roll_ability_check"`, `"roll_ability_check_raw"`.

- [ ] **Step 4: Зелёно + коммит**

Run: `python3 -m pytest tests/unit/application/test_ability_check.py -q && python3 -m mypy src`.
```bash
git add src/dnd/application/engine/ability_check.py tests/unit/application/test_ability_check.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v1): roll_ability_check[_raw] (помехи/преимущество от состояний)"
```

## Task V1-4: `passive_score` + пассивная Внимательность

**Files:** Modify `ability_check.py`; Test (дописать).

- [ ] **Step 1: Падающий тест**

```python
def test_passive_score_base() -> None:
    from dnd.application.engine.ability_check import passive_score
    c = _c()  # WIS 10 → +0, без владения
    assert passive_score(c, Skill.PERCEPTION) == 10  # 10 + 0


def test_passive_score_proficient() -> None:
    from dnd.application.engine.ability_check import passive_score
    c = _c()
    c.skill_proficiencies = frozenset({Skill.PERCEPTION})
    assert passive_score(c, Skill.PERCEPTION) == 12  # 10 + 0 + prof 2
```

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать**

В `ability_check.py`:
```python
def passive_score(
    actor: Creature, skill: Skill, *,
    modifier_applier: ModifierApplier | None = None,
    condition_service: ConditionService | None = None,
) -> int:
    """Пассивное значение проверки = 10 + бонус навыка (+ numeric-модификаторы,
    ±5 за преимущество/помеху — PHB-2024 стр. 11). Без броска. Пассивная
    Внимательность = passive_score(actor, Skill.PERCEPTION)."""
    score = 10 + skill_bonus(actor, skill)
    if modifier_applier is not None:
        mods = list(
            modifier_applier.collect(
                owner_id=actor.id, target_kind=ModifierTargetKind.ABILITY_CHECK
            )
        )
        if condition_service is not None:
            mods += condition_service.collect_modifiers(
                actor, ModifierTargetKind.ABILITY_CHECK
            )
        adj = modifier_applier.to_roll_adjustments(mods)
        score += adj.numeric_bonus
        if adj.advantage and not adj.disadvantage:
            score += 5
        elif adj.disadvantage and not adj.advantage:
            score -= 5
    return score
```
`__all__`: добавить `"passive_score"`.

- [ ] **Step 4: Зелёно + коммит**

```bash
git add src/dnd/application/engine/ability_check.py tests/unit/application/test_ability_check.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v1): passive_score + пассивная Внимательность"
```

## Task V1-5: источник владений (template/класс) + демо-контент

**Files:** Modify `templates.py`, `class_progression.py`, `yaml_class_repository.py`, `builder.py`, `level_up.py`, `data/content/classes.yaml`, `data/content/monsters.yaml`; Test `tests/integration/content/test_skill_content.py`.

- [ ] **Step 1: Падающий тест**

```python
"""Навыки приходят данными класса/шаблона (V1)."""
from __future__ import annotations

from pathlib import Path

from dnd.domain.values.skill import Skill
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository

_CLASSES = Path("data/content/classes.yaml")


def test_rogue_class_skill_proficiencies() -> None:
    rogue = YamlClassRepository(_CLASSES).load("rogue")
    assert Skill.STEALTH in rogue.skill_proficiencies
```

- [ ] **Step 2: Запустить — падает** (нет поля `skill_proficiencies`).

- [ ] **Step 3: ClassProgression + парсер**

В `domain/values/class_progression.py` (`@dataclass(frozen=True)`): добавить
поле
```python
    skill_proficiencies: frozenset[Skill] = frozenset()
```
(импорт `Skill`). В `yaml_class_repository.py` `_parse`/конструктор
`ClassProgression(...)`:
```python
        skill_proficiencies=frozenset(
            Skill(s) for s in entry.get("skill_proficiencies", [])
        ),
```
(импорт `Skill`). В `classes.yaml` добавить классам базовые навыки (для демо):
```yaml
- id: rogue
  ...
  skill_proficiencies: [stealth, sleight_of_hand]
- id: fighter
  ...
  skill_proficiencies: [athletics]
- id: wizard
  ...
  skill_proficiencies: [arcana]
```
(добавить ключ `skill_proficiencies` на уровне класса, рядом с
`saving_throw_proficiencies`.)

- [ ] **Step 4: Template + builder + level_up**

В `templates.py` `MonsterTemplate`:
```python
    skill_proficiencies: tuple[str, ...] = ()
    skill_expertise: tuple[str, ...] = ()
```
В `builder.py` (после блока saving_throw_proficiencies из класса) — навыки из
класса И из шаблона:
```python
    from dnd.domain.values.skill import Skill
    skills: set[Skill] = set()
    if class_repository is not None and template.character_class is not None \
            and class_repository.contains(template.character_class):
        skills |= class_repository.load(template.character_class).skill_proficiencies
    skills |= {Skill(s) for s in template.skill_proficiencies}
    creature.skill_proficiencies = frozenset(skills)
    creature.skill_expertise = frozenset(Skill(s) for s in template.skill_expertise)
```
В `level_up.py` `apply` (где синхронизируются saving_throw_proficiencies из
класса) — добавить:
```python
        creature.skill_proficiencies = (
            creature.skill_proficiencies | progression.skill_proficiencies
        )
```
(чтобы при level-up навыки класса не терялись; `progression` уже загружен.)

- [ ] **Step 5: Зелёно + регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests`
Expected: зелёно (перепроверить тесты класс-репозитория — у rogue/fighter/wizard
появилось поле `skill_proficiencies`; обновить, если тест сверяет точный состав).
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v1): владение навыками из класса/шаблона (builder/level_up/classes.yaml)"
```

## Task V1-6: документация V1

**Files:** Create `docs/SKILLS.md`; Modify `docs/ROADMAP.md`.

- [ ] **Step 1:** `docs/SKILLS.md`: список 18 навыков + характеристики; формула
бонуса (mod +prof +Экспертиза); `ability_check.py` (roll_ability_check,
passive_score); помехи от состояний через `ConditionService` (ABILITY_CHECK);
источник владений — данные класса/шаблона (полный выбор — в W). `ROADMAP.md`:
отметить **V1 ✅**.

- [ ] **Step 2: Коммит**
```bash
git add docs/SKILLS.md docs/ROADMAP.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "docs(v1): SKILLS.md + ROADMAP (V1 фундамент навыков)"
```

---

# V2 — боевые проверки (состязания)

## Task V2-1: `opposed_check`

**Files:** Modify `ability_check.py`; Test (дописать).

- [ ] **Step 1: Падающий тест**

```python
def test_opposed_check_actor_wins_and_ties_go_to_defender() -> None:
    from dnd.application.engine.ability_check import opposed_check_raw
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.entities.battlefield import Battlefield

    # actor Атлетика +3 (STR16), target Акробатика +2 (DEX14).
    deps, _b, _ = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=[15, 10])
    a, t = _c(), _c()
    # actor: 15+3=18; target лучшее из (Athletics 10+3=13 / Acrobatics 10+2=12)=13 → actor>target → True
    assert opposed_check_raw(
        a, Skill.ATHLETICS, t, (Skill.ATHLETICS, Skill.ACROBATICS),
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
    ) is True
```
> `_c()` возвращает STR16/DEX14 — у обоих одинаково; для проверки «ничья →
> защитник» добавить отдельный тест с равными итогами (actor d20=10 vs target
> d20=10, бонусы равны → actor НЕ строго больше → False).

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать**

В `ability_check.py`:
```python
def opposed_check_raw(
    actor: Creature,
    actor_skill: Skill,
    target: Creature,
    target_skills: tuple[Skill, ...],
    *,
    dice_roller: DiceRoller,
    modifier_applier: ModifierApplier,
    condition_service: ConditionService | None = None,
) -> bool:
    """Состязание: актёр против лучшей из проверок цели. True, если итог актёра
    СТРОГО больше — ничья остаётся за защищающимся (PHB-2024)."""
    a = _check_total(
        actor, actor_skill, dice_roller, modifier_applier, condition_service
    )
    best = max(
        _check_total(target, s, dice_roller, modifier_applier, condition_service)
        for s in target_skills
    )
    return a > best


def _check_total(
    actor: Creature, skill: Skill, dice_roller: DiceRoller,
    modifier_applier: ModifierApplier, condition_service: ConditionService | None,
) -> int:
    bonus = skill_bonus(actor, skill)
    mods = list(
        modifier_applier.collect(
            owner_id=actor.id, target_kind=ModifierTargetKind.ABILITY_CHECK
        )
    )
    if condition_service is not None:
        mods += condition_service.collect_modifiers(
            actor, ModifierTargetKind.ABILITY_CHECK
        )
    adj = modifier_applier.to_roll_adjustments(mods)
    roll = dice_roller.roll(
        DiceExpr.parse(f"d20{bonus + adj.numeric_bonus:+d}"),
        RollContext(
            purpose=RollPurpose.ABILITY_CHECK, actor_id=actor.id,
            advantage=adj.advantage, disadvantage=adj.disadvantage,
            extra_dice=adj.extra_dice, tags=("opposed_check",),
        ),
    )
    return roll.total
```
`__all__`: `"opposed_check_raw"`.

- [ ] **Step 4: Зелёно + коммит**
```bash
git add src/dnd/application/engine/ability_check.py tests/unit/application/test_ability_check.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v2): opposed_check (состязание, ничья → защитник)"
```

## Task V2-2: состояния Grappled / Hidden + guard движения

**Files:** Modify `domain/conditions/builtin.py`; Modify `actions/move.py`; Test `tests/unit/domain/conditions/test_grappled_hidden.py`.

- [ ] **Step 1: Падающий тест**

```python
"""GrappledCondition / HiddenCondition (V2)."""
from __future__ import annotations

from dnd.domain.conditions.builtin import (
    GRAPPLED, HIDDEN, GrappledCondition, HiddenCondition,
)
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.modifiers import AdvantageEffect, ModifierTargetKind


def test_grappled_has_no_combat_flags() -> None:
    g = GrappledCondition()
    assert g.id == GRAPPLED
    assert g.grants_advantage_to_attackers is False
    assert g.provides_modifiers(CreatureId("c")) == ()


def test_hidden_grants_self_attack_advantage() -> None:
    mods = HiddenCondition().provides_modifiers(CreatureId("c"))
    assert len(mods) == 1
    assert isinstance(mods[0].effect, AdvantageEffect)
    assert mods[0].target_kind is ModifierTargetKind.ATTACK_ROLL
```

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Состояния + helper**

В `builtin.py`: добавить id и классы. Сначала `_self_advantage` (рядом с
`_self_disadvantage`):
```python
def _self_advantage(
    owner_id: CreatureId, condition_id: ConditionId, *targets: ModifierTargetKind,
) -> tuple[Modifier, ...]:
    """«Существо имеет преимущество на броски такого-то типа»."""
    from dnd.domain.values.modifiers import AdvantageEffect
    return tuple(
        Modifier(
            source_id=f"condition:{condition_id}",
            source_kind=ModifierSourceKind.CONDITION,
            target_kind=target, effect=AdvantageEffect(), owner_id=owner_id,
            stack_key=f"condition:{condition_id}:{target.value}",
        )
        for target in targets
    )
```
Константы:
```python
GRAPPLED = ConditionId("grappled")
HIDDEN = ConditionId("hidden")
```
Классы (поля T3 — дефолтные False/False/frozenset(); как у Incapacitated):
```python
@dataclass(frozen=True, slots=True)
class GrappledCondition:
    """PHB-2024 стр. 368, «Схваченный». Скорость 0 (guard в MoveAction).
    Сам по себе боевых cross-creature эффектов не даёт."""
    id: ConditionId = GRAPPLED
    implies: frozenset[ConditionId] = field(default_factory=frozenset)
    grants_advantage_to_attackers: bool = False
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset()

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class HiddenCondition:
    """V2 (лёгкая версия): спрятавшийся получает преимущество на свои атаки;
    снимается в attack.py после атаки. Полный стелс («не виден», помеха атакам
    по нему) — отложено."""
    id: ConditionId = HIDDEN
    implies: frozenset[ConditionId] = field(default_factory=frozenset)
    grants_advantage_to_attackers: bool = False
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset()

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        return _self_advantage(owner_id, self.id, ModifierTargetKind.ATTACK_ROLL)
```
Зарегистрировать в `register_default_conditions`:
`registry.register(GrappledCondition())`, `registry.register(HiddenCondition())`.
Обновить `__all__` (GRAPPLED/HIDDEN/GrappledCondition/HiddenCondition).

- [ ] **Step 4: Guard движения при Grappled**

В `move.py` `can_perform` (рядом с проверкой `movement_remaining_ft <= 0`):
```python
        from dnd.domain.conditions.builtin import GRAPPLED
        if actor.has_condition(GRAPPLED):
            return Forbidden(
                reason=ForbiddenReason.CONDITION_BLOCKS_ACTION, details="grappled"
            )
```
(Проверить точный класс/импорт `Forbidden`/`ForbiddenReason` в move.py — взять
как у соседних веток.)

- [ ] **Step 5: Зелёно + коммит**
```bash
git add src/dnd/domain/conditions/builtin.py src/dnd/application/engine/actions/move.py tests/unit/domain/conditions/test_grappled_hidden.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v2): состояния Grappled (speed 0) + Hidden (self-advantage) + guard движения"
```

## Task V2-3: Shove / Grapple — действия + интенты

**Files:** Create `actions/skill_actions.py`; Modify `player_intent.py`, `game_runner.py`; Test `tests/integration/engine/test_shove_grapple.py`.

- [ ] **Step 1: Падающий тест**

```python
"""Shove → Prone, Grapple → Grappled (V2)."""
from __future__ import annotations

from dnd.application.engine.actions.skill_actions import GrappleAction, ShoveAction
from dnd.application.engine.actions.skill_actions import SkillActionParams
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import GRAPPLED, PRONE, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square


def _setup(rolls):
    bf = Battlefield(5, 5)
    hero = Creature.create(
        id_=CreatureId("hero"), name="hero",
        abilities=AbilityScores.of(str_=18, dex=10, con=12, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=14, speed_ft=30,
    )
    hero.skill_proficiencies = frozenset()
    gob = Creature.create(
        id_=CreatureId("g"), name="g",
        abilities=AbilityScores.of(str_=8, dex=8, con=10, int_=8, wis=8, cha=8),
        max_hp=12, armor_class=12, speed_ft=30,
    )
    bf.place_creature(hero.id, Square(1, 1))
    bf.place_creature(gob.id, Square(2, 1))
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    reg = ConditionRegistry(); register_default_conditions(reg)
    ctx = TurnContext(
        actor_id=hero.id, battlefield=bf, dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier, condition_service=ConditionService(reg),
        event_bus=bus, rng=deps.rng,
        participants={hero.id: hero, gob.id: gob},
        factions={hero.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        movement_remaining_ft=30,
    )
    return hero, gob, ctx


def test_shove_success_makes_prone() -> None:
    # hero Athletics 18+4=… d20=18 → 22; gob d20=3 + (-1) = 2 → hero>gob → Prone.
    hero, gob, ctx = _setup([18, 3])
    ShoveAction().execute(hero, SkillActionParams(target_id=gob.id), ctx)
    assert gob.has_condition(PRONE)


def test_grapple_success_grapples() -> None:
    hero, gob, ctx = _setup([18, 3])
    GrappleAction().execute(hero, SkillActionParams(target_id=gob.id), ctx)
    assert gob.has_condition(GRAPPLED)
```

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать действия**

Create `src/dnd/application/engine/actions/skill_actions.py`: `SkillActionParams`
(`ActionParams` с `target_id: CreatureId`), `ShoveAction`/`GrappleAction` (ACTION).
`can_perform_against`: цель в `ctx.participants`, дистанция ≤5 фт, экономика.
`execute`: `ctx.spend(ACTION)`; `won = opposed_check_raw(actor, Skill.ATHLETICS,
target, (Skill.ATHLETICS, Skill.ACROBATICS), dice_roller=ctx.dice_roller,
modifier_applier=ctx.modifier_applier, condition_service=ctx.condition_service)`;
при успехе — `ctx.condition_service.apply_with_implies(target, PRONE)` (Shove)
или `... GRAPPLED` (Grapple); публиковать событие (можно `ConditionApplied` с
`caster_id=actor.id`, `spell_id=None`, `conditions=result.applied`, без
длительности — переиспользуем T2-событие для лога/UI). Структуру `Action`
(id_value/economy_cost_value/`@property`) брать с `DashAction` (stances.py).

- [ ] **Step 4: Интенты + dispatch**

В `player_intent.py`: `ShoveIntent`/`GrappleIntent` (`_IntentBase`,
`kind` Literal, `target_id: CreatureId`). В `game_runner.py` — ветки (как
Dash/Disengage): `isinstance(intent, ShoveIntent)` → `_do_skill(ShoveAction(),
actor, intent, ctx)` (helper строит `SkillActionParams(target_id=intent.
target_id)`, проверяет `can_perform_against`, `execute`/лог-rejected).

- [ ] **Step 5: Зелёно + регрессия + коммит**

Run: `python3 -m pytest tests/integration/engine/test_shove_grapple.py -q && python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests`
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v2): Shove (→Prone) и Grapple (→Grappled) на состязаниях + интенты/диспатч"
```

## Task V2-4: Hide → Hidden + снятие после атаки + e2e

**Files:** Create part of `skill_actions.py` (HideAction); Modify `player_intent.py`, `game_runner.py`, `actions/attack.py`; Test `tests/integration/engine/test_hide.py`, `tests/e2e/test_skills_play.py`.

- [ ] **Step 1: Падающий тест (Hide + снятие)**

```python
"""Hide → Hidden → атака с преимуществом, Hidden снят после атаки (V2)."""
from __future__ import annotations

from dnd.application.dto.engine_event import AttackRolled, EngineEvent
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.skill_actions import HideAction, SkillActionParams
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import HIDDEN, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.skill import Skill
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import SCIMITAR


def test_hide_then_attack_has_advantage_and_clears_hidden() -> None:
    bf = Battlefield(5, 5)
    rogue = Creature.create(
        id_=CreatureId("rogue"), name="rogue",
        abilities=AbilityScores.of(str_=10, dex=18, con=12, int_=12, wis=10, cha=10),
        max_hp=16, armor_class=14, speed_ft=30, equipped_weapon=SCIMITAR,
    )
    rogue.skill_proficiencies = frozenset({Skill.STEALTH})
    gob = Creature.create(
        id_=CreatureId("g"), name="g",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=8),
        max_hp=12, armor_class=10, speed_ft=30,
    )
    bf.place_creature(rogue.id, Square(1, 1))
    bf.place_creature(gob.id, Square(2, 1))
    # Stealth d20=18 vs пассивная Внимательность гоблина (10) → спрятался;
    # атака advantage → 2 d20 (5,19) → 19; затем урон.
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[18, 5, 19, 4])
    reg = ConditionRegistry(); register_default_conditions(reg)
    ctx = TurnContext(
        actor_id=rogue.id, battlefield=bf, dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier, condition_service=ConditionService(reg),
        event_bus=bus, rng=deps.rng,
        participants={rogue.id: rogue, gob.id: gob},
        factions={rogue.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        movement_remaining_ft=30,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    HideAction().execute(rogue, SkillActionParams(target_id=gob.id), ctx)
    assert rogue.has_condition(HIDDEN)
    AttackAction().execute(rogue, weapon_attack_params(rogue, gob.id), ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.advantage is True
    assert not rogue.has_condition(HIDDEN)  # снят после атаки
```

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: HideAction**

В `skill_actions.py`: `HideAction` (ACTION). `execute`: `ctx.spend(ACTION)`;
порог = max пассивная Внимательность врагов рядом (через `passive_score(enemy,
Skill.PERCEPTION)`; враги — по `ctx.factions` != фракция актёра); `hid =
roll_ability_check_raw(actor, skill=Skill.STEALTH, dc=threshold, dice_roller=...,
modifier_applier=..., condition_service=...)`; при успехе
`ctx.condition_service.apply_with_implies(actor, HIDDEN)` + событие. `target_id`
в params не обязателен для Hide — можно сделать его опциональным
(`target_id: CreatureId | None = None`) ИЛИ передавать ближайшего врага; для
простоты порог считаем по всем врагам, target игнорируем.

- [ ] **Step 4: Снятие Hidden после атаки**

В `attack.py` `execute` (после публикации `AttackRolled`/в конце расчёта атаки):
```python
        if actor.has_condition(HIDDEN):
            actor.remove_condition(HIDDEN)
```
(импорт `HIDDEN` из `dnd.domain.conditions.builtin`). Преимущество от Hidden
приходит само — `collect_modifiers(ATTACK_ROLL)` уже подмешивается (T3).

- [ ] **Step 5: Интент + dispatch + e2e**

`HideIntent` в `player_intent.py`; ветка в `game_runner.py`. e2e
`tests/e2e/test_skills_play.py` (`@pytest.mark.e2e`): плут прячется → бьёт с
преимуществом (как тест выше, но через сборку deps). Подогнать RNG-бюджет.

- [ ] **Step 6: Зелёно + регрессия + коммит**

Run: полный набор гейтов.
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(v2): Hide → Hidden (преимущество на атаку, снятие после удара) + e2e"
```

## Task V2-5: документация V2 + аудит-смок

**Files:** Modify `docs/SKILLS.md`, `docs/CONDITIONS.md`, `docs/ROADMAP.md`.

- [ ] **Step 1:** `SKILLS.md` — раздел «Боевые проверки»: состязания
(`opposed_check`, ничья → защитник), Shove (→Prone), Grapple (→Grappled,
speed 0), Hide (→Hidden, лёгкая версия; преимущество на атаку, снятие после
удара). `CONDITIONS.md` — Grappled/Hidden + упрощения (полный стелс/толчок-5фт/
grapple-escape отложены). `ROADMAP.md` — **V ✅**.

- [ ] **Step 2: Финальная регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests && python3 -m pytest tests/unit/test_layering.py -q`
```bash
git add docs/SKILLS.md docs/CONDITIONS.md docs/ROADMAP.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "docs(v): SKILLS/CONDITIONS/ROADMAP — навыки и боевые проверки (этап V завершён)"
```

---

## Self-Review (выполнено)

**Покрытие спека:** §2.1 Skill+mapping — V1-1; §2.2 поля Creature — V1-2; §2.3
служба (skill_bonus/roll/passive) — V1-2/3/4; §2.4 источник владений — V1-5;
§3.1 opposed_check — V2-1; §3.2 Grappled — V2-2; §3.3 Shove/Grapple/Hide —
V2-3/4; §3.4 тесты — в каждом task; §5 инварианты (экспертиза поверх владения,
adv+disadv в RollContext, дефолты) — V1-2/3.

**Согласованность сигнатур:** `skill_bonus(actor, skill)`,
`ability_check_bonus(actor, ability)`, `roll_ability_check_raw(actor, *, skill=,
ability=, dc, dice_roller, modifier_applier, condition_service=None, tags)`,
`passive_score(actor, skill, *, modifier_applier=None, condition_service=None)`,
`opposed_check_raw(actor, actor_skill, target, target_skills, *, dice_roller,
modifier_applier, condition_service=None)`, `SkillActionParams(target_id)` —
одинаково в объявлениях и вызовах. `GRAPPLED`/`HIDDEN`/`Skill`/`SKILL_ABILITY` —
единые id/имена.

**Плейсхолдеры:** «подогнать RNG-бюджет», «взять структуру с DashAction»,
«проверить точный Forbidden в move.py» — указания свериться с существующим
кодом; логика и проверки приведены, не заглушки.

**Риски на месте:** (1) точный конструктор `ClassProgression`/парсер
(skill_proficiencies); (2) тесты класс-репозитория могли сверять точный состав
полей — обновить; (3) RNG-бюджеты состязаний/Hide (advantage = 2 d20); (4)
`_check_total` дублирует сбор adjustments из roll — допустимо (две стороны
состязания), при желании вынести общий хелпер.
