"""P1-4: CastSpellAction ATTACK (Fire Bolt) через реестр эффект-хендлеров."""
from __future__ import annotations

from pathlib import Path

from dnd.application.dto.action import Allowed, Forbidden
from dnd.application.dto.engine_event import DamageDealt, SpellCast
from dnd.application.engine.actions.cast_spell import CastSpellAction, CastSpellParams
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import SpellId
from dnd.domain.values.modifiers import ModifierTargetKind
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_SPELLS = Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"


def _repo() -> YamlSpellRepository:
    return YamlSpellRepository(_SPELLS)


def _mage() -> Creature:
    c = Creature.create(
        id_="mage", name="Mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30,
    )
    c.spellcasting_ability = Ability.INT       # +3, prof +2 → attack +5, DC 13
    c.known_spells = (
        SpellId("fire_bolt"), SpellId("magic_missile"), SpellId("sacred_flame"),
        SpellId("cure_wounds"), SpellId("shield_of_faith"),
    )
    return c


def _goblin(ac: int = 13) -> Creature:
    return Creature.create(
        id_="gob", name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=12, armor_class=ac, speed_ft=30, equipped_weapon=LONGSWORD,
    )


def _setup(rolls: list[int]) -> tuple[Encounter, Creature, Creature, object]:
    mage, gob = _mage(), _goblin()
    bf = Battlefield(8, 8)
    bf.place_creature(mage.id, Square(2, 2))
    bf.place_creature(gob.id, Square(4, 4))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={mage.id: mage, gob.id: gob},
        factions={mage.id: Faction.PARTY, gob.id: Faction.MONSTERS},
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
    return enc, mage, gob, ctx


def test_fire_bolt_hit_deals_damage() -> None:
    # init x2, затем attack d20=10 (+5=15 vs AC13 → hit), урон d10=7.
    enc, mage, gob, ctx = _setup([20, 19, 10, 7])
    casts: list[SpellCast] = []
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(SpellCast, casts.append)
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    action = CastSpellAction(_repo())
    params = CastSpellParams(spell_id=SpellId("fire_bolt"), target_id=gob.id)
    assert isinstance(action.can_perform_against(mage, params, ctx), Allowed)
    out = action.execute(mage, params, ctx)
    assert out.success
    assert casts and casts[0].spell_name == "Fire Bolt"
    assert dmg and dmg[0].final_amount == 7
    assert gob.hit_points.current == 5  # 12 - 7


def test_fire_bolt_miss_no_damage() -> None:
    # attack d20=3 (+5=8 vs AC13 → miss).
    enc, mage, gob, ctx = _setup([20, 19, 3])
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    action = CastSpellAction(_repo())
    out = action.execute(
        mage, CastSpellParams(spell_id=SpellId("fire_bolt"), target_id=gob.id), ctx
    )
    assert out.success           # каст состоялся (заговор брошен)
    assert not dmg               # но промах → урона нет
    assert gob.hit_points.current == 12


def test_cantrip_does_not_consume_slot() -> None:
    _enc, mage, gob, ctx = _setup([20, 19, 10, 7])
    mage.spell_slots = {1: 1}
    action = CastSpellAction(_repo())
    action.execute(
        mage, CastSpellParams(spell_id=SpellId("fire_bolt"), target_id=gob.id), ctx
    )
    assert mage.spell_slots == {1: 1}  # заговор слот не тратит


def test_non_caster_forbidden() -> None:
    _enc, mage, gob, ctx = _setup([20, 19, 10, 7])
    mage.spellcasting_ability = None
    action = CastSpellAction(_repo())
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=SpellId("fire_bolt"), target_id=gob.id), ctx
    )
    assert isinstance(avail, Forbidden)


def test_unknown_spell_forbidden() -> None:
    _enc, mage, gob, ctx = _setup([20, 19, 10, 7])
    action = CastSpellAction(_repo())
    avail = action.can_perform_against(
        mage, CastSpellParams(spell_id=SpellId("cure_wounds"), target_id=gob.id), ctx
    )
    assert isinstance(avail, Forbidden)  # не в known_spells мага


# --- P1-5: SAVE (Sacred Flame) -------------------------------------------

def test_sacred_flame_save_fail_full_damage() -> None:
    # init x2, урон d8=5, спасбросок d20=5 (+2 DEX=7 < DC13 → провал) → 5.
    enc, mage, gob, ctx = _setup([20, 19, 5, 5])
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    CastSpellAction(_repo()).execute(
        mage, CastSpellParams(spell_id=SpellId("sacred_flame"), target_id=gob.id), ctx
    )
    assert dmg and dmg[0].final_amount == 5
    assert gob.hit_points.current == 7  # 12 - 5


def test_sacred_flame_save_success_no_damage() -> None:
    # урон d8=5, спасбросок d20=15 (+2=17 ≥ DC13 → успех); save_for_half=False → 0.
    enc, mage, gob, ctx = _setup([20, 19, 5, 15])
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    CastSpellAction(_repo()).execute(
        mage, CastSpellParams(spell_id=SpellId("sacred_flame"), target_id=gob.id), ctx
    )
    assert dmg and dmg[0].final_amount == 0
    assert gob.hit_points.current == 12


def test_magic_missile_auto_damage_consumes_slot() -> None:
    # init x2, урон 3d4+3 = [4,4,4]+3 = 15 (auto, без броска атаки).
    enc, mage, gob, ctx = _setup([20, 19, 4, 4, 4])
    mage.spell_slots = {1: 1}
    dmg: list[DamageDealt] = []
    enc.event_bus.subscribe(DamageDealt, dmg.append)
    out = CastSpellAction(_repo()).execute(
        mage, CastSpellParams(spell_id=SpellId("magic_missile"), target_id=gob.id), ctx
    )
    assert out.success
    assert dmg and dmg[0].final_amount == 15
    assert mage.spell_slots == {1: 0}      # слот потрачен


def test_magic_missile_no_slot_forbidden() -> None:
    _enc, mage, gob, ctx = _setup([20, 19, 4, 4, 4])
    mage.spell_slots = {1: 0}
    avail = CastSpellAction(_repo()).can_perform_against(
        mage, CastSpellParams(spell_id=SpellId("magic_missile"), target_id=gob.id), ctx
    )
    assert isinstance(avail, Forbidden)


# --- P1-7: HEAL (Cure Wounds) --------------------------------------------

def test_cure_wounds_heals_self() -> None:
    # init x2, лечение d8=4 (+3 INT) = 7. Маг ранен до 2 → 9.
    enc, mage, _gob, ctx = _setup([20, 19, 4])
    mage.spell_slots = {1: 1}
    mage.hit_points = mage.hit_points.take_damage(8)  # 10 → 2
    from dnd.application.dto.engine_event import HealingApplied
    heals: list[HealingApplied] = []
    enc.event_bus.subscribe(HealingApplied, heals.append)
    out = CastSpellAction(_repo()).execute(
        mage, CastSpellParams(spell_id=SpellId("cure_wounds"), target_id=mage.id), ctx
    )
    assert out.success
    assert heals and heals[0].amount == 7
    assert mage.hit_points.current == 9


def test_cure_wounds_not_above_max() -> None:
    _enc, mage, _gob, ctx = _setup([20, 19, 8])
    mage.spell_slots = {1: 1}
    mage.hit_points = mage.hit_points.take_damage(2)  # 10 → 8
    CastSpellAction(_repo()).execute(
        mage, CastSpellParams(spell_id=SpellId("cure_wounds"), target_id=mage.id), ctx
    )
    assert mage.hit_points.current == 10  # не выше max


def test_heal_raises_ally_from_dying() -> None:
    """Прямой юнит HealSpellHandler: лечение поднимает PC из dying (Q-логика)."""
    from dnd.application.engine.spells.handlers import HealSpellHandler
    from dnd.domain.conditions.builtin import UNCONSCIOUS
    _enc, mage, _gob, ctx = _setup([20, 19, 4])
    ally = _mage()
    ally.id = type(ally.id)("ally")  # отдельный id
    ally.uses_death_saves = True
    ally.hit_points = ally.hit_points.take_damage(10)  # 0 HP
    ally.begin_dying()
    assert ally.death_saves is not None
    spell = _repo().load(SpellId("cure_wounds"))
    HealSpellHandler().apply(mage, (ally,), spell, ctx)
    assert ally.death_saves is None
    assert not ally.has_condition(UNCONSCIOUS)
    assert ally.hit_points.current > 0


# --- P1-8: BUFF + concentration (Shield of Faith) ------------------------

def _ac_bonus(ctx: object, target: Creature) -> int:
    mods = ctx.modifier_applier.collect(  # type: ignore[attr-defined]
        owner_id=target.id, target_kind=ModifierTargetKind.ARMOR_CLASS
    )
    return ctx.modifier_applier.to_roll_adjustments(mods).numeric_bonus  # type: ignore[attr-defined]


def test_shield_of_faith_grants_ac_and_concentration() -> None:
    _enc, mage, _gob, ctx = _setup([20, 19])
    mage.spell_slots = {1: 1}
    out = CastSpellAction(_repo()).execute(
        mage, CastSpellParams(spell_id=SpellId("shield_of_faith"), target_id=mage.id), ctx
    )
    assert out.success
    assert _ac_bonus(ctx, mage) == 2
    assert str(mage.concentration) == "shield_of_faith"


def test_recasting_concentration_does_not_stack() -> None:
    # Два каста в один ход невозможны (action economy) → проверяем хендлер
    # напрямую: повторное наложение снимает прежний бафф, не стэкается.
    from dnd.application.engine.spells.handlers import BuffSpellHandler
    _enc, mage, _gob, ctx = _setup([20, 19])
    spell = _repo().load(SpellId("shield_of_faith"))
    handler = BuffSpellHandler()
    handler.apply(mage, (mage,), spell, ctx)
    handler.apply(mage, (mage,), spell, ctx)
    assert _ac_bonus(ctx, mage) == 2  # не +4 — прежний бафф снят


def test_concentration_moves_buff_to_new_target() -> None:
    from dnd.application.engine.spells.handlers import BuffSpellHandler
    _enc, mage, gob, ctx = _setup([20, 19])
    spell = _repo().load(SpellId("shield_of_faith"))
    handler = BuffSpellHandler()
    handler.apply(mage, (mage,), spell, ctx)
    assert _ac_bonus(ctx, mage) == 2
    handler.apply(mage, (gob,), spell, ctx)  # новая концентрация на другой цели
    assert _ac_bonus(ctx, mage) == 0  # прежний бафф снят
    assert _ac_bonus(ctx, gob) == 2


# --- P1-audit регрессии -------------------------------------------------

def test_offensive_spell_on_dead_target_forbidden() -> None:
    """MAJOR-2: Fire Bolt по мёртвой цели → Forbidden (не только UI-фильтр)."""
    from dnd.domain.values.damage import DamageInstance, DamageType
    _enc, mage, gob, ctx = _setup([20, 19, 10, 7])
    gob.take_damage(DamageInstance(amount=99, type_=DamageType.SLASHING))  # труп
    avail = CastSpellAction(_repo()).can_perform_against(
        mage, CastSpellParams(spell_id=SpellId("fire_bolt"), target_id=gob.id), ctx
    )
    assert isinstance(avail, Forbidden)


def test_heal_on_dying_ally_allowed() -> None:
    """MAJOR-2: Cure Wounds по умирающему (0 HP, dying) союзнику — разрешено."""
    from dnd.domain.values.damage import DamageInstance, DamageType
    _enc, mage, _gob, ctx = _setup([20, 19, 4])
    mage.spell_slots = {1: 1}
    mage.uses_death_saves = True
    # ровно до 0 HP без massive damage (иначе мгновенная смерть, не dying)
    mage.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    mage.begin_dying()
    # маг таргетит сам себя (dying) — cure_wounds должно быть Allowed
    avail = CastSpellAction(_repo()).can_perform_against(
        mage, CastSpellParams(spell_id=SpellId("cure_wounds"), target_id=mage.id), ctx
    )
    assert isinstance(avail, Allowed)


def test_concentration_buff_removed_when_caster_downed() -> None:
    """MAJOR-1: при падении кастера в 0 HP его concentration-бафф (+AC) снимается."""
    from dnd.application.dto.engine_event import AttackResolved
    from dnd.domain.values.damage import DamageInstance, DamageType
    enc, mage, _gob, ctx = _setup([20, 19])
    mage.spell_slots = {1: 1}
    CastSpellAction(_repo()).execute(
        mage, CastSpellParams(spell_id=SpellId("shield_of_faith"), target_id=mage.id), ctx
    )
    assert _ac_bonus(ctx, mage) == 2
    # Маг получает летальный урон → концентрация рвётся, бафф снимается.
    mage.take_damage(DamageInstance(amount=99, type_=DamageType.SLASHING))
    enc.event_bus.publish(AttackResolved(
        attacker_id=_gob.id, target_id=mage.id,
        attack_roll_id="00000000-0000-0000-0000-000000000000",
        hit=True, is_critical=False, downed=True,
    ))
    assert _ac_bonus(ctx, mage) == 0
    assert mage.concentration is None


def test_save_for_half_yields_half_damage() -> None:
    """Прямой юнит SaveSpellHandler: save_for_half=True → половина урона."""
    from dnd.application.engine.spells.handlers import SaveSpellHandler
    from dnd.domain.values.damage import DamageType
    from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind
    _enc, mage, gob, ctx = _setup([20, 19, 6, 18])  # урон 6, save success
    spell = Spell(
        id=SpellId("fireball_like"), name="Half", level=1, school="evocation",
        effect=SpellEffect.SAVE, targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=60, description="", dice="1d8", damage_type=DamageType.FIRE,
        save_ability=Ability.DEX, save_for_half=True,
    )
    SaveSpellHandler().apply(mage, (gob,), spell, ctx)
    assert gob.hit_points.current == 9  # 12 - (6//2=3)
