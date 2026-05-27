"""Тесты ``weapon_attack_params`` — сборка AttackParams из equipped_weapon.

PHB-2024 стр. 25 + стр. 32 + стр. 211–212.
"""

from __future__ import annotations

import pytest

from dnd.application.engine.actions.attack import AttackKind
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.weapon import LONGSWORD, SCIMITAR, SHORTBOW


def _make(creature_id: str, *, str_: int, dex: int, weapon=LONGSWORD, prof: int = 2) -> Creature:
    return Creature.create(
        id_=CreatureId(creature_id),
        name=creature_id,
        abilities=AbilityScores.of(str_=str_, dex=dex, con=12, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=30,
        proficiency_bonus=prof,
        equipped_weapon=weapon,
    )


@pytest.mark.rules
def test_longsword_attack_bonus_is_prof_plus_str() -> None:
    """PHB-2024 стр. 25, 32: atk = proficiency + STR_mod для melee."""
    fighter = _make("fighter", str_=16, dex=12)  # STR mod +3
    params = weapon_attack_params(fighter, CreatureId("goblin"))
    assert params.attack_bonus == 2 + 3  # prof +2 + STR +3
    assert params.kind is AttackKind.MELEE
    assert params.damage_type is DamageType.SLASHING


@pytest.mark.rules
def test_longsword_damage_includes_str_mod() -> None:
    """PHB-2024 стр. 25: к броску урона добавляется ability_mod."""
    fighter = _make("fighter", str_=16, dex=12)
    params = weapon_attack_params(fighter, CreatureId("goblin"))
    assert params.damage_expr == "1d8+3"


def test_zero_str_mod_damage_keeps_dice_only() -> None:
    """STR mod = 0 → damage_expr = чистые кубы без +0."""
    fighter = _make("fighter", str_=10, dex=10)
    params = weapon_attack_params(fighter, CreatureId("goblin"))
    assert params.damage_expr == "1d8"  # без +0


@pytest.mark.rules
def test_finesse_picks_higher_of_str_dex() -> None:
    """PHB-2024 стр. 212 (Finesse): атакующий выбирает STR или DEX.

    Scimitar — finesse. STR=10 (+0), DEX=16 (+3) → выбираем DEX.
    """
    rogue = _make("rogue", str_=10, dex=16, weapon=SCIMITAR)
    params = weapon_attack_params(rogue, CreatureId("orc"))
    assert params.attack_bonus == 2 + 3  # prof + DEX
    assert params.damage_expr == "1d6+3"


@pytest.mark.rules
def test_finesse_picks_str_when_higher() -> None:
    """Finesse сам выбирает: STR=18 (+4), DEX=14 (+2) → STR."""
    swashbuckler = _make("sw", str_=18, dex=14, weapon=SCIMITAR)
    params = weapon_attack_params(swashbuckler, CreatureId("orc"))
    assert params.attack_bonus == 2 + 4


@pytest.mark.rules
def test_ranged_uses_dex_by_default() -> None:
    """PHB-2024 стр. 25: ranged attacks use DEX modifier."""
    ranger = _make("ranger", str_=10, dex=16, weapon=SHORTBOW)
    params = weapon_attack_params(ranger, CreatureId("goblin"))
    assert params.attack_bonus == 2 + 3
    assert params.kind is AttackKind.RANGED
    assert params.range_ft == 80
    assert params.long_range_ft == 320


def test_no_equipped_weapon_raises() -> None:
    unarmed = Creature.create(
        id_=CreatureId("unarmed"),
        name="Unarmed",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
    )
    with pytest.raises(ValueError, match="no equipped_weapon"):
        weapon_attack_params(unarmed, CreatureId("goblin"))


@pytest.mark.rules
def test_higher_proficiency_bonus_applies() -> None:
    """Уровни 5+ — prof bonus +3 (PHB-2024 стр. 32)."""
    fighter = _make("vet", str_=16, dex=12, prof=3)
    params = weapon_attack_params(fighter, CreatureId("goblin"))
    assert params.attack_bonus == 3 + 3  # prof +3 + STR +3


# -- VS-AI001 (audit 14): is_hostile_from_factions ---------------------


def test_is_hostile_from_factions_skips_neutral_and_self() -> None:
    """Аудит 14 VS-AI001: NEUTRAL и same-faction — не враги."""
    from dnd.application.engine.ai.simple_monster import (
        is_hostile_from_factions,
    )
    from dnd.domain.values.faction import Faction

    a = CreatureId("a")
    b = CreatureId("b")
    n = CreatureId("n")
    pred = is_hostile_from_factions(
        a,
        {a: Faction.PARTY, b: Faction.MONSTERS, n: Faction.NEUTRAL},
    )
    assert pred(a) is False  # self
    assert pred(b) is True  # MONSTERS vs PARTY → враг
    assert pred(n) is False  # NEUTRAL — не враг


def test_is_hostile_from_factions_same_faction_friendly() -> None:
    from dnd.application.engine.ai.simple_monster import (
        is_hostile_from_factions,
    )
    from dnd.domain.values.faction import Faction

    a = CreatureId("a")
    b = CreatureId("b")
    pred = is_hostile_from_factions(a, {a: Faction.PARTY, b: Faction.PARTY})
    assert pred(b) is False  # союзник
