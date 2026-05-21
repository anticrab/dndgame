"""Тесты Creature — правила урона/лечения/состояний/истощения по книге 2024.

Сценарии стр. 26-27 и отдельные сценарии «Сопротивление и Уязвимость»
(стр. 26), «Огромный урон» (стр. 27), «Истощение» (стр. 31).
"""

from __future__ import annotations

import pytest

from dnd.application.dto.ids import ConditionId, CreatureId
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.creature_size import CreatureSize
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.vision import NORMAL_VISION, Vision, VisionKind

# -- фабрика тест-существ -------------------------------------------------


def make_creature(
    *,
    max_hp: int = 20,
    ac: int = 15,
    speed: int = 30,
    size: CreatureSize = CreatureSize.MEDIUM,
    resistances: frozenset[str] = frozenset(),
    vulnerabilities: frozenset[str] = frozenset(),
    immunities: frozenset[str] = frozenset(),
    vision: tuple[Vision, ...] = (NORMAL_VISION,),
) -> Creature:
    return Creature.create(
        id_=CreatureId("test-1"),
        name="Test",
        abilities=AbilityScores.of(str_=14, dex=12, con=14, int_=10, wis=10, cha=8),
        max_hp=max_hp,
        armor_class=ac,
        speed_ft=speed,
        size=size,
        vision=vision,
        resistances=resistances,
        vulnerabilities=vulnerabilities,
        immunities=immunities,
    )


# -- создание -------------------------------------------------------------


def test_create_starts_with_full_hp() -> None:
    c = make_creature(max_hp=18)
    assert c.hit_points.current == 18
    assert c.hit_points.maximum == 18
    assert c.hit_points.temporary == 0


def test_create_rejects_zero_or_negative_hp() -> None:
    with pytest.raises(ValueError, match="max_hp must be >= 1"):
        Creature.create(
            id_=CreatureId("x"),
            name="x",
            abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
            max_hp=0,
            armor_class=10,
        )


def test_create_rejects_zero_ac() -> None:
    with pytest.raises(ValueError, match="armor_class must be >= 1"):
        Creature.create(
            id_=CreatureId("x"),
            name="x",
            abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
            max_hp=10,
            armor_class=0,
        )


def test_create_rejects_negative_speed() -> None:
    with pytest.raises(ValueError, match="speed_ft must be >= 0"):
        Creature.create(
            id_=CreatureId("x"),
            name="x",
            abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
            max_hp=10,
            armor_class=10,
            speed_ft=-1,
        )


def test_create_speed_zero_is_valid() -> None:
    """Скорость 0 валидна — это, например, статуя или парализованный."""
    c = Creature.create(
        id_=CreatureId("x"),
        name="x",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=0,
    )
    assert c.speed_ft == 0


# -- take_damage базово ---------------------------------------------------


@pytest.mark.rules
def test_take_damage_basic() -> None:
    c = make_creature(max_hp=20)
    res = c.take_damage(DamageInstance(8, DamageType.SLASHING))
    assert c.hit_points.current == 12
    assert res.final_amount == 8
    assert res.was_lethal is False


@pytest.mark.rules
def test_take_damage_zero_changes_nothing() -> None:
    c = make_creature(max_hp=20)
    res = c.take_damage(DamageInstance(0, DamageType.FIRE))
    assert c.hit_points.current == 20
    assert res.final_amount == 0


def test_take_damage_rejects_negative() -> None:
    c = make_creature()
    with pytest.raises(ValueError, match="must be >= 0"):
        c.take_damage(
            DamageInstance(amount=0, type_=DamageType.FIRE).__class__(
                amount=-1, type_=DamageType.FIRE
            )
        )


# -- resistance / vulnerability / immunity --------------------------------


@pytest.mark.rules
def test_resistance_halves_damage_rounded_down() -> None:
    c = make_creature(max_hp=20, resistances=frozenset({DamageType.FIRE.value}))
    res = c.take_damage(DamageInstance(7, DamageType.FIRE))
    assert res.final_amount == 3  # 7 // 2
    assert c.hit_points.current == 17


@pytest.mark.rules
def test_vulnerability_doubles_damage() -> None:
    c = make_creature(max_hp=20, vulnerabilities=frozenset({DamageType.FIRE.value}))
    res = c.take_damage(DamageInstance(5, DamageType.FIRE))
    assert res.final_amount == 10
    assert c.hit_points.current == 10


@pytest.mark.rules
def test_immunity_zeroes_damage() -> None:
    c = make_creature(max_hp=20, immunities=frozenset({DamageType.POISON.value}))
    res = c.take_damage(DamageInstance(100, DamageType.POISON))
    assert res.final_amount == 0
    assert c.hit_points.current == 20


@pytest.mark.rules
def test_resistance_and_vulnerability_cancel() -> None:
    """Книга: «бонусы одного типа не складываются». Resist+vuln = normal."""
    c = make_creature(
        max_hp=20,
        resistances=frozenset({DamageType.FIRE.value}),
        vulnerabilities=frozenset({DamageType.FIRE.value}),
    )
    res = c.take_damage(DamageInstance(10, DamageType.FIRE))
    assert res.final_amount == 10


@pytest.mark.rules
def test_immunity_overrides_vulnerability() -> None:
    c = make_creature(
        max_hp=20,
        vulnerabilities=frozenset({DamageType.POISON.value}),
        immunities=frozenset({DamageType.POISON.value}),
    )
    res = c.take_damage(DamageInstance(20, DamageType.POISON))
    assert res.final_amount == 0


@pytest.mark.rules
def test_only_specified_damage_type_affected() -> None:
    """Сопротивление огню не влияет на холод."""
    c = make_creature(max_hp=20, resistances=frozenset({DamageType.FIRE.value}))
    res = c.take_damage(DamageInstance(8, DamageType.COLD))
    assert res.final_amount == 8


# -- temp HP буфер -------------------------------------------------------


@pytest.mark.rules
def test_temp_hp_absorbs_damage_first() -> None:
    """Книга стр. 27: «временные хиты теряются первыми»."""
    c = make_creature(max_hp=20)
    c.gain_temporary_hp(5)
    res = c.take_damage(DamageInstance(3, DamageType.SLASHING))
    assert c.hit_points.current == 20
    assert c.hit_points.temporary == 2
    assert res.final_amount == 3


@pytest.mark.rules
def test_temp_hp_overflow_goes_to_current() -> None:
    c = make_creature(max_hp=20)
    c.gain_temporary_hp(5)
    res = c.take_damage(DamageInstance(8, DamageType.SLASHING))
    # temp 5 поглотили 5, остаток 3 ушёл в current
    assert c.hit_points.current == 17
    assert c.hit_points.temporary == 0
    assert res.final_amount == 8


# -- lethal damage & death (NPC vs PC семантика на уровне Character) -----


@pytest.mark.rules
def test_damage_to_zero_marks_was_lethal() -> None:
    c = make_creature(max_hp=10)
    res = c.take_damage(DamageInstance(10, DamageType.SLASHING))
    assert c.hit_points.current == 0
    assert c.is_unconscious is True
    assert res.was_lethal is True
    assert res.killed_outright is False  # overflow ровно равен max → не больше


@pytest.mark.rules
def test_massive_damage_kills_outright() -> None:
    """Книга стр. 27: «урон, превышающий максимум HP, убивает мгновенно».

    Существо с 14 HP (max 14), получает 30 урона: overflow = 30-14 = 16,
    16 >= 14 → killed_outright = True.
    """
    c = make_creature(max_hp=14)
    res = c.take_damage(DamageInstance(30, DamageType.SLASHING))
    assert res.was_lethal is True
    assert res.killed_outright is True
    assert res.overflow == 16


@pytest.mark.rules
def test_exact_max_damage_does_not_trigger_outright() -> None:
    """Грань: если урон ровно сводит в 0 без overflow — не massive death."""
    c = make_creature(max_hp=14)
    res = c.take_damage(DamageInstance(14, DamageType.SLASHING))
    assert res.was_lethal is True
    assert res.killed_outright is False
    assert res.overflow == 0


def test_overflow_zero_when_not_dropped_to_zero() -> None:
    c = make_creature(max_hp=20)
    res = c.take_damage(DamageInstance(5, DamageType.FIRE))
    assert res.overflow == 0
    assert res.killed_outright is False


def test_damage_at_zero_does_not_drop_below_zero() -> None:
    """Существо уже на 0 HP. Дополнительный удар не уводит current ниже 0."""
    c = make_creature(max_hp=10)
    c.take_damage(DamageInstance(15, DamageType.SLASHING))  # уже мертво
    assert c.hit_points.current == 0
    res = c.take_damage(DamageInstance(5, DamageType.SLASHING))
    assert c.hit_points.current == 0
    # was_alive=False (current уже 0), значит was_lethal должно быть False
    assert res.was_lethal is False


# -- heal ----------------------------------------------------------------


@pytest.mark.rules
def test_heal_basic() -> None:
    c = make_creature(max_hp=20)
    c.take_damage(DamageInstance(8, DamageType.SLASHING))
    res = c.heal(5)
    assert c.hit_points.current == 17
    assert res.final_amount == 5
    assert res.revived is False


@pytest.mark.rules
def test_heal_caps_at_max() -> None:
    c = make_creature(max_hp=10)
    c.take_damage(DamageInstance(5, DamageType.SLASHING))
    res = c.heal(100)
    assert c.hit_points.current == 10
    assert res.final_amount == 5  # реально применили только 5


@pytest.mark.rules
def test_heal_from_zero_marks_revived() -> None:
    """Лечение существа на 0 HP к >0 — `revived`. У PC это сбрасывает
    DeathSaveState; этот флаг — сигнал вызывающему слою."""
    c = make_creature(max_hp=10)
    c.take_damage(DamageInstance(15, DamageType.SLASHING))
    assert c.is_unconscious is True
    res = c.heal(3)
    assert c.hit_points.current == 3
    assert res.revived is True


def test_heal_zero_at_zero_does_not_revive() -> None:
    c = make_creature(max_hp=10)
    c.take_damage(DamageInstance(15, DamageType.SLASHING))
    res = c.heal(0)
    assert res.revived is False
    assert c.is_unconscious is True


def test_heal_rejects_negative() -> None:
    c = make_creature()
    with pytest.raises(ValueError, match=">= 0"):
        c.heal(-1)


# -- temp HP -------------------------------------------------------------


@pytest.mark.rules
def test_gain_temp_hp_replaces_smaller() -> None:
    """Книга стр. 27: «временные хиты не складываются, берёте лучший»."""
    c = make_creature()
    c.gain_temporary_hp(3)
    applied = c.gain_temporary_hp(8)
    assert c.hit_points.temporary == 8
    assert applied == 5  # 8 - 3 = +5 к существующим


def test_gain_temp_hp_keeps_larger() -> None:
    c = make_creature()
    c.gain_temporary_hp(8)
    applied = c.gain_temporary_hp(3)
    assert c.hit_points.temporary == 8
    assert applied == 0


def test_gain_temp_hp_rejects_negative() -> None:
    c = make_creature()
    with pytest.raises(ValueError, match=">= 0"):
        c.gain_temporary_hp(-1)


# -- conditions ----------------------------------------------------------


def test_apply_condition_adds() -> None:
    c = make_creature()
    poisoned = ConditionId("poisoned")
    assert c.apply_condition(poisoned) is True
    assert c.has_condition(poisoned) is True


def test_apply_condition_twice_is_idempotent() -> None:
    c = make_creature()
    poisoned = ConditionId("poisoned")
    c.apply_condition(poisoned)
    assert c.apply_condition(poisoned) is False  # уже есть


def test_immune_condition_not_applied() -> None:
    poisoned = ConditionId("poisoned")
    c = make_creature()
    c.condition_immunities = frozenset({poisoned})
    assert c.apply_condition(poisoned) is False
    assert c.has_condition(poisoned) is False


def test_remove_condition() -> None:
    c = make_creature()
    poisoned = ConditionId("poisoned")
    c.apply_condition(poisoned)
    assert c.remove_condition(poisoned) is True
    assert c.has_condition(poisoned) is False
    # Повторное удаление — False
    assert c.remove_condition(poisoned) is False


# -- exhaustion (Q34) ----------------------------------------------------


@pytest.mark.rules
def test_exhaustion_starts_at_zero() -> None:
    c = make_creature()
    assert c.exhaustion == 0
    assert c.is_exhaustion_lethal is False


@pytest.mark.rules
def test_add_exhaustion_caps_at_6() -> None:
    """Книга: 6 уровней. Дальше — смерть."""
    c = make_creature()
    c.add_exhaustion(10)  # просим больше, чем max
    assert c.exhaustion == 6
    assert c.is_exhaustion_lethal is True


@pytest.mark.rules
def test_remove_exhaustion_floors_at_zero() -> None:
    c = make_creature()
    c.add_exhaustion(2)
    c.remove_exhaustion(5)  # просим больше, чем есть
    assert c.exhaustion == 0


def test_add_exhaustion_rejects_negative() -> None:
    c = make_creature()
    with pytest.raises(ValueError, match=">= 0"):
        c.add_exhaustion(-1)


def test_remove_exhaustion_rejects_negative() -> None:
    c = make_creature()
    with pytest.raises(ValueError, match=">= 0"):
        c.remove_exhaustion(-1)


# -- concentration -------------------------------------------------------


def test_creature_starts_without_concentration() -> None:
    c = make_creature()
    assert c.concentration is None


@pytest.mark.rules
def test_concentration_broken_signal_when_damage_arrived() -> None:
    """При уроне на существо с концентрацией ставится сигнал
    `concentration_broken`. Реальный CON-save — на уровне выше.
    В MVP-классах concentration=None, поэтому сигнал не выставляется."""
    c = make_creature()
    c.concentration = ConditionId("bless")
    res = c.take_damage(DamageInstance(3, DamageType.SLASHING))
    assert res.concentration_broken is True


def test_concentration_not_broken_by_zero_damage() -> None:
    """Иммунитет: урон 0 → концентрация не срывается."""
    c = make_creature(immunities=frozenset({DamageType.POISON.value}))
    c.concentration = ConditionId("bless")
    res = c.take_damage(DamageInstance(10, DamageType.POISON))
    assert res.final_amount == 0
    assert res.concentration_broken is False


# -- vision / size (smoke) -----------------------------------------------


def test_creature_size_default_medium() -> None:
    c = make_creature()
    assert c.size is CreatureSize.MEDIUM


def test_creature_vision_default_normal() -> None:
    c = make_creature()
    assert c.vision == (NORMAL_VISION,)


def test_creature_can_have_darkvision() -> None:
    """Эльф/гоблин/большинство NPC."""
    c = make_creature(vision=(NORMAL_VISION, Vision(VisionKind.DARKVISION, 60)))
    assert len(c.vision) == 2
