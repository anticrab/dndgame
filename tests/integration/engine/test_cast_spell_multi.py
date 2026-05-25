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
from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind
from dnd.domain.values.square import Square

_SPELLS = Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"


def _mage() -> Creature:
    c = Creature.create(
        id_="mage", name="Mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30,
    )
    c.spellcasting_ability = Ability.INT
    c.spell_slots = {1: 4}
    return c


def _gob(id_: str) -> Creature:
    return Creature.create(
        id_=id_, name=id_,
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12, armor_class=13, speed_ft=30,
    )


def _setup(rolls: list[int]) -> tuple[Encounter, Creature, Creature, Creature, object]:
    mage = _mage()
    a, b = _gob("gobA"), _gob("gobB")
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


def _mm() -> Spell:
    return Spell(
        id=SpellId("mm"), name="MM", level=1, school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(
            kind=TargetKind.MULTI, max_targets=3, allow_repeat_target=True
        ),
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
    params = CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id, b.id))
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
        mage,
        CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id, b.id, b.id)),
        ctx,
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
    _enc, mage, a, _b, ctx = _setup([20, 19, 19])
    spell = Spell(
        id=SpellId("mm2"), name="MM2", level=1, school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(
            kind=TargetKind.MULTI, max_targets=3, allow_repeat_target=False
        ),
        range_ft=120, description="", dice="1d4+1", damage_type=DamageType.FORCE,
    )
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id)), ctx
    )
    assert isinstance(avail, Forbidden)  # дубль при allow_repeat=False


def test_multi_out_of_range_forbidden() -> None:
    _enc, mage, _a, b, ctx = _setup([20, 19, 19])
    spell = Spell(
        id=SpellId("mm3"), name="MM3", level=1, school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3),
        range_ft=5, description="", dice="1d4+1", damage_type=DamageType.FORCE,
    )
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    # gobB на (4,2) — chebyshev 2 от мага (2,2) = 10 фт > range 5.
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=spell.id, target_ids=(b.id,)), ctx
    )
    assert isinstance(avail, Forbidden)
