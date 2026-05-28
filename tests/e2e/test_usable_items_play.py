"""E2E U: PC выпивает зелье и читает свиток.

Сценарий по образцу :mod:`test_control_spells_play`:

* PC (не-кастер, чтобы тест в т.ч. проверял свиток у не-кастера) с
  ``healing_potion`` и ``scroll_of_fireball`` в инвентаре;
* выпивает зелье на себя → ``ItemUsed`` + ``HealingApplied``, HP вырос;
* читает свиток на скопление гоблинов → ``ItemUsed`` + ``DamageDealt`` по
  всем в зоне (slotless, DC по таблице PHB)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.engine_event import DamageDealt, HealingApplied, ItemUsed
from dnd.application.engine.actions.use_item import UseItemAction, UseItemParams
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.item import ItemId
from dnd.domain.values.square import Square
from dnd.infrastructure.content.yaml_item_repository import YamlItemRepository
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_DATA = Path("data/content")


@pytest.mark.e2e
def test_pc_drinks_potion_then_reads_scroll() -> None:
    items = YamlItemRepository(_DATA / "items.yaml")
    spells = YamlSpellRepository(_DATA / "spells.yaml")
    hero = Creature.create(
        id_=CreatureId("hero"),
        name="Hero",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
    )
    hero.hit_points = hero.hit_points.take_damage(15)  # 20 → 5
    hero.inventory.add(items.load(ItemId("healing_potion")))
    hero.inventory.add(items.load(ItemId("scroll_of_fireball")))
    g1 = Creature.create(
        id_=CreatureId("g1"),
        name="g1",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=50,
        armor_class=13,
        speed_ft=30,
    )
    g2 = Creature.create(
        id_=CreatureId("g2"),
        name="g2",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=50,
        armor_class=13,
        speed_ft=30,
    )
    bf = Battlefield(10, 10)
    bf.place_creature(hero.id, Square(0, 0))
    bf.place_creature(g1.id, Square(5, 5))
    bf.place_creature(g2.id, Square(6, 5))
    # Rolls: init [20,1,2] (hero первый), heal 2d4=[4,4]=10,
    # fireball per-target: g1 8d6=[3]*8 + d20=5 (fail), g2 8d6=[3]*8 + d20=20 (save).
    deps, bus, _ = build_scripted_dependencies(
        battlefield=bf,
        rolls=[20, 1, 2, 4, 4] + [3] * 8 + [5] + [3] * 8 + [20] + [3] * 30,
    )
    enc = Encounter(
        participants={hero.id: hero, g1.id: g1, g2.id: g2},
        factions={hero.id: Faction.PARTY, g1.id: Faction.MONSTERS, g2.id: Faction.MONSTERS},
        deps=deps,
    )
    used: list[ItemUsed] = []
    healed: list[HealingApplied] = []
    dmg: list[DamageDealt] = []
    bus.subscribe(ItemUsed, used.append)
    bus.subscribe(HealingApplied, healed.append)
    bus.subscribe(DamageDealt, dmg.append)
    enc.start()
    ctx = enc.start_turn()
    assert enc.factions[enc.current_actor_id] is Faction.PARTY  # ход PC

    # 1) Зелье — bonus_action.
    UseItemAction(spells).execute(
        hero,
        UseItemParams(item_id=ItemId("healing_potion"), target_id=hero.id),
        ctx,
    )
    # 2) Свиток — action (отдельная экономика).
    UseItemAction(spells).execute(
        hero,
        UseItemParams(item_id=ItemId("scroll_of_fireball"), target_point=Square(5, 5)),
        ctx,
    )

    # Зелье: HP вырос, событие зафиксировано.
    assert healed and healed[0].target_id == hero.id
    assert hero.hit_points.current == 15  # 5 + 10
    # Свиток: оба гоблина задеты, расходник списан.
    targets_hit = {d.target_id for d in dmg}
    assert g1.id in targets_hit and g2.id in targets_hit
    # Оба расходника списаны.
    assert not hero.inventory.contains(ItemId("healing_potion"))
    assert not hero.inventory.contains(ItemId("scroll_of_fireball"))
    # ItemUsed опубликовано дважды (зелье + свиток).
    assert [u.item_id for u in used] == [
        ItemId("healing_potion"),
        ItemId("scroll_of_fireball"),
    ]
