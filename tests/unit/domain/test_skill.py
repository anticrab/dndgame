"""Skill — 18 навыков + маппинг на характеристику (V1)."""

from __future__ import annotations

from dnd.domain.values.ability import Ability
from dnd.domain.values.skill import SKILL_ABILITY, Skill


def test_all_skills_have_ability() -> None:
    assert set(SKILL_ABILITY) == set(Skill)
    assert all(v in Ability for v in SKILL_ABILITY.values())


def test_known_mappings() -> None:
    assert SKILL_ABILITY[Skill.ATHLETICS] is Ability.STR
    assert SKILL_ABILITY[Skill.STEALTH] is Ability.DEX
    assert SKILL_ABILITY[Skill.PERCEPTION] is Ability.WIS
    assert SKILL_ABILITY[Skill.PERSUASION] is Ability.CHA
    assert SKILL_ABILITY[Skill.ARCANA] is Ability.INT


def test_eighteen_skills() -> None:
    assert len(Skill) == 18
