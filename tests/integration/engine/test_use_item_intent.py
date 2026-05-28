"""U2-5: UseItemIntent через GameRunner.

Образец — :mod:`test_cast_spell_intent`. Проверяем, что GameRunner правильно
проводит интент → UseItemAction → ItemUsed/HealingApplied; без
``spell_repository`` — тихий реджект (как и для CastSpell)."""

from __future__ import annotations

from pathlib import Path

from dnd.application.dto.engine_event import HealingApplied, ItemUsed
from dnd.application.dto.player_intent import EndTurnIntent, UseItemIntent
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.game_runner import GameRunner
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import SpellId
from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.item_use import ItemUseSpec
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_SPELLS = Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"


class _ScriptedProvider:
    def __init__(self, intents: list[object]) -> None:
        self._q = list(intents)

    def next_intent(self, actor: Creature, ctx: object, encounter: Encounter) -> object:
        return self._q.pop(0) if self._q else EndTurnIntent()


def _healing_potion() -> Item:
    return Item(
        id=ItemId("healing_potion"),
        name="Healing Potion",
        kind=ItemKind.CONSUMABLE,
        weight_lb=0.5,
        description="2d4+2",
        stackable=True,
        use=ItemUseSpec(
            effect_id=SpellId("cure_wounds"),
            economy="bonus_action",
            consumed=True,
            is_scroll=False,
        ),
    )


def _hero() -> Creature:
    h = Creature.create(
        id_="hero",
        name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=8, wis=10, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    h.hit_points = h.hit_points.take_damage(15)  # 20 → 5
    h.inventory.add(_healing_potion())
    return h


def test_use_item_intent_heals_and_consumes() -> None:
    hero = _hero()
    gob = Creature.create(
        id_="gob",
        name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(hero.id, Square(2, 2))
    bf.place_creature(gob.id, Square(4, 4))
    # init: hero 20+1, gob 1+2 → hero первый; затем 1d8 для cure_wounds = 6.
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1, 6])
    enc = Encounter(
        participants={hero.id: hero, gob.id: gob},
        factions={hero.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    used: list[ItemUsed] = []
    healed: list[HealingApplied] = []
    enc.event_bus.subscribe(ItemUsed, used.append)
    enc.event_bus.subscribe(HealingApplied, healed.append)
    provider = _ScriptedProvider(
        [
            UseItemIntent(item_id=ItemId("healing_potion"), target_id=hero.id),
            EndTurnIntent(),
        ]
    )
    runner = GameRunner(
        intent_provider=provider,
        spell_repository=YamlSpellRepository(_SPELLS),
        monster_turn=lambda a, c, e: None,
    )
    runner.run(enc)
    assert used and used[0].item_id == ItemId("healing_potion")
    assert healed and healed[0].target_id == hero.id
    assert hero.hit_points.current > 5  # вылечили
    assert hero.inventory.contains(ItemId("healing_potion")) is False  # расходник списан


def test_use_item_without_spell_repository_rejected() -> None:
    """Без spell_repository UseItemIntent тихо реджектится (HP не растёт)."""
    hero = _hero()
    gob = Creature.create(
        id_="gob",
        name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(hero.id, Square(2, 2))
    bf.place_creature(gob.id, Square(4, 4))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1, 6])
    enc = Encounter(
        participants={hero.id: hero, gob.id: gob},
        factions={hero.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    provider = _ScriptedProvider(
        [
            UseItemIntent(item_id=ItemId("healing_potion"), target_id=hero.id),
            EndTurnIntent(),
        ]
    )
    runner = GameRunner(intent_provider=provider, monster_turn=lambda a, c, e: None)
    runner.run(enc)
    assert hero.hit_points.current == 5  # spell_repository нет → каста нет
    assert hero.inventory.contains(ItemId("healing_potion")) is True
