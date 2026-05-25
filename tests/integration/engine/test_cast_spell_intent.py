"""P1-9: CastSpellIntent через GameRunner."""
from __future__ import annotations

from pathlib import Path

from dnd.application.dto.player_intent import CastSpellIntent, EndTurnIntent
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.game_runner import GameRunner
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import SpellId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_SPELLS = Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"


class _ScriptedProvider:
    def __init__(self, intents: list[object]) -> None:
        self._q = list(intents)

    def next_intent(self, actor: Creature, ctx: object, encounter: Encounter) -> object:
        return self._q.pop(0) if self._q else EndTurnIntent()


def _mage() -> Creature:
    c = Creature.create(
        id_="mage", name="Mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30,
    )
    c.spellcasting_ability = Ability.INT
    c.known_spells = (SpellId("fire_bolt"),)
    return c


def test_cast_spell_intent_applies_damage() -> None:
    mage = _mage()
    gob = Creature.create(
        id_="gob", name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(mage.id, Square(2, 2))
    bf.place_creature(gob.id, Square(4, 4))
    # init: mage 20+1, gob 1+2 → mage первый; затем fire_bolt attack=10, dmg=6.
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1, 10, 6])
    enc = Encounter(
        participants={mage.id: mage, gob.id: gob},
        factions={mage.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    provider = _ScriptedProvider([
        CastSpellIntent(spell_id=SpellId("fire_bolt"), target_id=gob.id),
        EndTurnIntent(),
    ])
    runner = GameRunner(
        intent_provider=provider,
        spell_repository=YamlSpellRepository(_SPELLS),
        monster_turn=lambda a, c, e: None,  # монстр пасует
    )
    runner.run(enc)
    assert gob.hit_points.current == 6  # 12 - 6 (Fire Bolt попал)


def test_multi_cast_intent_propagates_target_ids() -> None:
    """P2b-аудит C1: GameRunner прокидывает target_ids в params — иначе
    MULTI-заклинания (Magic Missile) реджектятся в реальном игровом цикле."""
    mage = _mage()
    mage.known_spells = (SpellId("magic_missile"),)
    mage.spell_slots = {1: 1}
    gob = Creature.create(
        id_="gob", name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(mage.id, Square(2, 2))
    bf.place_creature(gob.id, Square(4, 4))
    # init: mage 20+1, gob 1+2 → mage первый; 3 дротика 1d4: [4,4,4] → raw 15.
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1, 4, 4, 4])
    enc = Encounter(
        participants={mage.id: mage, gob.id: gob},
        factions={mage.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    provider = _ScriptedProvider([
        CastSpellIntent(
            spell_id=SpellId("magic_missile"),
            target_ids=(gob.id, gob.id, gob.id),
        ),
        EndTurnIntent(),
    ])
    runner = GameRunner(
        intent_provider=provider,
        spell_repository=YamlSpellRepository(_SPELLS),
        monster_turn=lambda a, c, e: None,
    )
    runner.run(enc)
    assert gob.hit_points.current == 0   # 12 - 15 → 0 (3 дротика попали)
    assert mage.spell_slots == {1: 0}    # слот потрачен → каст реально прошёл


def test_cast_without_spell_repository_rejected() -> None:
    """Без spell_repository CastSpellIntent тихо реджектится (урона нет)."""
    mage = _mage()
    gob = Creature.create(
        id_="gob", name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(mage.id, Square(2, 2))
    bf.place_creature(gob.id, Square(4, 4))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1, 10, 6])
    enc = Encounter(
        participants={mage.id: mage, gob.id: gob},
        factions={mage.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    provider = _ScriptedProvider([
        CastSpellIntent(spell_id=SpellId("fire_bolt"), target_id=gob.id),
        EndTurnIntent(),
    ])
    runner = GameRunner(intent_provider=provider, monster_turn=lambda a, c, e: None)
    runner.run(enc)
    assert gob.hit_points.current == 12  # spell_repository нет → каста нет
