"""R1-2: YamlClassRepository грузит классы из classes.yaml."""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.domain.values.ids import FeatureId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository

_CLASSES = Path(__file__).resolve().parents[3] / "data" / "content" / "classes.yaml"


def _repo() -> YamlClassRepository:
    return YamlClassRepository(_CLASSES)


def test_loads_all_classes() -> None:
    assert set(_repo().list_ids()) == {"fighter", "rogue", "wizard"}


def test_fighter_levels() -> None:
    f = _repo().load("fighter")
    assert f.hit_die == "1d10"
    # T4: L1 += fighting_style; L3 — подкласс (Чемпион даёт Improved Critical).
    assert f.levels[1].features == (
        FeatureId("second_wind"), FeatureId("fighting_style"),
    )
    assert f.levels[3].features == (FeatureId("subclass"),)


def test_contains_and_unknown() -> None:
    repo = _repo()
    assert repo.contains("rogue") and repo.contains("wizard")
    assert not repo.contains("bard")
    with pytest.raises(KeyError):
        repo.load("bard")
