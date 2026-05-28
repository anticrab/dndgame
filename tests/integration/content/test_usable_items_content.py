"""U3-2: контент HEAL/BUFF — зелье лечения и зелье силы.

Проверяем сквозную связку YAML→ItemUseSpec→UseItemAction:

* ``healing_potion`` ссылается на ``potion_healing`` (HEAL, 2d4+2) — выпивание
  восстанавливает HP, расходник списан, ``ItemUsed`` опубликован;
* ``potion_of_strength`` ссылается на ``potion_strength_buff`` (BUFF, +2 к
  проверкам Силы) — после выпивания модификатор виден в ``modifier_applier``
  с per-spell/per-owner source_id (U3-1).
"""

from __future__ import annotations

from pathlib import Path

from dnd.application.dto.engine_event import HealingApplied, ItemUsed
from dnd.application.engine.actions.use_item import UseItemAction, UseItemParams
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.item import ItemId
from dnd.domain.values.modifiers import ModifierTargetKind
from dnd.domain.values.square import Square
from dnd.infrastructure.content.yaml_item_repository import YamlItemRepository
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_DATA = Path(__file__).resolve().parents[3] / "data" / "content"
_ITEMS = _DATA / "items.yaml"
_SPELLS = _DATA / "spells.yaml"


def _hero() -> Creature:
    return Creature.create(
        id_="hero",
        name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=8, wis=10, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=30,
    )


def _ctx(hero: Creature, rolls: list[int]) -> TurnContext:
    bf = Battlefield(5, 5)
    bf.place_creature(hero.id, Square(2, 2))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    return TurnContext(
        actor_id=hero.id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={hero.id: hero},
        movement_remaining_ft=30,
    )


def test_healing_potion_heals_and_logs_item_used() -> None:
    hero = _hero()
    hero.hit_points = hero.hit_points.take_damage(15)  # 20 → 5
    items = YamlItemRepository(_ITEMS)
    spells = YamlSpellRepository(_SPELLS)
    hero.inventory.add(items.load(ItemId("healing_potion")))
    ctx = _ctx(hero, rolls=[4, 4])  # 2d4 = 8, +2 = 10
    used: list[ItemUsed] = []
    healed: list[HealingApplied] = []
    ctx.event_bus.subscribe(ItemUsed, used.append)
    ctx.event_bus.subscribe(HealingApplied, healed.append)
    action = UseItemAction(spells)
    out = action.execute(
        hero,
        UseItemParams(item_id=ItemId("healing_potion"), target_id=hero.id),
        ctx,
    )
    assert out.success
    assert used and used[0].effect == "heal"
    assert healed and healed[0].amount == 10  # 2d4(4+4)+2
    assert hero.hit_points.current == 15  # 5 + 10
    assert hero.inventory.contains(ItemId("healing_potion")) is False


def test_potion_of_strength_applies_buff_with_own_source() -> None:
    hero = _hero()
    items = YamlItemRepository(_ITEMS)
    spells = YamlSpellRepository(_SPELLS)
    hero.inventory.add(items.load(ItemId("potion_of_strength")))
    ctx = _ctx(hero, rolls=[1])
    used: list[ItemUsed] = []
    ctx.event_bus.subscribe(ItemUsed, used.append)
    action = UseItemAction(spells)
    out = action.execute(hero, UseItemParams(item_id=ItemId("potion_of_strength")), ctx)
    assert out.success
    assert used and used[0].effect == "buff"
    # Модификатор виден на проверках Силы, source_id — собственный (не concentration).
    mods = ctx.modifier_applier.collect(
        owner_id=hero.id, target_kind=ModifierTargetKind.ABILITY_CHECK
    )
    assert len(mods) == 1
    assert mods[0].source_id == "buff:potion_strength_buff:hero"
    assert hero.inventory.contains(ItemId("potion_of_strength")) is False
