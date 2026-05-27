# Каркас волшебника (T1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development или superpowers:executing-plans — task-by-task. Шаги — чекбоксы.

**Goal:** Играбельный волшебник, кастующий через меню способностей; + профициентные спасброски классов (закрывает отложенный пункт аудита).

**Architecture:** Класс/слоты/спасброски — данные (`classes.yaml`) + готовый `LevelUpService`. Единая точка `roll_saving_throw` (prof не дублируется). Заклинания → `Ability` в меню через новый `requires_area`. Движок конструкций не ломаем — расширяем.

**Tech stack:** Python 3.12, pydantic v2, dataclasses, Textual, pytest. Тесты: `python3 -m pytest -q`, `python3 -m mypy src`, `python3 -m ruff check src tests`.

**Спек:** `docs/superpowers/specs/2026-05-27-t1-wizard-core-design.md`.
**Коммиты:** `Maxim Lokotkov` / `anticrab@users.noreply.github.com`. Язык — русский.

---

## File Structure
- `src/dnd/domain/values/class_progression.py` — +`saving_throw_proficiencies`.
- `src/dnd/infrastructure/content/yaml_class_repository.py` — парсинг нового поля.
- `data/content/classes.yaml` — поле у fighter/rogue + новый `wizard`.
- `src/dnd/domain/entities/creature.py` — +`saving_throw_proficiencies`.
- `src/dnd/application/engine/builder.py` — заполнять профы из класса.
- `src/dnd/application/engine/scenario_builder.py` — прокинуть `class_repository`.
- `src/dnd/application/engine/progression/level_up.py` — ставить профы при level-up.
- `src/dnd/application/engine/saving_throw.py` — **create**: `roll_saving_throw`.
- `src/dnd/application/engine/spells/handlers.py` — `SaveSpellHandler` → helper.
- `src/dnd/application/engine/encounter.py` — concentration-save → helper.
- `src/dnd/application/abilities/ability.py` — +`requires_area`.
- `src/dnd/application/abilities/spell_abilities.py` — `requires_area` для AREA.
- `src/dnd/interfaces/tui/screens/battle.py` — AREA-ветка для ability + спеллы в `ability_ids`.
- `data/content/monsters.yaml` — `mage_apprentice` → `character_class: wizard`.
- `src/dnd/interfaces/cli/app.py`, `src/dnd/interfaces/tui/app.py` — `class_repository` в build_encounter.
- docs: SPELLS.md / ABILITIES.md / PROGRESSION.md / ROADMAP.md.

---

## Task T1-1: `saving_throw_proficiencies` в ClassProgression + classes.yaml

**Files:** Modify `class_progression.py`, `yaml_class_repository.py`, `data/content/classes.yaml`; Test `tests/unit/domain/test_class_progression.py`.

- [ ] **Step 1: Failing-тест** (дописать в test_class_progression.py):

```python
def test_class_progression_has_saving_throw_proficiencies() -> None:
    from dnd.domain.values.ability import Ability
    from dnd.domain.values.class_progression import ClassLevel, ClassProgression
    prog = ClassProgression(
        id="x", name="X", hit_die="1d6",
        levels={1: ClassLevel(proficiency_bonus=2)},
        saving_throw_proficiencies=frozenset({Ability.INT, Ability.WIS}),
    )
    assert Ability.INT in prog.saving_throw_proficiencies
```

- [ ] **Step 2: FAIL** — `TypeError: unexpected keyword 'saving_throw_proficiencies'`.

Run: `python3 -m pytest tests/unit/domain/test_class_progression.py -q`

- [ ] **Step 3: Реализация.** В `class_progression.py` (frozen dataclass `ClassProgression`) добавить поле:

```python
from dnd.domain.values.ability import Ability
...
    saving_throw_proficiencies: frozenset[Ability] = frozenset()
```

(Поле — после существующих, с дефолтом, чтобы не ломать вызовы.)

- [ ] **Step 4: Парсинг в `YamlClassRepository`.** Где собирается `ClassProgression` из YAML — прочитать `saving_throw_proficiencies` (список строк-кодов абилки) → `frozenset(Ability(code) for code in raw)`; пустой по умолчанию.

- [ ] **Step 5: classes.yaml** — добавить поле классам:

```yaml
- id: fighter
  name: "Воин"
  hit_die: "1d10"
  saving_throw_proficiencies: [STR, CON]
  levels: { ... как было ... }
- id: rogue
  name: "Плут"
  hit_die: "1d8"
  saving_throw_proficiencies: [DEX, INT]
  levels: { ... }
```

- [ ] **Step 6: PASS + repo-тест.** Прогнать unit + интеграционный тест репозитория (если есть `test_yaml_class_repository`): fighter профы = {STR, CON}.

Run: `python3 -m pytest tests/unit/domain/test_class_progression.py tests/integration/content -q -k "class"`

- [ ] **Step 7: mypy/ruff + commit**

```bash
git add src/dnd/domain/values/class_progression.py src/dnd/infrastructure/content/yaml_class_repository.py data/content/classes.yaml tests/unit/domain/test_class_progression.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(t1): saving_throw_proficiencies в ClassProgression + classes.yaml"
```

---

## Task T1-2: `Creature.saving_throw_proficiencies` + заполнение

**Files:** Modify `creature.py`, `builder.py`, `scenario_builder.py`, `level_up.py`, `cli/app.py`, `tui/app.py`; Test `tests/unit/application/test_builder_xp.py` (рядом).

- [ ] **Step 1: Failing-тест** (новый файл `tests/integration/content/test_class_save_profs.py`):

```python
from __future__ import annotations
from pathlib import Path
from dnd.application.dto.templates import AbilityScoresTemplate, MonsterTemplate
from dnd.application.engine.builder import build_creature_from_template
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import CreatureId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository


class _NoContent:
    pass


def test_builder_sets_class_save_proficiencies() -> None:
    repo = YamlClassRepository(Path("data/content/classes.yaml"))
    tmpl = MonsterTemplate(
        id="f", name="F",
        abilities=AbilityScoresTemplate.model_validate(
            {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10}
        ),
        max_hp=20, armor_class=16, character_class="fighter", level=1,
    )
    c = build_creature_from_template(
        tmpl, instance_id=CreatureId("f1"), content=_NoContent(),  # type: ignore[arg-type]
        class_repository=repo,
    )
    assert Ability.STR in c.saving_throw_proficiencies
    assert Ability.CON in c.saving_throw_proficiencies
    assert Ability.DEX not in c.saving_throw_proficiencies
```

- [ ] **Step 2: FAIL** (нет поля / нет параметра).

- [ ] **Step 3: Creature-поле.** В `creature.py` (рядом с `character_class`/`level`):

```python
from dnd.domain.values.ability import Ability  # уже импортирован? проверить
...
    saving_throw_proficiencies: frozenset[Ability] = field(default_factory=frozenset)
```

- [ ] **Step 4: builder.** `build_creature_from_template(..., *, class_repository: ClassRepository | None = None)`; после установки `character_class`:

```python
    if class_repository is not None and template.character_class is not None \
            and class_repository.contains(template.character_class):
        prog = class_repository.load(template.character_class)
        creature.saving_throw_proficiencies = prog.saving_throw_proficiencies
```

(Импорт `ClassRepository` под TYPE_CHECKING.)

- [ ] **Step 5: scenario_builder + composition.** `build_encounter_from_scenario(..., class_repository=None)` → пробросить в `build_creature_from_template`. В `cli/app.py` и `tui/app.py` передать уже существующий `class_repo`/`self._class_repository` в `build_encounter_from_scenario`.

- [ ] **Step 6: level_up.** В `LevelUpService.apply`, после `progression = self._classes.load(...)`, выставить (на случай повышения/смены): `creature.saving_throw_proficiencies = progression.saving_throw_proficiencies`.

- [ ] **Step 7: PASS + регресс** (`pytest -q` — scenario_builder сигнатура изменилась, проверить вызовы).

- [ ] **Step 8: mypy/ruff + commit**

```bash
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -am "feat(t1): Creature.saving_throw_proficiencies + заполнение из класса"
```

---

## Task T1-3: `roll_saving_throw` helper + применение

**Files:** Create `src/dnd/application/engine/saving_throw.py`; Modify `spells/handlers.py`, `encounter.py`; Test `tests/unit/application/test_saving_throw.py`.

- [ ] **Step 1: Failing-тест** (новый файл):

```python
"""T1: единый бросок спасброска с учётом профициентности класса."""
from __future__ import annotations
from dnd.application.engine.saving_throw import roll_saving_throw
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId
# ctx-сборка — как в tests/unit/application/actions/test_attack_action.py::_setup
# (минимальный TurnContext с deps из build_scripted_dependencies).


def _ctx(actor):  # see _setup pattern; here inline minimal
    ...


def test_proficient_save_adds_proficiency() -> None:
    actor = Creature.create(
        id_=CreatureId("h"), name="h",
        abilities=AbilityScores.of(str_=10, dex=10, con=14, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )
    actor.proficiency_bonus = 2
    actor.saving_throw_proficiencies = frozenset({Ability.CON})
    ctx = _ctx(actor)  # rolls=[10] → d20=10
    # CON mod +2, prof +2 → total 14 ≥ DC 13 → success
    assert roll_saving_throw(actor, Ability.CON, dc=13, ctx=ctx) is True


def test_nonproficient_save_no_proficiency() -> None:
    actor = ...  # тот же, без CON в профах
    ctx = _ctx(actor)  # d20=10
    # CON mod +2, без prof → total 12 < 13 → fail
    assert roll_saving_throw(actor, Ability.CON, dc=13, ctx=ctx) is False
```

> Исполнителю: ctx собрать как `_setup` в `test_attack_action.py` (battlefield +
> `build_scripted_dependencies(rolls=[...])` + `TurnContext(...)`), `rolls=[10]`.

- [ ] **Step 2: FAIL** (нет модуля).

- [ ] **Step 3: Реализация** `saving_throw.py`:

```python
"""Единая точка броска спасброска (T1). Учитывает бонус мастерства, если
существо профициентно в этом спасброске (PHB-2024 стр. 9), и адъюстменты
состояний (advantage/disadvantage/numeric)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.modifiers import ModifierTargetKind

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability


def saving_throw_bonus(actor: Creature, ability: Ability) -> int:
    mod = actor.abilities.modifier(ability)
    if ability in actor.saving_throw_proficiencies:
        return mod + actor.proficiency_bonus
    return mod


def roll_saving_throw(
    actor: Creature, ability: Ability, *, dc: int, ctx: TurnContext,
    tags: tuple[str, ...] = ("saving_throw",),
) -> bool:
    bonus = saving_throw_bonus(actor, ability)
    adj = ctx.modifier_applier.to_roll_adjustments(
        ctx.modifier_applier.collect(
            owner_id=actor.id, target_kind=ModifierTargetKind.SAVING_THROW
        )
    )
    roll = ctx.dice_roller.roll(
        DiceExpr.parse(f"d20{bonus + adj.numeric_bonus:+d}"),
        RollContext(
            purpose=RollPurpose.SAVE, actor_id=actor.id,
            advantage=adj.advantage, disadvantage=adj.disadvantage,
            extra_dice=adj.extra_dice, tags=tags,
        ),
    )
    return roll.total >= dc
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Применить в `SaveSpellHandler`** (`spells/handlers.py`): заменить ручной `d20 + save_mod` блок на `roll_saving_throw(target, spell.save_ability, dc=dc, ctx=ctx, tags=("spell_save",))`. Поведение save/half-on-save сохранить (метод возвращает bool — успех). Сверить порядок бросков в тестах (могли «протухнуть» — теперь prof у профициентных целей; монстры — без профов, для них ничего не меняется).

- [ ] **Step 6: Применить в concentration-save** (`encounter.py::_check_concentration`): заменить ручной CON-бросок на `roll_saving_throw(target, Ability.CON, dc=dc, ctx=…)`. ⚠ У `_check_concentration` нет `TurnContext` — он в `_on_downed` (подписчик шины). Вынести бросок: собрать `RollAdjustments` через `self._deps.modifier_applier` напрямую (как сейчас) ИЛИ перегрузить helper на работу с `modifier_applier`+`dice_roller` без ctx. Решение: добавить параметр-перегрузку — функцию `roll_saving_throw_raw(actor, ability, dc, *, dice_roller, modifier_applier) -> bool`, а `roll_saving_throw(...ctx...)` — тонкая обёртка. `_check_concentration` зовёт `_raw`. (Так helper не требует TurnContext там, где его нет.)

- [ ] **Step 7: PASS (вкл. test_concentration.py — пересчитать ролл-бюджет, если prof изменил исход; для монстров без профов — без изменений) + mypy/ruff + commit**

```bash
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -am "feat(t1): roll_saving_throw (prof классов) + применение в spell-save и concentration"
```

---

## Task T1-4: класс `wizard` (d6, L1–3, слоты)

**Files:** Modify `data/content/classes.yaml`; Test `tests/integration/engine/test_wizard_progression.py` (create).

- [ ] **Step 1: Failing-тест:**

```python
"""T1: маг — слоты по уровням через LevelUpService."""
from __future__ import annotations
from pathlib import Path
from dnd.application.engine.features.defaults import default_feature_registry
from dnd.application.engine.progression.level_up import LevelUpService
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus


def _wiz() -> Creature:
    c = Creature.create(
        id_=CreatureId("w"), name="w",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=6, armor_class=12, speed_ft=30,
    )
    c.character_class = "wizard"
    c.level = 1
    c.spellcasting_ability = Ability.INT
    return c


def _svc() -> LevelUpService:
    return LevelUpService(
        class_repository=YamlClassRepository(Path("data/content/classes.yaml")),
        feature_registry=default_feature_registry(),
        event_bus=InMemoryEventBus(),
    )


def test_wizard_slots_grow_by_level() -> None:
    w = _wiz()
    svc = _svc()
    svc.apply(w, to_level=2, ctx=None)
    assert w.spell_slots == {1: 3}
    svc.apply(w, to_level=3, ctx=None)
    assert w.spell_slots == {1: 4, 2: 2}
```

- [ ] **Step 2: FAIL** (нет класса wizard → `LevelUpService` no-op, слоты не растут).

- [ ] **Step 3: classes.yaml** — добавить:

```yaml
- id: wizard
  name: "Волшебник"
  hit_die: "1d6"
  saving_throw_proficiencies: [INT, WIS]
  levels:
    1: { proficiency_bonus: 2, features: [arcane_recovery], spell_slots: { 1: 2 } }
    2: { proficiency_bonus: 2, features: [], spell_slots: { 1: 3 } }
    3: { proficiency_bonus: 2, features: [], spell_slots: { 1: 4, 2: 2 } }
```

- [ ] **Step 4: Фича `arcane_recovery`.** Зарегистрировать в `default_feature_registry` минимальный хендлер (`on_gain` — no-op или инициализация ресурса `arcane_recovery` max=1, recharge LONG_REST). Если регистрация фичи обязательна (FeatureRegistry бросает на неизвестную) — добавить заглушку-хендлер. Проверить: при отсутствии — `features: []` на L1 и оставить `arcane_recovery` на T4. **Решение для T1:** features L1 = `[]` (Spellcasting не моделируем фичей), чтобы не плодить пустой хендлер; слоты дают каст. (Упростить YAML выше: `features: []` на L1.)

- [ ] **Step 5: PASS + mypy/ruff + commit**

```bash
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -am "feat(t1): класс wizard (d6, L1-3, таблица слотов)"
```

---

## Task T1-5: `Ability.requires_area`

**Files:** Modify `application/abilities/ability.py`, `application/abilities/spell_abilities.py`; Test `tests/unit/abilities/test_ability.py` (рядом с существующими).

- [ ] **Step 1: Failing-тесты:**

```python
def test_requires_area_flag() -> None:
    from dnd.application.abilities.ability import Ability
    from dnd.application.dto.action import ActionEconomyCost
    from dnd.domain.values.ability_id import AbilityId
    ab = Ability(
        id=AbilityId("x"), name="X", icon="*", default_hotkey="",
        economy_cost=ActionEconomyCost.ACTION, requires_target=False,
        requires_path=False, requires_area=True, intent_factory=lambda: None,
    )
    assert ab.requires_area is True


def test_target_and_area_mutually_exclusive() -> None:
    import pytest
    from dnd.application.abilities.ability import Ability
    from dnd.application.dto.action import ActionEconomyCost
    from dnd.domain.values.ability_id import AbilityId
    with pytest.raises(ValueError):
        Ability(
            id=AbilityId("x"), name="X", icon="*", default_hotkey="",
            economy_cost=ActionEconomyCost.ACTION, requires_target=True,
            requires_path=False, requires_area=True, intent_factory=lambda: None,
        )
```

- [ ] **Step 2: FAIL.**

- [ ] **Step 3:** В `ability.py` добавить поле `requires_area: bool = False` (после `requires_path`); в `__post_init__` запретить >1 из трёх:

```python
        if sum((self.requires_target, self.requires_path, self.requires_area)) > 1:
            raise ValueError(
                f"Ability {self.id}: requires_target/requires_path/requires_area "
                "взаимоисключающие"
            )
```

- [ ] **Step 4:** В `spell_abilities.py::spell_ability` добавить `requires_area=spell.targeting.kind is TargetKind.AREA` (и `requires_target` оставить `is SINGLE`).

- [ ] **Step 5: PASS + mypy/ruff + commit**

```bash
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -am "feat(t1): Ability.requires_area + spell_ability для AoE"
```

---

## Task T1-6: заклинания в меню + AREA-ветка триггера

**Files:** Modify `interfaces/tui/screens/battle.py`; Test `tests/integration/tui/test_ability_menu.py` (дописать).

- [ ] **Step 1: Заклинания в `ability_ids`.** В `BattleScreen._apply_keymap` (где спеллы кладутся на 1..9) — дополнительно класть их `AbilityId` во временный набор для меню и регистрировать `Ability` в `self._ability_registry` (если ещё нет), чтобы `_open_ability_menu` (источник — `actor.ability_ids`) их видел. Реализация: после сбора `spell_ability(spell, str(i))` — `self._ability_registry.register(ab)` (идемпотентно: пропускать, если id уже зарегистрирован) и добавить `ab.id` в `actor.ability_ids`, если отсутствует. (Дубли не плодить — проверка `in`.)

> Исполнителю: свериться с `AbilityRegistry.register` (бросает на дубль? тогда
> `if ab.id not in registry: register`). `actor.ability_ids` — tuple; добавлять
> неразрушающе: `actor.ability_ids = (*actor.ability_ids, ab.id)` при отсутствии.

- [ ] **Step 2: AREA-ветка в `_trigger_ability`.** Сейчас обрабатываются `requires_target`/`requires_path`. Добавить:

```python
        if ab.requires_area:
            # AoE: вход в существующий BattleMode.AREA (как цифровой хоткей AoE).
            self._pending_ability = ab
            # переиспользовать путь, которым AoE-заклинание входит в AREA
            # (см. как digit-hotkey AoE-спелла открывает AreaModeHandler).
            ... (вызвать тот же _enter_area-путь) ...
            return
```

> Исполнителю: найти, как AoE-заклинание сейчас входит в `BattleMode.AREA`
> (через `_trigger_ability`? или отдельно в on_key для digit). Переиспользовать
> ту же установку `_pending_area_spec`/`enter_mode(AREA)`. Если AoE уже шёл через
> `_trigger_ability` по другому флагу — заменить на `requires_area`.

- [ ] **Step 3: Pilot-тест** (дописать в test_ability_menu.py): маг с AoE-заклинанием в `ability_ids` → `Tab` → меню содержит заклинание; `Enter` на нём → `screen._mode is BattleMode.AREA`. (Сборку мага взять как в существующем `test_tab_opens_ability_menu_in_battle`, добавив `spell_repository` и каст-абилку.)

- [ ] **Step 4: регресс TUI + mypy/ruff + commit**

```bash
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -am "feat(t1): заклинания в меню способностей + AREA-ветка триггера"
```

---

## Task T1-7: контент мага + e2e-смоук

**Files:** Modify `data/content/monsters.yaml`; Test `tests/e2e/test_wizard_play.py` (create).

- [ ] **Step 1: `mage_apprentice` → класс.** В monsters.yaml добавить `character_class: wizard`, `level: 1`, привести `spell_slots: { 1: 2 }` (таблица L1 мага).

- [ ] **Step 2: e2e-смоук** (`tests/e2e/test_wizard_play.py`): загрузить `mage_skirmish` (уже есть, маг vs гоблин) через `build_encounter_from_scenario(..., class_repository=...)`; проверить: маг имеет `character_class == "wizard"`, `saving_throw_proficiencies == {INT, WIS}`, `spell_slots == {1: 2}`, `known_spells` непуст.

```python
@pytest.mark.e2e
def test_mage_scenario_builds_wizard() -> None:
    from pathlib import Path
    from dnd.infrastructure.content.yaml_repository import YamlContentRepository
    from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
    from dnd.application.engine.scenario_builder import build_encounter_from_scenario
    from dnd.composition import build_default_runtime_services
    from dnd.domain.values.ability import Ability
    from dnd.domain.values.faction import Faction
    cdir = Path("data/content")
    repo = YamlContentRepository(cdir)
    enc = build_encounter_from_scenario(
        repo.scenario_by_id("mage_skirmish"), content=repo,
        services=build_default_runtime_services(),
        class_repository=YamlClassRepository(cdir / "classes.yaml"),
    )
    mage = next(c for c, f in enc.factions.items() if f is Faction.PARTY)
    m = enc.participants[mage]
    assert m.character_class == "wizard"
    assert m.saving_throw_proficiencies == frozenset({Ability.INT, Ability.WIS})
    assert m.spell_slots.get(1, 0) >= 2 and m.known_spells
```

- [ ] **Step 3: PASS + полный регресс + commit**

```bash
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -am "feat(t1): mage_apprentice как класс wizard + e2e-смоук"
```

---

## Task T1-8: документация

**Files:** Modify `docs/SPELLS.md`, `docs/ABILITIES.md`, `docs/PROGRESSION.md`, `docs/ROADMAP.md`.

- [ ] **Step 1:** `PROGRESSION.md` — раздел про класс Волшебник (d6, слоты L1-3, спасброски INT/WIS) + профициентные спасброски классов (таблица). `SPELLS.md` — что заклинания доступны и через меню способностей. `ABILITIES.md` — `requires_area` + заклинания в меню. `ROADMAP.md` — веха T1 (✅), T2–T4 (⏳).

- [ ] **Step 2: commit**

```bash
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -am "docs(t1): волшебник + профициентные спасброски + requires_area"
```

---

## Task T1-9: финальная проверка

- [ ] `python3 -m pytest -q` — всё зелёное (новые тесты + не сломаны спасброски/concentration).
- [ ] `python3 -m mypy src && python3 -m ruff check src tests` — чисто.
- [ ] Ручной дым: `dnd play mage_skirmish --tui` → `Tab` показывает заклинания; SINGLE → TARGET, AoE → AREA; каст тратит слот; маг level-up'ится (если добрать XP) с ростом слотов.
- [ ] Спек-покрытие: §2.1 wizard → T1-4; §2.2 спасброски → T1-1/2/3; §2.3 меню/area → T1-5/6; §2.4 контент → T1-7. OK.

---

## Self-Review
- **Покрытие спека:** класс+слоты (T1-4), спасброски-профы (T1-1/2/3), requires_area
  (T1-5), спеллы-в-меню+AREA (T1-6), контент (T1-7), доки (T1-8). Полное.
- **Плейсхолдеры:** места «исполнителю: свериться» — T1-3 step6 (raw-обёртка без
  ctx), T1-6 (точный путь входа в AREA) — это указания сверить существующий код,
  логика и сигнатуры приведены; не заглушки фич.
- **Типы:** `roll_saving_throw(actor, ability, *, dc, ctx)` + `_raw(... dice_roller,
  modifier_applier)`; `Ability.requires_area: bool`; `ClassProgression.
  saving_throw_proficiencies: frozenset[Ability]`; `build_creature_from_template(
  ..., class_repository=None)`; `build_encounter_from_scenario(..., class_repository
  =None)` — согласованы между задачами.
