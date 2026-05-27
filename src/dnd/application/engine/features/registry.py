"""FeatureRegistry — реестр классовых фич (этап R1, open/closed).

Каждая фича — feature_id + хендлер (``on_gain``). Регистрируется в
``default_feature_registry``. Новая фича = новый хендлер + регистрация + строка
в classes.yaml, без правки LevelUpService/движка (как SpellEffectRegistry).

``ResourceRegistry`` хранит спеки ограниченных ресурсов (max + recharge_on),
чтобы RestService знал, что и когда восстанавливать, не зная про конкретные фичи.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from dnd.domain.values.rest import RechargeOn

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ids import FeatureId


class FeatureHandler(Protocol):
    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        """Применить фичу при обретении: пассив (модификатор/деривация) или
        регистрация активной способности + инициализация ресурса. ``ctx`` —
        None при применении вне боя (создание PC), иначе текущий ход."""
        ...


class FeatureRegistry:
    def __init__(self) -> None:
        self._by_id: dict[FeatureId, FeatureHandler] = {}

    def register(self, feature_id: FeatureId, handler: FeatureHandler) -> None:
        self._by_id[feature_id] = handler

    def contains(self, feature_id: FeatureId) -> bool:
        return feature_id in self._by_id

    def get(self, feature_id: FeatureId) -> FeatureHandler:
        if feature_id not in self._by_id:
            raise KeyError(f"unknown feature: {feature_id!r}")
        return self._by_id[feature_id]


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    max_uses: int
    recharge_on: RechargeOn


class ResourceRegistry:
    def __init__(self) -> None:
        self._by_key: dict[str, ResourceSpec] = {}

    def register(self, key: str, spec: ResourceSpec) -> None:
        self._by_key[key] = spec

    def get(self, key: str) -> ResourceSpec:
        return self._by_key[key]

    def all_specs(self) -> dict[str, ResourceSpec]:
        return dict(self._by_key)


__all__ = ["FeatureHandler", "FeatureRegistry", "ResourceRegistry", "ResourceSpec"]
