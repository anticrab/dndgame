"""R1-2: ClassProgression / ClassLevel."""

from __future__ import annotations

import pytest

from dnd.domain.values.class_progression import ClassLevel, ClassProgression
from dnd.domain.values.ids import FeatureId


def _fighter() -> ClassProgression:
    return ClassProgression(
        id="fighter",
        name="Воин",
        hit_die="1d10",
        levels={
            1: ClassLevel(proficiency_bonus=2, features=(FeatureId("second_wind"),)),
            2: ClassLevel(proficiency_bonus=2, features=(FeatureId("action_surge"),)),
            3: ClassLevel(proficiency_bonus=2, features=(FeatureId("improved_critical"),)),
        },
    )


def test_level_lookup() -> None:
    f = _fighter()
    assert f.levels[1].proficiency_bonus == 2
    assert f.levels[2].features == (FeatureId("action_surge"),)


def test_requires_level_1() -> None:
    with pytest.raises(ValueError):
        ClassProgression(id="x", name="X", hit_die="1d8", levels={})


def test_hit_die_average() -> None:
    # ⌈(sides+1)/2⌉: d10 → 6.
    assert _fighter().hit_die_average() == 6


def test_class_progression_has_saving_throw_proficiencies() -> None:
    from dnd.domain.values.ability import Ability

    prog = ClassProgression(
        id="x",
        name="X",
        hit_die="1d6",
        levels={1: ClassLevel(proficiency_bonus=2)},
        saving_throw_proficiencies=frozenset({Ability.INT, Ability.WIS}),
    )
    assert Ability.INT in prog.saving_throw_proficiencies
    assert Ability.STR not in prog.saving_throw_proficiencies


def test_class_progression_save_profs_default_empty() -> None:
    prog = ClassProgression(
        id="y",
        name="Y",
        hit_die="1d6",
        levels={1: ClassLevel(proficiency_bonus=2)},
    )
    assert prog.saving_throw_proficiencies == frozenset()
