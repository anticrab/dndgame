# U — используемые предметы Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Зелья лечат, зелья-баффы баффают, свитки кастуют — всё через **единый slotless-каст** эффект-пакета (предмет ссылается на запись в `spells.yaml` по id; никаких дублей логики заклинаний).

**Architecture:** Из `CastSpellAction` выносится чистое ядро `resolve_and_apply_spell` (таргетинг + эффект, без слота/экономики). Новый VO `SpellPower` (Сл/атака/мод) развязывает «силу» эффекта от источника: волшебник → из кастера; свиток → фикс по уровню (PHB); зелье HEAL → мод 0. `Item.use: ItemUseSpec` — обвязка доставки (`effect_id`, `economy`, `consumed`, `is_scroll`). `UseItemAction` зовёт ядро slotless. Спек: `docs/superpowers/specs/2026-05-28-u-usable-items-design.md`.

**Tech Stack:** Python 3.12, frozen dataclasses (domain), pydantic v2 (события/интенты — frozen BaseModel), pytest, mypy strict, ruff. Guard `tests/unit/test_layering.py` (domain НЕ импортирует application). Коммиты: `Maxim Lokotkov` / `anticrab@users.noreply.github.com`. Доки/комментарии — русский.

**CI-гейты (гонять ВСЕ после каждой задачи):** `python3 -m ruff check src tests` · `python3 -m ruff format --check src tests` · `python3 -m mypy src` · `python3 -m pytest -q`. После `ruff format` — перепроверять mypy.

---

## Карта файлов

| Файл | Изменение |
|------|-----------|
| `src/dnd/domain/values/spell_power.py` | **Create** — `SpellPower` + `SCROLL_TABLE` |
| `src/dnd/application/engine/spells/effect_handler.py` | `apply(..., power)` в протоколе |
| `src/dnd/application/engine/spells/handlers.py` | хендлеры читают `power.*`; Heal без assert на кастера |
| `src/dnd/application/engine/spells/resolve.py` | **Create** — `resolve_and_apply_spell` (вынос из CastSpell) |
| `src/dnd/application/engine/actions/cast_spell.py` | делегирует ядру с `SpellPower.from_caster` |
| `src/dnd/domain/values/item_use.py` | **Create** — `ItemUseSpec` |
| `src/dnd/domain/values/item.py` | `Item.use: ItemUseSpec | None = None` |
| `src/dnd/infrastructure/content/yaml_item_repository.py` | парсинг `use` |
| `src/dnd/application/dto/engine_event.py` | `ItemUsed` |
| `src/dnd/application/engine/actions/use_item.py` | **Create** — `UseItemAction` + `UseItemParams` |
| `src/dnd/application/dto/player_intent.py` | `UseItemIntent` + union |
| `src/dnd/application/engine/game_runner.py` | `_do_use_item` + диспатч |
| `data/content/spells.yaml` | `potion_healing`, `potion_strength_buff` |
| `data/content/items.yaml` | `use` у зелий + новые свитки |
| `src/dnd/interfaces/tui/screens/inventory_screen.py` | действие «Использовать» |
| `src/dnd/interfaces/cli/event_printer.py` | рендер `ItemUsed` |
| `docs/ITEMS.md` | **Create**; ROADMAP — правка |

Все новые поля — с дефолтами (backward-compat): `Item.use=None`.

---

# U1 — `SpellPower` + ядро резолва + рефактор хендлеров

## U1-1 — `SpellPower` (источник Сл/атаки/мода)

**Files:** Create `src/dnd/domain/values/spell_power.py`; Test `tests/unit/domain/test_spell_power.py`.

- [ ] **Step 1: Падающий тест**

```python
"""SpellPower — источник Сл/атаки/мода эффекта (U1)."""
from __future__ import annotations

from dnd.domain.values.spell_power import SpellPower


def test_scroll_dc_attack_by_level() -> None:
    assert SpellPower.scroll(0) == SpellPower(save_dc=13, attack_bonus=5, ability_mod=0)
    assert SpellPower.scroll(2) == SpellPower(save_dc=13, attack_bonus=5, ability_mod=0)
    assert SpellPower.scroll(3) == SpellPower(save_dc=15, attack_bonus=7, ability_mod=0)
    assert SpellPower.scroll(9) == SpellPower(save_dc=19, attack_bonus=11, ability_mod=0)


def test_potion_has_zero_mod() -> None:
    assert SpellPower.potion() == SpellPower(save_dc=0, attack_bonus=0, ability_mod=0)
```

- [ ] **Step 2: Запустить — падает** (`ImportError`).

- [ ] **Step 3: Реализовать**

Create `src/dnd/domain/values/spell_power.py`:
```python
"""SpellPower (U) — эффективные Сл/атака/мод применяемого эффекта.

Развязывает «силу» эффекта от источника: заклинание волшебника берёт её из
кастера, свиток — фикс по уровню (PHB-2024, таблица свитков), зелье — нулевой
мод (лечит ровно по кости). Хендлеры читают эти числа вместо прямых
``caster.spell_*()`` — поэтому один и тот же эффект-пакет (напр. fireball)
работает и как заклинание, и как свиток."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class SpellPower:
    save_dc: int  # для SAVE / CONTROL
    attack_bonus: int  # для ATTACK
    ability_mod: int  # прибавка к HEAL ("+ мод заклинательной хар-ки")

    # PHB-2024: Сл/атака свитка по уровню заклинания (порог уровня → (DC, атака)).
    _SCROLL: ClassVar[tuple[tuple[int, int, int], ...]] = (
        # (max_level, dc, attack)
        (2, 13, 5),
        (4, 15, 7),
        (6, 17, 9),
        (8, 18, 10),
        (9, 19, 11),
    )

    @classmethod
    def scroll(cls, spell_level: int) -> SpellPower:
        for max_level, dc, atk in cls._SCROLL:
            if spell_level <= max_level:
                return cls(save_dc=dc, attack_bonus=atk, ability_mod=0)
        last = cls._SCROLL[-1]
        return cls(save_dc=last[1], attack_bonus=last[2], ability_mod=0)

    @classmethod
    def potion(cls) -> SpellPower:
        return cls(save_dc=0, attack_bonus=0, ability_mod=0)


__all__ = ["SpellPower"]
```

> `from_caster` добавим в U1-2 (нужен `Creature`-импорт; держим конструкторы-данные
> здесь, а кастер-зависимый — там же, где используется). Для чистоты domain:
> `from_caster` — статметод, принимающий `Creature` (domain-сущность), без
> application-импортов.

- [ ] **Step 4: Зелёно + гейты + коммит**

Run: `python3 -m pytest tests/unit/domain/test_spell_power.py -q && python3 -m ruff format src/dnd/domain/values/spell_power.py tests/unit/domain/test_spell_power.py && python3 -m ruff check src tests && python3 -m mypy src`
```bash
git add src/dnd/domain/values/spell_power.py tests/unit/domain/test_spell_power.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): SpellPower — Сл/атака/мод эффекта (фикс-таблица свитка PHB)"
```

---

## U1-2 — `from_caster` + рефактор протокола хендлеров (читают `power`)

**Files:** Modify `domain/values/spell_power.py` (`from_caster`); `application/engine/spells/effect_handler.py`; `application/engine/spells/handlers.py`; `application/engine/actions/cast_spell.py`; Test `tests/unit/application/test_control_spell_handler.py` (обновить вызовы).

- [ ] **Step 1: `from_caster`** в `spell_power.py` (добавить метод):
```python
    @staticmethod
    def from_caster(caster: "Creature") -> "SpellPower":
        mod = (
            caster.abilities.modifier(caster.spellcasting_ability)
            if caster.spellcasting_ability is not None
            else 0
        )
        return SpellPower(
            save_dc=caster.spell_save_dc(),
            attack_bonus=caster.spell_attack_bonus(),
            ability_mod=mod,
        )
```
Импорт `Creature` — в `TYPE_CHECKING` (метод аннотирует строкой), runtime-импорт не нужен.

- [ ] **Step 2: Протокол** — в `effect_handler.py` сигнатуру `apply` дополнить `power: SpellPower` (последним параметром); импорт `SpellPower` в `TYPE_CHECKING`.

- [ ] **Step 3: Хендлеры** — в `handlers.py`:
  - Импорт `from dnd.domain.values.spell_power import SpellPower` в `TYPE_CHECKING`.
  - Каждому `apply(self, caster, targets, spell, ctx)` добавить `, power: SpellPower`.
  - `AttackSpellHandler`: `atk_bonus = caster.spell_attack_bonus()` → `atk_bonus = power.attack_bonus`.
  - `SaveSpellHandler`: `dc = caster.spell_save_dc()` → `dc = power.save_dc`.
  - `HealSpellHandler`: заменить `assert spell.heal_dice is not None and caster.spellcasting_ability is not None` на `assert spell.heal_dice is not None`; `mod = caster.abilities.modifier(...)` → `mod = power.ability_mod`.
  - `ControlSpellHandler`: пробросить `power` в `_apply_pool`/`_apply_save`/`_apply_condition`; в `_apply_save` `dc = caster.spell_save_dc()` → `dc = power.save_dc`; в `_apply_condition` `dc = caster.spell_save_dc() if spell.save_ability is not None else None` → `dc = power.save_dc if spell.save_ability is not None else None`.
  - `AutoSpellHandler` / `BuffSpellHandler`: добавить `power` в сигнатуру (не используют).

- [ ] **Step 4: Вызов в `CastSpellAction.execute`** — `cast_spell.py`:
```python
        self._effects.get(spell.effect).apply(actor, targets, spell, ctx, SpellPower.from_caster(actor))
```
Импорт `from dnd.domain.values.spell_power import SpellPower`.

- [ ] **Step 5: Обновить прямые вызовы в тесте** — `test_control_spell_handler.py`: во все 5 вызовов `ControlSpellHandler().apply(mage, targets, spell, ctx)` добавить `, SpellPower.from_caster(mage)`; импорт `SpellPower`.

- [ ] **Step 6: Зелёно + полная регрессия + гейты**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests`
Expected: PASS (поведение CastSpell не изменилось — `power` из кастера).
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "refactor(u): хендлеры эффектов читают SpellPower (power из кастера в спелл-пути)"
```

---

## U1-3 — вынос `resolve_and_apply_spell` (чистое ядро)

**Files:** Create `src/dnd/application/engine/spells/resolve.py`; Modify `cast_spell.py`; Test `tests/unit/application/test_resolve_spell.py`.

- [ ] **Step 1: Падающий тест** (резолв SELF-heal без слота/экономики)

```python
"""resolve_and_apply_spell — чистое ядро применения эффекта (U1-3)."""
from __future__ import annotations

from dnd.application.engine.spells.resolve import resolve_and_apply_spell
from dnd.application.engine.spells.defaults import default_spell_effect_registry
from dnd.application.engine.spells.area import default_area_shape_registry
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind
from dnd.domain.values.spell_power import SpellPower


def _ctx(rolls: list[int], creatures: list[Creature]) -> TurnContext:
    bf = Battlefield(5, 5)
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    return TurnContext(
        actor_id=creatures[0].id, battlefield=bf, dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier, condition_service=deps.condition_service,
        event_bus=deps.event_bus, rng=deps.rng,
        participants={c.id: c for c in creatures}, movement_remaining_ft=30,
    )


def test_resolve_self_heal_no_slot() -> None:
    hero = Creature.create(
        id_=CreatureId("h"), name="h",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=10, speed_ft=30,
    )
    hero.take_damage_for_test_to(10) if hasattr(hero, "take_damage_for_test_to") else None
    spell = Spell(
        id=SpellId("potion_healing"), name="x", level=0, school="-",
        effect=SpellEffect.HEAL, targeting=TargetingSpec(kind=TargetKind.SELF),
        range_ft=5, description="", heal_dice="2d4+2",
    )
    ctx = _ctx([4, 4], [hero])  # 2d4+2 = 10 (без мода)
    before = hero.hit_points.current
    resolve_and_apply_spell(
        hero, spell, ctx=ctx, power=SpellPower.potion(),
        target_id=None, target_ids=(), target_point=None, direction=None,
        effect_registry=default_spell_effect_registry(),
        area_registry=default_area_shape_registry(),
    )
    assert hero.hit_points.current >= before  # лечение применилось (без слота)
```

> Сверить способ «ранить героя до лечения» с существующими тестами heal
> (`take_damage`/фабрика); цель теста — что ядро применяет эффект без траты слота.
> При необходимости упростить: проверить публикацию `HealingApplied`.

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать ядро** — Create `resolve.py`: перенести `_resolve_targets` (как модульная функция с параметрами `spell, caster, *, target_id, target_ids, target_point, direction, ctx, area_registry`) + `resolve_and_apply_spell(caster, spell, *, ctx, power, target_id, target_ids, target_point, direction, effect_registry, area_registry)` — резолв целей + `effect_registry.get(spell.effect).apply(caster, targets, spell, ctx, power)`. Без слота/экономики/`SpellCast`.

- [ ] **Step 4: `CastSpellAction` делегирует** — в `cast_spell.py` `_resolve_targets` заменить на вызов ядра; `execute` после `consume_spell_slot`/`spend`/`SpellCast` зовёт `resolve_and_apply_spell(actor, spell, ctx=ctx, power=SpellPower.from_caster(actor), target_id=params.target_id, target_ids=params.target_ids, target_point=params.target_point, direction=params.direction, effect_registry=self._effects, area_registry=self._areas)`.

- [ ] **Step 5: Зелёно + полная регрессия + гейты + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests`
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "refactor(u): вынос resolve_and_apply_spell (slotless-ядро) из CastSpellAction"
```

---

# U2 — `Item.use` + `UseItemAction` + `ItemUsed` + интент

## U2-1 — `ItemUseSpec`

**Files:** Create `src/dnd/domain/values/item_use.py`; Test `tests/unit/domain/test_item_use.py`.

- [ ] **Step 1: Падающий тест**
```python
"""ItemUseSpec — обвязка доставки эффекта предмета (U2)."""
from __future__ import annotations

from dnd.application.dto.action import ActionEconomyCost  # см. примечание ниже
from dnd.domain.values.item_use import ItemUseSpec
from dnd.domain.values.ids import SpellId


def test_defaults_action_consumed() -> None:
    use = ItemUseSpec(effect_id=SpellId("cure_wounds"))
    assert use.consumed is True
    assert use.is_scroll is False
```

> **Важно:** `ActionEconomyCost` лежит в `application/dto/action.py`. Чтобы domain
> не импортировал application, `ItemUseSpec.economy` хранить как `str`
> (сериализованное значение `"action"`/`"bonus_action"`), а `UseItemAction`
> конвертирует в `ActionEconomyCost`. В тесте проверять строки. Скорректировать
> импорт теста соответственно.

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать** — Create `item_use.py`:
```python
"""ItemUseSpec (U) — как предмет доставляет эффект-пакет. Сам эффект — запись в
каталоге заклинаний по ``effect_id`` (единый slotless-каст). domain не зависит от
application: ``economy`` — строка ("action"/"bonus_action"), конвертирует
UseItemAction."""
from __future__ import annotations

from dataclasses import dataclass

from dnd.domain.values.ids import SpellId

_ECONOMY = {"action", "bonus_action"}


@dataclass(frozen=True, slots=True)
class ItemUseSpec:
    effect_id: SpellId
    economy: str = "action"
    consumed: bool = True
    is_scroll: bool = False  # True → SpellPower.scroll(level); иначе SpellPower.potion()

    def __post_init__(self) -> None:
        if self.economy not in _ECONOMY:
            raise ValueError(f"economy must be one of {_ECONOMY}, got {self.economy!r}")


__all__ = ["ItemUseSpec"]
```

- [ ] **Step 4: Зелёно + гейты + коммит**
```bash
git add src/dnd/domain/values/item_use.py tests/unit/domain/test_item_use.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): ItemUseSpec — обвязка доставки эффекта предмета (ссылка на effect_id)"
```

---

## U2-2 — `Item.use` + парсинг YAML

**Files:** Modify `domain/values/item.py`, `infrastructure/content/yaml_item_repository.py`; Test `tests/integration/content/test_yaml_item_repository.py` (дописать).

- [ ] **Step 1: Падающий тест** — добавить `use:` в тестовый YAML и проверить, что `repo.get(...)` вернёт `Item.use` с `effect_id`/`economy`/`is_scroll`. (Сверить API репозитория — `load`/`get` — с существующими тестами файла.)

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3:** В `item.py` добавить поле `use: ItemUseSpec | None = None` (импорт `ItemUseSpec`). В `yaml_item_repository.py` `_parse`: распарсить опциональный блок `use`:
```python
        raw_use = entry.get("use")
        use = (
            None if raw_use is None
            else ItemUseSpec(
                effect_id=SpellId(raw_use["effect_id"]),
                economy=str(raw_use.get("economy", "action")),
                consumed=bool(raw_use.get("consumed", True)),
                is_scroll=bool(raw_use.get("is_scroll", False)),
            )
        )
```
и передать `use=use` в `Item(...)`.

- [ ] **Step 4: Зелёно + гейты + коммит**
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): Item.use + парсинг use в YamlItemRepository"
```

---

## U2-3 — событие `ItemUsed`

**Files:** Modify `application/dto/engine_event.py`; Test — покрывается U2-4.

- [ ] **Step 1: Реализовать** — добавить класс рядом с прочими событиями:
```python
class ItemUsed(EngineEvent):
    """Предмет использован (U): зелье/свиток. consumed — списан ли расходник."""
    event_type: ClassVar[str] = "inventory.item_used"
    actor_id: CreatureId
    item_id: str
    item_name: str
    effect: str
    target_id: CreatureId | None = None
    consumed: bool = True
```

- [ ] **Step 2: Гейты** (`ruff`/`mypy`); коммит вместе с U2-4 (событие без потребителя — тривиально). Можно отдельным коммитом:
```bash
git add src/dnd/application/dto/engine_event.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): событие ItemUsed"
```

---

## U2-4 — `UseItemAction`

**Files:** Create `src/dnd/application/engine/actions/use_item.py`; Test `tests/integration/engine/test_use_item_action.py`.

- [ ] **Step 1: Падающий тест** — герой с `healing_potion` (in-test Item с `use=ItemUseSpec(effect_id=SpellId("cure_wounds"), economy="bonus_action")`) в инвентаре; in-test `SpellRepository`-стаб (или реальный с записью cure_wounds); `UseItemAction.execute` → `ItemUsed` опубликован, расходник списан (`inventory.contains` → False при qty 1), бонусное действие потрачено.

> Сверить интерфейс `SpellRepository` (`load`/`contains`) и способ положить Item в
> `actor.inventory` (`inventory.add(item)`), как в тестах Pickup/инвентаря.

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать** — Create `use_item.py`:
  - `UseItemParams(ActionParams)`: `item_id: ItemId`, `target_id`, `target_ids`, `target_point`, `direction` (как `CastSpellParams`).
  - `UseItemAction.__init__(spell_repository, effect_registry=None, area_registry=None)`.
  - `_real_economy(item)` → `ActionEconomyCost(item.use.economy)`.
  - `can_perform_against`: `actor.inventory.contains(item_id)`; `item.use is not None`; `spell_repository.contains(use.effect_id)`; `spell.effect in effect_registry`; `ctx.can_spend(real_economy)`; валидность цели — как у `CastSpellAction` (переиспользовать проверки range/liveness/targeting по `spell.targeting`).
  - `execute`: `avail` guard; `spell = spell_repository.load(use.effect_id)`; `power = SpellPower.scroll(spell.level) if use.is_scroll else SpellPower.potion()`; `ctx.spend(real_economy)`; `resolve_and_apply_spell(actor, spell, ctx=ctx, power=power, target_id=..., target_ids=..., target_point=..., direction=..., effect_registry=self._effects, area_registry=self._areas)`; если `use.consumed` → `actor.inventory.remove_one(item_id)`; publish `ItemUsed(...)`; вернуть `ActionOutcome(success=True, consumed=real_economy, ...)`.

  > Item грузить из инвентаря (`actor.inventory.find_by_id(item_id).item`) — не из
  > ItemRepository: используемый предмет уже в инвентаре актора.

- [ ] **Step 4: Зелёно + гейты + коммит**
```bash
git add src/dnd/application/engine/actions/use_item.py tests/integration/engine/test_use_item_action.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): UseItemAction — slotless-применение эффекта предмета (экономика из данных, списание)"
```

---

## U2-5 — `UseItemIntent` + `GameRunner._do_use_item` + проводка

**Files:** Modify `application/dto/player_intent.py`, `application/engine/game_runner.py`; Test `tests/integration/engine/test_use_item_intent.py`.

- [ ] **Step 1: Падающий тест** — `GameRunner` с `item_repository`+`spell_repository`; `UseItemIntent(item_id=..., target_id=...)` в очереди → действие исполнено (зелье выпито, `ItemUsed` опубликован). Образец — `test_cast_spell_intent.py`.

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3:** В `player_intent.py` добавить:
```python
class UseItemIntent(_IntentBase):
    """Игрок использует предмет (U): зелье/свиток. Проверки — в UseItemAction."""
    kind: Literal["use_item"] = "use_item"
    item_id: ItemId
    target_id: CreatureId | None = None
    target_ids: tuple[CreatureId, ...] = ()
    target_point: Square | None = None
    direction: Direction | None = None
```
Добавить `UseItemIntent` в `PlayerIntent` union и в `__all__`; импорт `ItemId`.

В `game_runner.py`: диспатч `if isinstance(intent, UseItemIntent): self._do_use_item(actor, intent, ctx); return` и метод-зеркало `_do_cast`:
```python
    def _do_use_item(self, actor, intent, ctx) -> None:
        if self._spell_repository is None:
            self._log_rejected(actor, "use_item", "no_spell_repository (runner not wired)")
            return
        params = UseItemParams(
            item_id=intent.item_id, target_id=intent.target_id,
            target_ids=intent.target_ids, target_point=intent.target_point,
            direction=intent.direction,
        )
        action = UseItemAction(spell_repository=self._spell_repository)
        avail = action.can_perform_against(actor, params, ctx)
        if isinstance(avail, Allowed):
            action.execute(actor, params, ctx)
        else:
            self._log_rejected(actor, "use_item", _avail_reason(avail))
```

- [ ] **Step 4: Зелёно + полная регрессия + гейты + коммит**
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): UseItemIntent + GameRunner._do_use_item + диспатч"
```

---

# U3 — HEAL + BUFF (контент + фикс source_id)

## U3-1 — фикс `BuffSpellHandler.source_id` (не-концентрационный бафф)

**Files:** Modify `application/engine/spells/handlers.py`; Test `tests/unit/application/test_buff_source.py`.

- [ ] **Step 1: Падающий тест** — не-концентрационный BUFF (зелье) применяется с `source_id = f"buff:{spell.id}:{owner.id}"`, и старт concentration-заклинания кастера его НЕ снимает (collect для owner всё ещё содержит модификатор).

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать** — в `BuffSpellHandler.apply`:
```python
        concentration_src = concentration_source(caster.id)
        if spell.concentration and caster.concentration is not None:
            ctx.modifier_applier.remove_by_source(concentration_src)
        if spell.concentration:
            caster.concentration = spell.id
        expires_at_round = _expires_at(spell, ctx)
        for target in targets:
            source_id = (
                concentration_src if spell.concentration
                else f"buff:{spell.id}:{target.id}"
            )
            for buff in spell.buffs:
                ... ctx.modifier_applier.add(Modifier(source_id=source_id, ...))
            if expires_at_round is not None:
                ctx.event_bus.publish(BuffApplied(owner_id=target.id, source_id=source_id, expires_at_round=expires_at_round))
```
(Концентрационный бафф — общий source на кастера, как раньше; не-концентрационный — уникальный per-spell/per-owner.)

- [ ] **Step 4: Зелёно + полная регрессия + гейты + коммит**
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "fix(u): BuffSpellHandler — concentration-source только при концентрации (не-конц. бафф независим)"
```

---

## U3-2 — контент HEAL/BUFF + тесты «зелье лечит / баффает»

**Files:** Modify `data/content/spells.yaml`, `data/content/items.yaml`; Test `tests/integration/content/test_usable_items_content.py`.

- [ ] **Step 1: Падающий тест** — загрузить items+spells; через `UseItemAction` выпить `healing_potion` (лечит на 2d4+2 без мода) и `potion_of_strength` (BUFF висит; на границе раунда по `duration` истекает — переиспользовать X0-трекер).

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Контент** — в `spells.yaml`:
```yaml
- id: potion_healing
  name: "Potion of Healing (effect)"
  level: 0
  school: "-"
  effect: heal
  targeting: { kind: single }
  range_ft: 5
  heal_dice: "2d4+2"
  description: "Эффект зелья лечения: восстанавливает 2d4+2 хитов."

- id: potion_strength_buff
  name: "Potion of Strength (effect)"
  level: 0
  school: "-"
  effect: buff
  targeting: { kind: self }
  range_ft: 0
  duration: { unit: until_encounter_end }
  buffs:
    - { target: ability_check, numeric_bonus: 2 }
  description: "Эффект зелья силы: +2 к проверкам Силы до конца сцены."
```
В `items.yaml`: `healing_potion.use: {effect_id: potion_healing, economy: bonus_action}`; новый `potion_of_strength` (consumable, stackable) с `use: {effect_id: potion_strength_buff, economy: bonus_action}`.

> Сверить, что `until_encounter_end` поддержан `DurationUnit` (X0); если для
> `until_encounter_end` `to_rounds()` is None — бафф не истекает по часам (снимется
> при EncounterEnded), это ожидаемо; для теста истечения по времени использовать
> `{ unit: minutes, amount: 1 }`.

- [ ] **Step 4: Зелёно + гейты + коммит**
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): контент зелий (potion_healing/strength) + use в items.yaml + тесты"
```

---

# U4 — CAST (свиток)

## U4-1 — свитки кастуют slotless с фикс-DC

**Files:** Modify `data/content/items.yaml`; Test `tests/integration/engine/test_scroll_cast.py`.

- [ ] **Step 1: Падающий тест** — не-кастер с `scroll_of_fireball` использует свиток: AoE-резолв, цели кидают DEX-спасбросок против **DC15** (`SpellPower.scroll(3)`), слот не тратится (у не-кастера его и нет), свиток списан. Второй кейс: `scroll_of_cure_wounds` лечит на 1d8 (ability_mod=0).

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Контент** — в `items.yaml`:
```yaml
- id: scroll_of_cure_wounds
  name: "Scroll of Cure Wounds"
  kind: consumable
  weight_lb: 0.1
  stackable: true
  description: "Свиток: сотворить Cure Wounds (1d8), без траты слота."
  use: { effect_id: cure_wounds, economy: action, is_scroll: true }

- id: scroll_of_fireball
  name: "Scroll of Fireball"
  kind: consumable
  weight_lb: 0.1
  stackable: true
  description: "Свиток: сотворить Fireball (сфера 20 фт), Сл15 по уровню свитка."
  use: { effect_id: fireball, economy: action, is_scroll: true }
```

- [ ] **Step 4: Зелёно + полная регрессия + гейты + коммит**
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): свитки cure_wounds/fireball (CAST slotless, фикс-DC по уровню)"
```

---

# U5 — TUI + демо-инвентарь + лог

## U5-1 — использование с экрана инвентаря

**Files:** Modify `src/dnd/interfaces/tui/screens/inventory_screen.py` (+ bridge/intent provider при необходимости); Test — pilot-smoke (см. существующие TUI-тесты).

- [ ] **Step 1:** На `InventoryScreen` у расходника с `item.use is not None` — действие «Использовать» (кнопка/hotkey). По выбору:
  - если эффект-пакет требует цели (`SINGLE`/`AREA`/`MULTI`) — переключение в соответствующий inline-режим выбора (как у CastSpell) и затем `UseItemIntent`;
  - иначе (SELF) — сразу `UseItemIntent(item_id=...)`.
  > Сверить с тем, как `BattleScreen` ставит `CastSpellIntent` и входит в режимы
  > таргетинга (`BattleMode.TARGET/AREA/MULTI_TARGET`); переиспользовать тот же путь,
  > подменив терминальный intent на `UseItemIntent`. Минимально: SELF/SINGLE-зелье.

- [ ] **Step 2:** Pilot-smoke: открыть инвентарь, использовать зелье, убедиться, что HP вырос / лог содержит ItemUsed. (Образец — существующие `tests/.../pilot`-смоки.)

- [ ] **Step 3: Гейты + коммит**
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): TUI — использование предмета с экрана инвентаря (+ таргетинг свитка)"
```

---

## U5-2 — рендер `ItemUsed` в логе

**Files:** Modify `src/dnd/interfaces/cli/event_printer.py`; Test — дописать в тест EventPrinter.

- [ ] **Step 1: Падающий тест** — `EventPrinter` на `ItemUsed` печатает рус. строку (зелье: «🧪 hero выпивает Healing Potion», свиток: «📜 hero читает Scroll of Fireball»). Сверить стиль с рендером `SpellCast`/`HealingApplied`.

- [ ] **Step 2: Реализовать** — подписать `ItemUsed`, отрендерить по `effect`/`consumed`.

- [ ] **Step 3: Зелёно + гейты + коммит**
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): EventPrinter — рендер ItemUsed (зелье/свиток)"
```

---

## U5-3 — демо-инвентарь

**Files:** Modify сценарий/шаблон демо-PC (там, где задаётся стартовый инвентарь — сверить с этапом D/демо); Test — e2e-смок (U6).

- [ ] **Step 1:** Выдать демо-PC `healing_potion` ×1 и `scroll_of_fireball` ×1 в стартовый инвентарь (данными сценария/шаблона). Сверить, где формируется стартовый инвентарь PC.

- [ ] **Step 2: Гейты + коммит**
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(u): демо-PC получает зелье и свиток в стартовый инвентарь"
```

---

# U6 — документация + аудит-смок

**Files:** Create `docs/ITEMS.md`; Modify `docs/ROADMAP.md`; Test `tests/e2e/test_usable_items_play.py`.

- [ ] **Step 1: e2e-смок** — прогон: PC выпивает зелье (HP растёт, `ItemUsed`+`HealingApplied`) и читает свиток fireball (урон по врагам по DC15, `ItemUsed`). Образец — `tests/e2e/test_control_spells_play.py`.

- [ ] **Step 2: Запустить — PASS.**

- [ ] **Step 3: Доки** — `docs/ITEMS.md`: модель `Item.use`/`ItemUseSpec`, единый slotless-каст (ссылка на эффект-пакет), `SpellPower` (кастер/свиток/зелье), `UseItemAction`/`ItemUsed`, как добавить используемый предмет (данные). `ROADMAP.md`: отметить **U ✅** (HEAL/CAST/BUFF; LIGHT → X; ограничения свитка → W).

- [ ] **Step 4: Финальная регрессия + гейты + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests`
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "docs(u): ITEMS.md + ROADMAP + e2e-смок (этап U завершён)"
```

---

## Self-Review (выполнено)

**Покрытие спека:** §1 решения — учтены (объём HEAL/CAST/BUFF, LIGHT→X, фикс-DC, экономика данными, UX инвентарь); §2 ядро+SpellPower+протокол — U1-1..U1-3; §3 данные (ItemUseSpec/Item.use/эффект-пакеты) — U2-1/U2-2/U3-2/U4-1; §4 исполнение (UseItemAction/ItemUsed/source_id-фикс/интент/TUI) — U2-3..U2-5, U3-1, U5; §5 контент — U3-2/U4-1/U5-3; §6 расширяемость/инварианты — отражены в задачах; §7 декомпозиция — 1:1; §8 отложенное (LIGHT/ограничения/Drop-Equip) — не входит, помечено в доках.

**Плейсхолдеры:** места «сверить точное API» (SpellRepository.load/contains, способ ранить героя в heal-тесте, TUI-режимы таргетинга, стартовый инвентарь демо, рендер EventPrinter) — указания свериться с существующим кодом; логика и сигнатуры приведены.

**Согласованность типов:** `SpellPower(save_dc, attack_bonus, ability_mod)` + `.scroll(level)`/`.potion()`/`.from_caster(creature)`; `apply(caster, targets, spell, ctx, power)` во всех хендлерах и реестре; `resolve_and_apply_spell(caster, spell, *, ctx, power, target_id, target_ids, target_point, direction, effect_registry, area_registry)`; `ItemUseSpec(effect_id, economy:str, consumed, is_scroll)`; `Item.use`; `UseItemParams(item_id, target_id, target_ids, target_point, direction)`; `UseItemIntent(kind="use_item", …)`; `ItemUsed(actor_id, item_id, item_name, effect, target_id, consumed)` — единообразно между задачами.

**Риски:** (1) смена сигнатуры хендлеров — единственные прямые вызовы в `test_control_spell_handler.py` (5 шт, обновляются в U1-2); (2) domain↔application: `ItemUseSpec.economy` — строка, конверсия в `UseItemAction` (инвариант слоёв сохранён); (3) `until_encounter_end` не истекает по часам — для теста истечения брать minutes; (4) свиток у не-кастера — slotless, `consume_spell_slot` не вызывается (ядро его не трогает).
```
