"""Навыки приходят данными класса/шаблона (V1)."""

from __future__ import annotations

from pathlib import Path

from dnd.domain.values.skill import Skill
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository

_CLASSES = Path("data/content/classes.yaml")


def test_rogue_class_skill_proficiencies() -> None:
    rogue = YamlClassRepository(_CLASSES).load("rogue")
    assert Skill.STEALTH in rogue.skill_proficiencies
    assert Skill.SLEIGHT_OF_HAND in rogue.skill_proficiencies


def test_fighter_class_skill_proficiencies() -> None:
    fighter = YamlClassRepository(_CLASSES).load("fighter")
    assert Skill.ATHLETICS in fighter.skill_proficiencies
