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
from dnd.domain.values.spell_power import SpellPower
from dnd.domain.values.square import Square

_SPELLS = Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"


def _mage() -> Creature:
    c = Creature.create(
        id_="mage",
        name="Mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=10,
        armor_class=12,
        speed_ft=30,
    )
    c.spellcasting_ability = Ability.INT
    c.spell_slots = {1: 4}
    return c


def _gob(id_: str) -> Creature:
    return Creature.create(
        id_=id_,
        name=id_,
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12,
        armor_class=13,
        speed_ft=30,
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
            mage.id: Faction.PARTY,
            a.id: Faction.MONSTERS,
            b.id: Faction.MONSTERS,
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
        id=SpellId("mm"),
        name="MM",
        level=1,
        school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3, allow_repeat_target=True),
        range_ft=120,
        description="",
        dice="1d4+1",
        damage_type=DamageType.FORCE,
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
    from dnd.application.engine.spells.area import default_area_shape_registry
    from dnd.application.engine.spells.resolve import _resolve_targets

    _enc, mage, a, b, ctx = _setup([20, 19, 19])
    spell = _mm()
    mage.known_spells = (spell.id,)
    resolved = _resolve_targets(
        spell,
        mage,
        ctx=ctx,
        area_registry=default_area_shape_registry(),
        target_id=None,
        target_ids=(a.id, a.id, b.id),
        target_point=None,
        direction=None,
    )
    assert [c.id for c in resolved] == [a.id, a.id, b.id]


def test_multi_empty_targets_forbidden() -> None:
    _enc, mage, _a, _b, ctx = _setup([20, 19, 19])
    spell = _mm()
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    avail = action.can_perform_against(mage, CastSpellParams(spell_id=spell.id, target_ids=()), ctx)
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
        id=SpellId("mm2"),
        name="MM2",
        level=1,
        school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3, allow_repeat_target=False),
        range_ft=120,
        description="",
        dice="1d4+1",
        damage_type=DamageType.FORCE,
    )
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id)), ctx
    )
    assert isinstance(avail, Forbidden)  # дубль при allow_repeat=False


def test_magic_missile_distributes_across_targets() -> None:
    # 3 дротика 1d4+1: 2 в gobA, 1 в gobB. d4-броски [3,3,2].
    enc, mage, a, b, ctx = _setup([20, 19, 19, 3, 3, 2])
    from dnd.application.dto.engine_event import DamageDealt

    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    spell = _mm()
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    out = action.execute(
        mage,
        CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id, b.id)),
        ctx,
    )
    assert out.success
    by_target: dict[object, int] = {}
    for d in dmg:
        by_target[d.target_id] = by_target.get(d.target_id, 0) + d.raw_amount
    assert by_target[a.id] == (3 + 1) + (3 + 1)  # 2 дротика
    assert by_target[b.id] == (2 + 1)  # 1 дротик


def test_bless_adds_d4_to_spell_save() -> None:
    """Bless на цели → её спасбросок от спелла включает +1d4 (extra_dice)."""
    from dnd.application.engine.spells.handlers import (
        BuffSpellHandler,
        SaveSpellHandler,
    )
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.roll_purpose import RollPurpose
    from dnd.domain.values.spell import BuffSpec

    # init x3; затем SaveSpellHandler: урон d8=5, спасбросок d20=10 + bless d4=4.
    _enc, mage, a, _b, ctx = _setup([20, 19, 19, 5, 10, 4])
    bless = Spell(
        id=SpellId("bless"),
        name="Bless",
        level=1,
        school="enchantment",
        effect=SpellEffect.BUFF,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3),
        range_ft=30,
        description="",
        concentration=True,
        buffs=(BuffSpec(target=ModifierTargetKind.SAVING_THROW, dice_bonus="1d4"),),
    )
    BuffSpellHandler().apply(mage, (a,), bless, ctx, SpellPower.from_caster(mage))
    mods = ctx.modifier_applier.collect(owner_id=a.id, target_kind=ModifierTargetKind.SAVING_THROW)
    assert ctx.modifier_applier.to_roll_adjustments(mods).extra_dice == ("1d4",)
    save_spell = Spell(
        id=SpellId("sf"),
        name="SF",
        level=0,
        school="evocation",
        effect=SpellEffect.SAVE,
        targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=60,
        description="",
        dice="1d8",
        damage_type=DamageType.RADIANT,
        save_ability=Ability.DEX,
        save_for_half=False,
    )
    captured: list[object] = []
    orig_roll = ctx.dice_roller.roll

    def _spy(expr: object, rc: object) -> object:
        captured.append(rc)
        return orig_roll(expr, rc)  # type: ignore[arg-type]

    ctx.dice_roller.roll = _spy  # type: ignore[method-assign]
    SaveSpellHandler().apply(mage, (a,), save_spell, ctx, SpellPower.from_caster(mage))
    save_ctxs = [rc for rc in captured if getattr(rc, "purpose", None) is RollPurpose.SAVE]
    assert save_ctxs and save_ctxs[0].extra_dice == ("1d4",)  # type: ignore[attr-defined]


def test_spell_kill_triggers_downing() -> None:
    """M1: смерть от урона заклинанием триггерит падение (CreatureDied),
    как и от оружия — обработчик висит на DamageDealt(was_lethal), не на
    AttackResolved."""
    from dnd.application.dto.engine_event import CreatureDied

    # init x3; 3 дротика d4=[4,4,4] → 15 урона по gobA (12 HP) → смерть.
    enc, mage, a, _b, ctx = _setup([20, 19, 19, 4, 4, 4])
    spell = _mm()
    mage.known_spells = (spell.id,)
    deaths: list[CreatureDied] = []
    enc.event_bus.subscribe(CreatureDied, deaths.append)
    action = CastSpellAction(_OneSpellRepo(spell))
    action.execute(mage, CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id, a.id)), ctx)
    assert not a.is_alive
    assert any(d.actor_id == a.id for d in deaths)  # падение отработало


def test_spell_kill_breaks_concentration() -> None:
    """M1: летальный урон заклинанием рвёт концентрацию жертвы — её
    concentration-бафф снимается из ModifierApplier."""
    from dnd.application.engine.spells.handlers import (
        BuffSpellHandler,
        concentration_source,
    )
    from dnd.domain.values.modifiers import ModifierTargetKind
    from dnd.domain.values.spell import BuffSpec

    # init×3; gobA 12 HP, дротики 1d4+1=5: дротик1 (12→7) + CON-save d20=10
    # (успех, REV-1), дротик2 (7→2) + CON-save d20=10 (успех), дротик3 (→0,
    # летальный — рвёт концентрацию убийством, как и проверяет тест).
    _enc, mage, a, _b, ctx = _setup([20, 19, 19, 4, 10, 4, 10, 4])
    spell = _mm()
    mage.known_spells = (spell.id,)
    # gobA «концентрируется»: вешаем concentration-бафф на него (source=gobA).
    conc_spell = Spell(
        id=SpellId("conc"),
        name="Conc",
        level=1,
        school="abjuration",
        effect=SpellEffect.BUFF,
        targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=5,
        description="",
        concentration=True,
        buffs=(BuffSpec(target=ModifierTargetKind.ARMOR_CLASS, numeric_bonus=2),),
    )
    BuffSpellHandler().apply(a, (a,), conc_spell, ctx, SpellPower.from_caster(a))
    ac_mods = ctx.modifier_applier.collect(
        owner_id=a.id, target_kind=ModifierTargetKind.ARMOR_CLASS
    )
    assert ctx.modifier_applier.to_roll_adjustments(ac_mods).numeric_bonus == 2
    # Маг убивает gobA Magic Missile'ом → концентрация должна сорваться.
    CastSpellAction(_OneSpellRepo(spell)).execute(
        mage, CastSpellParams(spell_id=spell.id, target_ids=(a.id, a.id, a.id)), ctx
    )
    assert not a.is_alive
    after = ctx.modifier_applier.collect(owner_id=a.id, target_kind=ModifierTargetKind.ARMOR_CLASS)
    assert ctx.modifier_applier.to_roll_adjustments(after).numeric_bonus == 0
    assert concentration_source(a.id)  # sanity: source-helper доступен


def test_multi_out_of_range_forbidden() -> None:
    _enc, mage, _a, b, ctx = _setup([20, 19, 19])
    spell = Spell(
        id=SpellId("mm3"),
        name="MM3",
        level=1,
        school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(kind=TargetKind.MULTI, max_targets=3),
        range_ft=5,
        description="",
        dice="1d4+1",
        damage_type=DamageType.FORCE,
    )
    mage.known_spells = (spell.id,)
    action = CastSpellAction(_OneSpellRepo(spell))
    # gobB на (4,2) — chebyshev 2 от мага (2,2) = 10 фт > range 5.
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=spell.id, target_ids=(b.id,)), ctx
    )
    assert isinstance(avail, Forbidden)
