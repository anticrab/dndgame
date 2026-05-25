"""P1-2: YamlSpellRepository — загрузка каталога заклинаний."""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.ids import SpellId
from dnd.application.ports.spell_repository import SpellRepository
from dnd.domain.values.ability import Ability
from dnd.domain.values.damage import DamageType
from dnd.domain.values.spell import SpellEffect, TargetKind
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPELLS = _REPO_ROOT / "data" / "content" / "spells.yaml"


def test_repo_implements_port() -> None:
    repo = YamlSpellRepository(_SPELLS)
    assert isinstance(repo, SpellRepository)


def test_loads_five_spells() -> None:
    repo = YamlSpellRepository(_SPELLS)
    ids = set(repo.list_ids())
    assert ids == {
        SpellId("fire_bolt"), SpellId("sacred_flame"), SpellId("magic_missile"),
        SpellId("cure_wounds"), SpellId("shield_of_faith"),
    }


def test_fire_bolt_fields() -> None:
    s = YamlSpellRepository(_SPELLS).load(SpellId("fire_bolt"))
    assert s.effect is SpellEffect.ATTACK
    assert s.level == 0
    assert s.dice == "1d10" and s.damage_type is DamageType.FIRE
    assert s.targeting.kind is TargetKind.SINGLE


def test_sacred_flame_save_fields() -> None:
    s = YamlSpellRepository(_SPELLS).load(SpellId("sacred_flame"))
    assert s.effect is SpellEffect.SAVE
    assert s.save_ability is Ability.DEX
    assert s.save_for_half is False


def test_shield_of_faith_buff() -> None:
    s = YamlSpellRepository(_SPELLS).load(SpellId("shield_of_faith"))
    assert s.effect is SpellEffect.BUFF
    assert s.ac_bonus == 2 and s.concentration is True


def test_contains_and_unknown() -> None:
    repo = YamlSpellRepository(_SPELLS)
    assert repo.contains(SpellId("fire_bolt"))
    assert not repo.contains(SpellId("nope"))
    with pytest.raises(KeyError):
        repo.load(SpellId("nope"))


def test_missing_file_is_empty(tmp_path: Path) -> None:
    repo = YamlSpellRepository(tmp_path / "absent.yaml")
    assert repo.list_ids() == ()


def test_duplicate_id_rejected(tmp_path: Path) -> None:
    f = tmp_path / "dup.yaml"
    f.write_text(
        "- {id: x, name: X, level: 0, school: e, effect: auto,\n"
        "   targeting: {kind: single}, range_ft: 10, dice: '1d4', damage_type: force}\n"
        "- {id: x, name: X2, level: 0, school: e, effect: auto,\n"
        "   targeting: {kind: single}, range_ft: 10, dice: '1d4', damage_type: force}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate spell id"):
        YamlSpellRepository(f)
