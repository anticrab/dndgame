"""Контент T2: sleep/hold_person парсятся; уровни evocation исправлены."""
from __future__ import annotations

from pathlib import Path

from dnd.domain.conditions.builtin import PARALYZED, UNCONSCIOUS
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import SpellEffect
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_SPELLS = Path("data/content/spells.yaml")


def _repo() -> YamlSpellRepository:
    return YamlSpellRepository(_SPELLS)


def test_sleep_parsed() -> None:
    sp = _repo().load(SpellId("sleep"))
    assert sp.effect is SpellEffect.CONTROL
    assert sp.condition == UNCONSCIOUS
    assert sp.hp_pool_dice == "5d8"
    assert sp.condition_ends_on_damage is True
    assert sp.level == 1


def test_hold_person_parsed() -> None:
    sp = _repo().load(SpellId("hold_person"))
    assert sp.effect is SpellEffect.CONTROL
    assert sp.condition == PARALYZED
    assert sp.save_ability is Ability.WIS
    assert sp.concentration is True
    assert sp.condition_repeat_save is True
    assert sp.level == 2


def test_evocation_levels_fixed() -> None:
    repo = _repo()
    assert repo.load(SpellId("fireball")).level == 3
    assert repo.load(SpellId("lightning_bolt")).level == 3
    assert repo.load(SpellId("burning_hands")).level == 1
