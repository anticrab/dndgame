# T4 — подклассы L3 + боевые стили + Cunning Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Довести Воина/Плута/Волшебника до полного L1–3: боевой стиль (Воин L1), Cunning Action (Плут L2), подклассы на L3 (Чемпион / Вор / Школа Воплощения) — выбором через данные шаблона.

**Architecture:** Выбор хранится в `Creature.fighting_style`/`subclass` (из YAML-шаблона). Мета-фичи-хендлеры (`FightingStyleHandler`/`SubclassHandler`) на `on_gain` применяют выбранную конкретную фичу (или дефолт). Боевые числовые бонусы стилей — изолированный helper `fighting_styles.py` (реестр данных), `attack.py` его зовёт. Sculpt Spells фильтрует AoE в `cast_spell`. Cunning Action грантит bonus-action Dash/Disengage (экономика-оверрайд у действий).

**Tech Stack:** Python 3.12, frozen dataclasses (domain), pydantic v2, pytest, mypy strict, ruff. Guard `tests/unit/test_layering.py`. Коммиты: `Maxim Lokotkov` / `anticrab@users.noreply.github.com`. Доки/комментарии — русский.

---

## Карта файлов

| Файл | Изменение |
|------|-----------|
| `src/dnd/domain/entities/creature.py` | поля `fighting_style`/`subclass: FeatureId|None` |
| `src/dnd/application/dto/templates.py` | `MonsterTemplate.fighting_style`/`subclass: str|None` |
| `src/dnd/application/engine/builder.py` | проводка полей из шаблона |
| `src/dnd/application/engine/features/fighting_styles.py` | **Create** — реестр стилей + helper бонусов |
| `src/dnd/application/engine/features/handlers.py` | `FightingStyleHandler`, `SubclassHandler`, `CunningActionHandler`, `style_*`/`subclass_*`/Fast Hands хендлеры |
| `src/dnd/application/engine/features/defaults.py` | регистрация новых фич |
| `src/dnd/application/engine/actions/attack.py` | бонусы стиля (attack/damage) |
| `src/dnd/application/engine/actions/cast_spell.py` | Sculpt Spells (фильтр AoE) |
| `src/dnd/application/engine/actions/stances.py` | `economy`-параметр Dash/Disengage |
| `src/dnd/application/dto/player_intent.py` | `bonus_action` флаг в DashIntent/DisengageIntent |
| `src/dnd/application/engine/game_runner.py` | bonus-экономика в `_do_stance` |
| `src/dnd/application/abilities/defaults.py` | абилки `cunning_dash`/`cunning_disengage`/`cunning_hide` |
| `data/content/classes.yaml` | фичи выбора по уровням |
| `data/content/monsters.yaml` | `fighting_style`/`subclass` у воина |
| `docs/PROGRESSION.md`, `docs/ABILITIES.md`, `docs/SPELLS.md`, `docs/ROADMAP.md` | T4 |

`FeatureId` = `NewType(str)` (`domain/values/ids`). Все новые `creature`-поля и
template-поля — с дефолтами (backward-compat).

---

# T4-a — боевые стили (Воин L1)

## Task T4a-1: поля выбора + helper стилей + Defense (+1 AC)

**Files:**
- Modify: `src/dnd/domain/entities/creature.py`, `src/dnd/application/dto/templates.py`, `src/dnd/application/engine/builder.py`
- Create: `src/dnd/application/engine/features/fighting_styles.py`
- Modify: `src/dnd/application/engine/features/handlers.py`, `.../features/defaults.py`
- Test: `tests/unit/application/test_fighting_styles.py` (Create)

- [ ] **Step 1: Падающий тест**

Create `tests/unit/application/test_fighting_styles.py`:

```python
"""Боевые стили Воина (T4-a)."""
from __future__ import annotations

from dnd.application.engine.features.defaults import default_feature_registry
from dnd.application.engine.features.fighting_styles import (
    fighting_style_attack_bonus,
    fighting_style_damage_bonus,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.ids import FeatureId


def _c() -> Creature:
    return Creature.create(
        id_="c", name="c",
        abilities=AbilityScores.of(str_=14, dex=14, con=12, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=15, speed_ft=30,
    )


def test_defense_style_adds_ac_on_gain() -> None:
    reg = default_feature_registry()
    c = _c()
    c.fighting_style = FeatureId("style_defense")
    reg.get(FeatureId("fighting_style")).on_gain(c, None)
    assert c.armor_class == 16  # 15 + 1
    assert FeatureId("style_defense") in c.features


def test_fighting_style_default_is_defense() -> None:
    reg = default_feature_registry()
    c = _c()  # fighting_style не задан
    reg.get(FeatureId("fighting_style")).on_gain(c, None)
    assert c.armor_class == 16
    assert FeatureId("style_defense") in c.features


def test_archery_attack_bonus_ranged_only() -> None:
    c = _c()
    c.fighting_style = FeatureId("style_archery")
    assert fighting_style_attack_bonus(c, AttackKind.RANGED) == 2
    assert fighting_style_attack_bonus(c, AttackKind.MELEE) == 0


def test_dueling_damage_bonus_melee_only() -> None:
    c = _c()
    c.fighting_style = FeatureId("style_dueling")
    assert fighting_style_damage_bonus(c, AttackKind.MELEE) == 2
    assert fighting_style_damage_bonus(c, AttackKind.RANGED) == 0
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_fighting_styles.py -q`
Expected: FAIL (нет полей/модуля).

- [ ] **Step 3: Поля Creature**

В `creature.py` рядом с `features: tuple[FeatureId, ...] = ()` добавить:
```python
    # T4: выбор данными шаблона (интерактив отложен). Какой боевой стиль /
    # подкласс выбран; применяется мета-фичей на нужном уровне.
    fighting_style: FeatureId | None = None
    subclass: FeatureId | None = None
```
(`FeatureId` уже импортирован в creature.py — проверить; если нет, добавить в
`from dnd.domain.values.ids import ...`.)

- [ ] **Step 4: helper-модуль стилей**

Create `src/dnd/application/engine/features/fighting_styles.py`:
```python
"""Боевые стили Воина (T4-a) — данные + чистые helper'ы бонусов.

Числовые/пассивные эффекты стиля. attack.py зовёт helper'ы (не switch по
классам). Defense применяется при получении фичи (см. FightingStyleHandler),
здесь — только ситуативные боевые бонусы атака/урон.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.ids import FeatureId

if TYPE_CHECKING:
    from dnd.domain.entities.creature import Creature

STYLE_DEFENSE = FeatureId("style_defense")
STYLE_DUELING = FeatureId("style_dueling")
STYLE_ARCHERY = FeatureId("style_archery")
STYLE_GWF = FeatureId("style_gwf")  # отложен (нужен reroll-хук урона)

#: Все известные стили — для валидации/автодефолта.
KNOWN_STYLES = frozenset({STYLE_DEFENSE, STYLE_DUELING, STYLE_ARCHERY, STYLE_GWF})


def fighting_style_attack_bonus(actor: Creature, kind: AttackKind) -> int:
    """Archery: +2 к ranged-атаке (PHB-2024)."""
    if actor.fighting_style == STYLE_ARCHERY and kind is AttackKind.RANGED:
        return 2
    return 0


def fighting_style_damage_bonus(actor: Creature, kind: AttackKind) -> int:
    """Dueling: +2 к урону melee (приближение «одноручного» — любое melee)."""
    if actor.fighting_style == STYLE_DUELING and kind is AttackKind.MELEE:
        return 2
    return 0


__all__ = [
    "KNOWN_STYLES", "STYLE_ARCHERY", "STYLE_DEFENSE", "STYLE_DUELING", "STYLE_GWF",
    "fighting_style_attack_bonus", "fighting_style_damage_bonus",
]
```

- [ ] **Step 5: FightingStyleHandler + style_defense**

В `handlers.py` добавить (импорт `FeatureId` уже есть в файле — проверить; если
нет, `from dnd.domain.values.ids import FeatureId`):
```python
class StyleDefenseHandler:
    """Defense: +1 КД (пассив, persist в Creature.armor_class)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.armor_class += 1


class _NoEffectHandler:
    """Стиль без on_gain-эффекта (бонусы — ситуативно в attack.py)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        return


class FightingStyleHandler:
    """Воин L1: применяет выбранный боевой стиль (данные шаблона) или дефолт
    (Defense). T4: выбор данными шаблона (интерактив отложен)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        from dnd.application.engine.features.fighting_styles import (
            KNOWN_STYLES, STYLE_DEFENSE,
        )
        style = creature.fighting_style
        if style is None or style not in KNOWN_STYLES:
            style = STYLE_DEFENSE
            creature.fighting_style = style
        if style not in creature.features:
            creature.features = (*creature.features, style)
        # Применить эффект конкретного стиля через тот же реестр.
        _FEATURE_REGISTRY_REF.get(style).on_gain(creature, ctx)
```

> Проблема: хендлеру нужен доступ к реестру, чтобы применить конкретный стиль.
> Чтобы не тащить глобал, передадим реестр в конструктор хендлера. Перепишем:
> `FightingStyleHandler(registry)` хранит `self._reg`, в `on_gain` зовёт
> `self._reg.get(style).on_gain(...)`. defaults.py соберёт реестр и
> зарегистрирует `FightingStyleHandler(reg)` после регистрации `style_*`.
> Аналогично для SubclassHandler (T4-b). Финальный код хендлера:

```python
class FightingStyleHandler:
    def __init__(self, registry: FeatureRegistry) -> None:
        self._reg = registry

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        from dnd.application.engine.features.fighting_styles import (
            KNOWN_STYLES, STYLE_DEFENSE,
        )
        style = creature.fighting_style
        if style is None or style not in KNOWN_STYLES:
            style = STYLE_DEFENSE
            creature.fighting_style = style
        if style not in creature.features:
            creature.features = (*creature.features, style)
        self._reg.get(style).on_gain(creature, ctx)
```
(Импорт `FeatureRegistry` — в TYPE_CHECKING.)

- [ ] **Step 6: defaults.py — регистрация**

В `default_feature_registry`:
```python
    reg.register(FeatureId("style_defense"), StyleDefenseHandler())
    reg.register(FeatureId("style_dueling"), _NoEffectHandler())
    reg.register(FeatureId("style_archery"), _NoEffectHandler())
    reg.register(FeatureId("style_gwf"), _NoEffectHandler())
    reg.register(FeatureId("fighting_style"), FightingStyleHandler(reg))
```
(импорты хендлеров — дополнить.)

- [ ] **Step 7: Запустить — зелёно**

Run: `python3 -m pytest tests/unit/application/test_fighting_styles.py -q`
Expected: PASS (4 теста).

- [ ] **Step 8: Template + builder**

В `templates.py` `MonsterTemplate`:
```python
    fighting_style: str | None = None
    subclass: str | None = None
```
В `builder.py` после `creature.level = template.level` (и `creature.xp`):
```python
    # T4: выбор данными шаблона (интерактив отложен).
    creature.fighting_style = (
        FeatureId(template.fighting_style) if template.fighting_style else None
    )
    creature.subclass = FeatureId(template.subclass) if template.subclass else None
```
Импорт `FeatureId` в builder.py: добавить в `from dnd.domain.values.ids import ...`.

- [ ] **Step 9: attack.py — бонусы стиля**

В импорты attack.py:
```python
from dnd.application.engine.features.fighting_styles import (
    fighting_style_attack_bonus,
    fighting_style_damage_bonus,
)
```
В расчёт атаки:
```python
        total_atk_bonus = (
            params.attack_bonus + atk_adj.numeric_bonus
            + fighting_style_attack_bonus(actor, params.kind)
        )
```
В расчёт урона (где собирается `dmg_adj.numeric_bonus` в выражение урона) —
прибавить `fighting_style_damage_bonus(actor, params.kind)` к числовому бонусу
урона. Найти строку, где формируется damage-выражение/числовой бонус, и
добавить слагаемое (рядом с `dmg_adj.numeric_bonus`).

- [ ] **Step 10: classes.yaml + контент воина**

В `data/content/classes.yaml` fighter L1: `features: [second_wind, fighting_style]`.
В `data/content/monsters.yaml` `warrior_veteran` и боевому PC-воину добавить
`fighting_style: defense`.

- [ ] **Step 11: Регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: зелёно (перепроверить: воин теперь +1 AC от defense — демо-тесты AC).

```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t4a): боевые стили Воина (Defense/Archery/Dueling) + поля выбора + helper"
```

---

# T4-b — подклассы L3

## Task T4b-1: SubclassHandler + Champion + Evoker Sculpt Spells + Thief

**Files:**
- Modify: `src/dnd/application/engine/features/handlers.py`, `.../features/defaults.py`
- Modify: `src/dnd/application/engine/actions/cast_spell.py`
- Modify: `data/content/classes.yaml`
- Test: `tests/unit/application/test_subclasses.py` (Create), `tests/integration/engine/test_sculpt_spells.py` (Create)

- [ ] **Step 1: Падающий тест подклассов**

Create `tests/unit/application/test_subclasses.py`:
```python
"""Подклассы L3 (T4-b): автовыбор по классу + эффект."""
from __future__ import annotations

from dnd.application.engine.features.defaults import default_feature_registry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import FeatureId


def _c(cls: str) -> Creature:
    c = Creature.create(
        id_="c", name="c",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=12, wis=10, cha=10),
        max_hp=20, armor_class=14, speed_ft=30,
    )
    c.character_class = cls
    return c


def test_fighter_subclass_default_champion_sets_crit() -> None:
    reg = default_feature_registry()
    c = _c("fighter")
    reg.get(FeatureId("subclass")).on_gain(c, None)
    assert c.subclass == FeatureId("subclass_champion")
    assert c.crit_range_min == 19  # Improved Critical


def test_wizard_subclass_default_evoker_flag() -> None:
    reg = default_feature_registry()
    c = _c("wizard")
    reg.get(FeatureId("subclass")).on_gain(c, None)
    assert c.subclass == FeatureId("subclass_evoker")
    assert FeatureId("subclass_evoker") in c.features


def test_rogue_subclass_default_thief() -> None:
    reg = default_feature_registry()
    c = _c("rogue")
    reg.get(FeatureId("subclass")).on_gain(c, None)
    assert c.subclass == FeatureId("subclass_thief")
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_subclasses.py -q`
Expected: FAIL.

- [ ] **Step 3: Хендлеры подклассов**

В `handlers.py`:
```python
#: Дефолтный подкласс по классу (T4: выбор данными шаблона, интерактив отложен).
_DEFAULT_SUBCLASS = {
    "fighter": FeatureId("subclass_champion"),
    "rogue": FeatureId("subclass_thief"),
    "wizard": FeatureId("subclass_evoker"),
}


class SubclassHandler:
    """L3: применяет выбранный подкласс (данные шаблона) или дефолт по классу."""

    def __init__(self, registry: FeatureRegistry) -> None:
        self._reg = registry

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        sub = creature.subclass
        if sub is None or not self._reg.has(sub):
            sub = _DEFAULT_SUBCLASS.get(creature.character_class or "")
        if sub is None:
            return
        creature.subclass = sub
        if sub not in creature.features:
            creature.features = (*creature.features, sub)
        self._reg.get(sub).on_gain(creature, ctx)


class ThiefHandler:
    """Вор L3 (лёгкая версия): Fast Hands — бонусным действием Interact.
    Second-Story Work (лазание) — вне scope, описано в доках."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        _grant_ability(creature, "interact")  # доступно и так; флаг подкласса в features


class EvokerHandler:
    """Школа Воплощения L3: Sculpt Spells — поведение в cast_spell по наличию
    фичи subclass_evoker; on_gain — пасс (фича уже в features)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        return
```
> Champion = существующий `ImprovedCriticalHandler` (переиспользуем под id
> `subclass_champion`). Нужен `FeatureRegistry.has` — проверить наличие (есть
> у других реестров; если нет — добавить `def has(self, fid) -> bool`).

- [ ] **Step 4: defaults.py регистрация подклассов**

```python
    reg.register(FeatureId("subclass_champion"), ImprovedCriticalHandler())
    reg.register(FeatureId("subclass_thief"), ThiefHandler())
    reg.register(FeatureId("subclass_evoker"), EvokerHandler())
    reg.register(FeatureId("subclass"), SubclassHandler(reg))
```
(`improved_critical` остаётся зарегистрированным для backward-compat старых
шаблонов; новые classes.yaml используют `subclass`.)

- [ ] **Step 5: classes.yaml L3**

- fighter L3: `features: [subclass]` (было `improved_critical`).
- rogue L3: `features: [subclass]`.
- wizard L3: `features: [subclass]` (+ существующие spell_slots).

- [ ] **Step 6: Запустить тест подклассов — зелёно**

Run: `python3 -m pytest tests/unit/application/test_subclasses.py -q`
Expected: PASS.

- [ ] **Step 7: Sculpt Spells — тест**

Create `tests/integration/engine/test_sculpt_spells.py`:
```python
"""Эвокатор Sculpt Spells (T4-b): союзники кастера не получают урон его AoE."""
from __future__ import annotations

from dnd.application.dto.action import Allowed
from dnd.application.engine.actions.cast_spell import CastSpellAction, CastSpellParams
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import FeatureId, SpellId
from dnd.domain.values.spell import (
    AreaShape, OriginMode, Spell, SpellEffect, TargetingSpec, TargetKind,
)
from dnd.domain.values.damage import DamageType


def _fireball() -> Spell:
    return Spell(
        id=SpellId("fireball"), name="Fireball", level=3, school="evocation",
        effect=SpellEffect.SAVE,
        targeting=TargetingSpec(
            kind=TargetKind.AREA, origin=OriginMode.AT_POINT,
            shape=AreaShape.CIRCLE, radius_ft=10,
        ),
        range_ft=150, description="", dice="2d6", damage_type=DamageType.FIRE,
        save_ability=Ability.DEX, save_for_half=True,
    )


def test_sculpt_excludes_caster_ally() -> None:
    from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository
    from pathlib import Path
    bf = Battlefield(8, 8)
    from dnd.domain.values.square import Square
    mage = Creature.create(
        id_="mage", name="mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=14, armor_class=12, speed_ft=30,
    )
    mage.spellcasting_ability = Ability.INT
    mage.spell_slots = {3: 1}
    mage.subclass = FeatureId("subclass_evoker")
    mage.features = (FeatureId("subclass_evoker"),)
    ally = Creature.create(
        id_="ally", name="ally",
        abilities=AbilityScores.of(str_=12, dex=10, con=12, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=12, speed_ft=30,
    )
    foe = Creature.create(
        id_="foe", name="foe",
        abilities=AbilityScores.of(str_=12, dex=10, con=12, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=12, speed_ft=30,
    )
    bf.place_creature(mage.id, Square(0, 0))
    bf.place_creature(ally.id, Square(5, 5))
    bf.place_creature(foe.id, Square(6, 5))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[1, 1] + [3] * 20)
    reg = ConditionRegistry(); register_default_conditions(reg)
    ctx = TurnContext(
        actor_id=mage.id, battlefield=bf,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
        condition_service=ConditionService(reg), event_bus=deps.event_bus,
        rng=deps.rng,
        participants={mage.id: mage, ally.id: ally, foe.id: foe},
        factions={mage.id: Faction.PARTY, ally.id: Faction.PARTY,
                  foe.id: Faction.MONSTERS},
        movement_remaining_ft=30,
    )
    spells = YamlSpellRepository(Path("data/content/spells.yaml"))
    action = CastSpellAction(spell_repository=spells)
    params = CastSpellParams(spell_id=SpellId("fireball"), target_point=Square(5, 5))
    assert isinstance(action.can_perform_against(mage, params, ctx), Allowed)
    action.execute(mage, params, ctx)
    assert ally.hit_points.current == ally.hit_points.maximum  # союзник невредим
    assert foe.hit_points.current < foe.hit_points.maximum     # враг получил урон
```
> Сверить, что `TurnContext` принимает `factions=` и что `deps` отдаёт
> `event_bus`/`rng` (build_scripted_dependencies). Если конструктор иной —
> подогнать, сохранив проверку «союзник невредим, враг — нет».

- [ ] **Step 8: Sculpt Spells — реализация**

В `cast_spell.py`, в `_resolve_targets` AREA-ветке (и в SAVE/AUTO AoE-обработке,
где собираются цели в зоне) — после сбора кандидатов-`cid` отфильтровать
союзников кастера, если у кастера фича Эвокатора:
```python
        if FeatureId("subclass_evoker") in caster.features:
            caster_faction = ctx.factions.get(caster.id)
            cids = [
                cid for cid in cids
                if ctx.factions.get(cid) != caster_faction
            ]
```
(Имена переменных — под фактический код `_resolve_targets`; `caster`/`actor` и
`cids`/список целей привести к локальным. Импорт `FeatureId`.) Применять только
к AoE-зоне (не к SELF/SINGLE).

- [ ] **Step 9: Запустить — зелёно + регрессия**

Run: `python3 -m pytest tests/integration/engine/test_sculpt_spells.py tests/unit/application/test_subclasses.py -q && python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: зелёно (перепроверить демо/level-up: fighter L3 → subclass → champion → crit 19).

- [ ] **Step 10: Коммит**

```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t4b): подклассы L3 — Чемпион/Вор/Эвокатор (Sculpt Spells) + автовыбор по классу"
```

---

# T4-c — Cunning Action (Плут L2) + добивка + доки

## Task T4c-1: Cunning Action (bonus Dash/Disengage)

**Files:**
- Modify: `src/dnd/application/dto/player_intent.py`, `.../actions/stances.py`, `.../game_runner.py`, `.../abilities/defaults.py`, `.../features/handlers.py`, `.../features/defaults.py`, `data/content/classes.yaml`
- Test: `tests/integration/engine/test_cunning_action.py` (Create)

- [ ] **Step 1: Падающий тест**

Create `tests/integration/engine/test_cunning_action.py`:
```python
"""Cunning Action (T4-c): Плут L2 — Dash/Disengage бонусным действием."""
from __future__ import annotations

from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import DashIntent
from dnd.application.engine.actions.stances import DashAction
from dnd.application.engine.features.defaults import default_feature_registry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import AbilityId, FeatureId


def test_cunning_action_grants_bonus_abilities() -> None:
    reg = default_feature_registry()
    c = Creature.create(
        id_="r", name="r",
        abilities=AbilityScores.of(str_=10, dex=16, con=12, int_=12, wis=10, cha=10),
        max_hp=16, armor_class=14, speed_ft=30,
    )
    reg.get(FeatureId("cunning_action")).on_gain(c, None)
    assert AbilityId("cunning_dash") in c.ability_ids
    assert AbilityId("cunning_disengage") in c.ability_ids


def test_dash_action_bonus_economy_spends_bonus() -> None:
    # DashAction с economy=BONUS_ACTION тратит бонусное действие, не основное.
    action = DashAction(economy=ActionEconomyCost.BONUS_ACTION)
    assert action.economy_cost is ActionEconomyCost.BONUS_ACTION


def test_dash_intent_carries_bonus_flag() -> None:
    assert DashIntent(bonus_action=True).bonus_action is True
    assert DashIntent().bonus_action is False
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/integration/engine/test_cunning_action.py -q`
Expected: FAIL.

- [ ] **Step 3: bonus-флаг в интентах**

В `player_intent.py` у `DashIntent` и `DisengageIntent` добавить поле
`bonus_action: bool = False` (pydantic-поле; сохранить frozen/extra-config как
у соседних интентов).

- [ ] **Step 4: economy-параметр у действий**

В `stances.py` `DashAction` и `DisengageAction`: добавить `__init__(self, *,
economy: ActionEconomyCost = ActionEconomyCost.ACTION)` → `self._economy`;
свойство `economy_cost` возвращает `self._economy`; в `can_perform` проверять
`ctx.can_spend(self._economy)`; в `execute` — `ctx.spend(self._economy)` вместо
жёсткого `ACTION`. (DodgeAction не трогаем.) Проверить, что `can_perform` сейчас
проверяет economy — привести к `self._economy`.

- [ ] **Step 5: game_runner — bonus при флаге**

В `_run_pc_turn`/dispatch, где `DashIntent`/`DisengageIntent`:
```python
        if isinstance(intent, DashIntent):
            economy = (
                ActionEconomyCost.BONUS_ACTION if intent.bonus_action
                else ActionEconomyCost.ACTION
            )
            self._do_stance(DashAction(economy=economy), actor, ctx)
            return
        if isinstance(intent, DisengageIntent):
            economy = (
                ActionEconomyCost.BONUS_ACTION if intent.bonus_action
                else ActionEconomyCost.ACTION
            )
            self._do_stance(DisengageAction(economy=economy), actor, ctx)
            return
```
(Импорт `ActionEconomyCost`. `_do_stance` type hint расширить не нужно —
действия те же классы.)

- [ ] **Step 6: абилки Cunning Action**

В `abilities/defaults.py` добавить фабрики и абилки:
```python
def _cunning_dash() -> PlayerIntent:
    return DashIntent(bonus_action=True)


def _cunning_disengage() -> PlayerIntent:
    return DisengageIntent(bonus_action=True)
```
Регистрировать (НЕ в дефолтном наборе всех существ — это фича Плута; их грантит
CunningActionHandler через `_grant_ability`). Но абилки должны быть в
`AbilityRegistry`, иначе keymap их не найдёт. Зарегистрировать в
`register_default_abilities` (доступность — по наличию в `ability_ids`):
```python
    registry.register(Ability(
        id=AbilityId("cunning_dash"), name="Cunning Dash (bonus)", icon="h",
        default_hotkey="", economy_cost=ActionEconomyCost.BONUS_ACTION,
        requires_target=False, requires_path=False, intent_factory=_cunning_dash,
    ))
    registry.register(Ability(
        id=AbilityId("cunning_disengage"), name="Cunning Disengage (bonus)", icon="g",
        default_hotkey="", economy_cost=ActionEconomyCost.BONUS_ACTION,
        requires_target=False, requires_path=False, intent_factory=_cunning_disengage,
    ))
```

- [ ] **Step 7: CunningActionHandler**

В `handlers.py`:
```python
class CunningActionHandler:
    """Плут L2: Cunning Action — бонусным действием Dash/Disengage (Hide —
    лёгкая версия/вне scope). Грантит соответствующие абилки."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        _grant_ability(creature, "cunning_dash")
        _grant_ability(creature, "cunning_disengage")
```
В `defaults.py`: `reg.register(FeatureId("cunning_action"), CunningActionHandler())`.

- [ ] **Step 8: classes.yaml rogue L2**

rogue L2: `features: [cunning_action]`.

- [ ] **Step 9: Запустить — зелёно**

Run: `python3 -m pytest tests/integration/engine/test_cunning_action.py -q && python3 -m pytest -q`
Expected: PASS, регрессия зелёная.

- [ ] **Step 10: Коммит**

```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t4c): Cunning Action — Dash/Disengage бонусным действием (Плут L2)"
```

## Task T4c-2: e2e + документация

**Files:**
- Create: `tests/e2e/test_subclasses_play.py`
- Modify: `docs/PROGRESSION.md`, `docs/ABILITIES.md`, `docs/ROADMAP.md`

- [ ] **Step 1: e2e**

Create `tests/e2e/test_subclasses_play.py` — собрать воина из шаблона с
`character_class: fighter`, `fighting_style: defense`, прокачать LevelUpService'ом
до L3 и проверить: `armor_class` получил +1 (defense на L1), `crit_range_min == 19`
(champion на L3), `"action_surge" in resource_uses` (L2). Модель — по
`tests/e2e/test_demo_skirmish.py` (LevelUpService + default_feature_registry).
Пометить `@pytest.mark.e2e`.

```python
"""E2E T4: воин L1→L3 получает стиль (Defense +1 AC) и подкласс (Champion crit 19)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.engine.features.defaults import default_feature_registry
from dnd.application.engine.progression.level_up import LevelUpService
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId, FeatureId


@pytest.mark.e2e
def test_fighter_l1_to_l3_gains_style_and_champion() -> None:
    classes = YamlClassRepository(Path("data/content/classes.yaml"))
    svc = LevelUpService(
        class_repository=classes, feature_registry=default_feature_registry(),
        event_bus=InMemoryEventBus(),
    )
    fighter = Creature.create(
        id_=CreatureId("f"), name="f",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=16, speed_ft=30,
    )
    fighter.character_class = "fighter"
    fighter.fighting_style = FeatureId("style_defense")
    svc.apply(fighter, to_level=1, ctx=None)
    assert fighter.armor_class == 17  # Defense +1
    svc.apply(fighter, to_level=2, ctx=None)
    assert "action_surge" in fighter.resource_uses
    svc.apply(fighter, to_level=3, ctx=None)
    assert fighter.crit_range_min == 19  # Champion → Improved Critical
    assert fighter.subclass == FeatureId("subclass_champion")
```
> Сверить сигнатуру `LevelUpService.apply(creature, to_level, ctx)` и что L1
> применяется (если apply идёт «от текущего+1 до to_level», стартовать с L1).
> Подогнать вызовы под фактический контракт, сохранив проверки.

- [ ] **Step 2: Запустить e2e — зелёно (подгонкой)**

Run: `python3 -m pytest tests/e2e/test_subclasses_play.py -q`
Expected: PASS.

- [ ] **Step 3: Документация**

- `docs/PROGRESSION.md` §7c: боевые стили (Воин L1, выбор данными), Cunning
  Action (Плут L2), подклассы L3 (Чемпион/Вор/Эвокатор); отметить «выбор данными
  шаблона, интерактив отложен»; что отложено (GWF, Hide, Second-Story, навыки).
- `docs/ABILITIES.md`: cunning_dash/cunning_disengage (bonus-economy).
- `docs/ROADMAP.md`: веха **T4 ✅** (серия T завершена); обновить пункт про
  подклассы из ⏳ в ✅.

- [ ] **Step 4: Финальная регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m pytest tests/unit/test_layering.py -q`
Expected: всё зелёно, guard проходит.

```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "test+docs(t4): e2e подклассов/стилей + PROGRESSION/ABILITIES/ROADMAP (серия T завершена)"
```

---

## Self-Review (выполнено)

**Покрытие спека:** §2.1 поля выбора+мета-хендлеры — T4a-1/T4b-1; §2.2 стили —
T4a-1; §2.3 подклассы (Champion/Thief/Evoker+Sculpt) — T4b-1; §2.4 Cunning
Action — T4c-1; §2.5 wiring — распределён; §4 тесты — юнит/интеграция/e2e
покрыты; §5 инварианты — backward-compat дефолты, автодетерминизм, layering.

**Согласованность:** `FightingStyleHandler(registry)`/`SubclassHandler(registry)`
— конструктор с реестром, регистрируются ПОСЛЕ конкретных фич; `style_*`/
`subclass_*` id одинаковы в handlers/defaults/fighting_styles/тестах; `DashAction(
economy=...)` + `DashIntent(bonus_action=...)` согласованы T4c-1.

**Плейсхолдеры:** «сверить сигнатуру/подогнать» (Sculpt _resolve_targets,
TurnContext factions, LevelUpService.apply) — указания свериться с фактическим
кодом; логика и проверки приведены, не заглушки.

**Риски на месте:** (1) точные имена переменных в `cast_spell._resolve_targets`
для фильтра Sculpt; (2) `FeatureRegistry.has` существует ли; (3) `DashAction.
can_perform` сейчас проверяет economy — привести к `self._economy`; (4)
demo/level-up тесты на fighter L3 (improved_critical через subclass) — обновить
ожидания, если ссылались на прямую фичу `improved_critical`.
