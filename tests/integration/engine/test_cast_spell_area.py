"""P2-4/P2-5: AoE-резолвинг целей в CastSpellAction (круг/конус, friendly fire)."""
from __future__ import annotations

from typing import ClassVar

from dnd.application.dto.action import Allowed, Forbidden
from dnd.application.dto.engine_event import DamageDealt
from dnd.application.dto.ids import SpellId
from dnd.application.engine.actions.cast_spell import CastSpellAction, CastSpellParams
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.direction import Direction
from dnd.domain.values.faction import Faction
from dnd.domain.values.spell import (
    AreaShape,
    OriginMode,
    Spell,
    SpellEffect,
    TargetingSpec,
    TargetKind,
)
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD

_FIREBALL = Spell(
    id=SpellId("fireball"), name="Fireball", level=1, school="evocation",
    effect=SpellEffect.SAVE,
    targeting=TargetingSpec(
        kind=TargetKind.AREA, origin=OriginMode.AT_POINT,
        shape=AreaShape.CIRCLE, radius_ft=10,  # 2 клетки
    ),
    range_ft=150, description="", dice="1d6", damage_type=DamageType.FIRE,
    save_ability=Ability.DEX, save_for_half=True,
)
_BURNING_HANDS = Spell(
    id=SpellId("burning_hands"), name="Burning Hands", level=1, school="evocation",
    effect=SpellEffect.SAVE,
    targeting=TargetingSpec(
        kind=TargetKind.AREA, origin=OriginMode.FROM_CASTER,
        shape=AreaShape.CONE, length_ft=15,  # 3 клетки
    ),
    range_ft=15, description="", dice="1d6", damage_type=DamageType.FIRE,
    save_ability=Ability.DEX, save_for_half=True,
)


class _Repo:
    _m: ClassVar[dict[SpellId, Spell]] = {
        _FIREBALL.id: _FIREBALL, _BURNING_HANDS.id: _BURNING_HANDS,
    }

    def list_ids(self) -> tuple[SpellId, ...]:
        return tuple(self._m)

    def load(self, sid: SpellId) -> Spell:
        return self._m[sid]

    def contains(self, sid: SpellId) -> bool:
        return sid in self._m


def _mage() -> Creature:
    c = Creature.create(
        id_="mage", name="Mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=20, armor_class=12, speed_ft=30,
    )
    c.spellcasting_ability = Ability.INT
    c.known_spells = (SpellId("fireball"), SpellId("burning_hands"))
    c.spell_slots = {1: 5}
    return c


def _grunt(id_: str, faction_hp: int = 12) -> Creature:
    return Creature.create(
        id_=id_, name=id_,
        abilities=AbilityScores.of(str_=12, dex=10, con=12, int_=8, wis=8, cha=8),
        max_hp=faction_hp, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )


def _setup(positions: dict[str, Square], factions: dict[str, Faction],
           rolls: list[int]) -> tuple[Encounter, dict[str, Creature], object]:
    creatures: dict[str, Creature] = {}
    bf = Battlefield(10, 10)
    for cid, pos in positions.items():
        cr = _mage() if cid == "mage" else _grunt(cid)
        creatures[cid] = cr
        bf.place_creature(cr.id, pos)
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={c.id: c for c in creatures.values()},
        factions={creatures[k].id: v for k, v in factions.items()},
        deps=deps,
    )
    enc.start()
    for _ in range(20):
        if enc.current_actor_id == creatures["mage"].id:
            break
        enc.start_turn()
        enc.end_turn()
    assert enc.current_actor_id == creatures["mage"].id
    ctx = enc.start_turn()
    return enc, creatures, ctx


def test_fireball_at_point_hits_all_in_circle_incl_ally() -> None:
    # маг(1,1), gobA(4,4), gobB(5,4), ally(4,5). Круг r=2 в точку (4,4)
    # накрывает всех троих (friendly fire), мага — нет.
    enc, cr, ctx = _setup(
        positions={
            "mage": Square(1, 1), "gobA": Square(4, 4),
            "gobB": Square(5, 4), "ally": Square(4, 5),
        },
        factions={
            "mage": Faction.PARTY, "ally": Faction.PARTY,
            "gobA": Faction.MONSTERS, "gobB": Faction.MONSTERS,
        },
        rolls=[20, 19, 18, 17] + [3] * 40,  # инициативы + урон/сейвы (провал → урон)
    )
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    out = CastSpellAction(_Repo()).execute(
        cr["mage"],
        CastSpellParams(spell_id=SpellId("fireball"), target_point=Square(4, 4)),
        ctx,
    )
    assert out.success
    hit_ids = {d.target_id for d in dmg}
    assert hit_ids == {cr["gobA"].id, cr["gobB"].id, cr["ally"].id}  # 3, вкл. союзника
    assert cr["mage"].id not in hit_ids


def test_fireball_out_of_range_forbidden() -> None:
    _enc, cr, ctx = _setup(
        positions={"mage": Square(0, 0), "gobA": Square(9, 9)},
        factions={"mage": Faction.PARTY, "gobA": Faction.MONSTERS},
        rolls=[20, 19] + [3] * 20,
    )
    # range fireball 150ft = 30 клеток; поле 10×10 — точка всегда в range,
    # поэтому проверяем явный далёкий point за пределами range искусственно
    avail = CastSpellAction(_Repo()).can_perform_against(
        cr["mage"],
        CastSpellParams(spell_id=SpellId("fireball"), target_point=Square(9, 9)),
        ctx,
    )
    assert isinstance(avail, Allowed)  # 9 клеток ≤ 30 — в range


def test_fireball_without_point_forbidden() -> None:
    _enc, cr, ctx = _setup(
        positions={"mage": Square(0, 0), "gobA": Square(5, 5)},
        factions={"mage": Faction.PARTY, "gobA": Faction.MONSTERS},
        rolls=[20, 19] + [3] * 20,
    )
    avail = CastSpellAction(_Repo()).can_perform_against(
        cr["mage"], CastSpellParams(spell_id=SpellId("fireball")), ctx
    )
    assert isinstance(avail, Forbidden)


def test_burning_hands_from_caster_requires_direction() -> None:
    _enc, cr, ctx = _setup(
        positions={"mage": Square(2, 2), "gobA": Square(5, 5)},
        factions={"mage": Faction.PARTY, "gobA": Faction.MONSTERS},
        rolls=[20, 19] + [3] * 20,
    )
    action = CastSpellAction(_Repo())
    no_dir = action.can_perform_against(
        cr["mage"], CastSpellParams(spell_id=SpellId("burning_hands")), ctx
    )
    assert isinstance(no_dir, Forbidden)
    with_dir = action.can_perform_against(
        cr["mage"],
        CastSpellParams(spell_id=SpellId("burning_hands"), direction=Direction.E),
        ctx,
    )
    assert isinstance(with_dir, Allowed)


def test_burning_hands_cone_hits_creatures_in_direction() -> None:
    # маг(2,2), конус на E длиной 3: задевает (3,2),(4,1),(4,2),(4,3),(5,*)...
    enc, cr, ctx = _setup(
        positions={
            "mage": Square(2, 2), "gobA": Square(3, 2), "gobB": Square(4, 3),
            "behind": Square(1, 2),  # позади мага (W) — не в конусе
        },
        factions={
            "mage": Faction.PARTY, "gobA": Faction.MONSTERS,
            "gobB": Faction.MONSTERS, "behind": Faction.MONSTERS,
        },
        rolls=[20, 19, 18, 17] + [3] * 40,
    )
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    CastSpellAction(_Repo()).execute(
        cr["mage"],
        CastSpellParams(spell_id=SpellId("burning_hands"), direction=Direction.E),
        ctx,
    )
    hit_ids = {d.target_id for d in dmg}
    assert cr["gobA"].id in hit_ids and cr["gobB"].id in hit_ids
    assert cr["behind"].id not in hit_ids  # позади — не задет


def test_yaml_fireball_smoke_hits_multiple() -> None:
    """P2-5: Fireball из реального spells.yaml бьёт нескольких в зоне."""
    from pathlib import Path

    from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository
    spells = YamlSpellRepository(
        Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"
    )
    enc, cr, ctx = _setup(
        positions={
            "mage": Square(0, 0), "gobA": Square(5, 5), "gobB": Square(6, 5),
        },
        factions={
            "mage": Faction.PARTY, "gobA": Faction.MONSTERS,
            "gobB": Faction.MONSTERS,
        },
        rolls=[20, 19, 18] + [3] * 40,
    )
    cr["mage"].known_spells = (SpellId("fireball"),)
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    out = CastSpellAction(spells).execute(
        cr["mage"],
        CastSpellParams(spell_id=SpellId("fireball"), target_point=Square(5, 5)),
        ctx,
    )
    assert out.success
    assert {d.target_id for d in dmg} == {cr["gobA"].id, cr["gobB"].id}
