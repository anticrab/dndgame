"""Q-1: Creature — спасброски от смерти, dying state (PHB-2024 стр. 27)."""
from __future__ import annotations

from dnd.domain.conditions.builtin import UNCONSCIOUS
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType


def _pc(max_hp: int = 10, *, uses_death_saves: bool = True) -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=max_hp, armor_class=12, speed_ft=30,
    )
    c.uses_death_saves = uses_death_saves
    return c


def _hit(c: Creature, amount: int, *, crit: bool = False) -> None:
    c.take_damage(DamageInstance(amount=amount, type_=DamageType.SLASHING), is_critical=crit)


def test_pc_dropped_to_zero_begins_dying() -> None:
    c = _pc(10)
    _hit(c, 10)
    assert c.is_at_zero_hp
    # ещё не dying, пока Encounter не вызовет begin_dying()
    assert c.death_saves is None
    assert c.begin_dying() is True
    assert c.death_saves is not None
    assert c.has_condition(UNCONSCIOUS)
    assert not c.is_dead


def test_npc_does_not_begin_dying() -> None:
    c = _pc(10, uses_death_saves=False)
    _hit(c, 10)
    assert c.begin_dying() is False
    assert c.death_saves is None


def test_death_save_success_then_failure() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    out = c.roll_death_save(15)
    assert out.result == "success"
    assert out.successes == 1 and out.failures == 0
    out = c.roll_death_save(5)
    assert out.result == "failure"
    assert out.successes == 1 and out.failures == 1


def test_nat20_recovers_one_hp() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    out = c.roll_death_save(20)
    assert out.result == "recovered"
    assert c.hit_points.current == 1
    assert c.death_saves is None
    assert not c.has_condition(UNCONSCIOUS)


def test_nat1_two_failures() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    out = c.roll_death_save(1)
    assert out.failures == 2


def test_three_failures_is_dead() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    c.roll_death_save(5)
    c.roll_death_save(5)
    out = c.roll_death_save(5)
    assert out.failures == 3
    assert c.is_dead


def test_damage_at_zero_adds_failure_crit_two() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    _hit(c, 3)  # обычный удар по лежачему → 1 провал
    assert c.death_saves is not None and c.death_saves.failures == 1
    _hit(c, 3, crit=True)  # крит → ещё 2 → всего 3
    assert c.death_saves.failures == 3
    assert c.is_dead


def test_massive_damage_kills_outright() -> None:
    c = _pc(10)
    _hit(c, 25)  # overflow 15 >= max 10 → killed_outright
    assert c.death_saves is not None
    assert c.death_saves.is_dead


def test_heal_from_dying_restores_consciousness() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    c.heal(4)
    assert c.death_saves is None
    assert not c.has_condition(UNCONSCIOUS)
    assert c.hit_points.current == 4
