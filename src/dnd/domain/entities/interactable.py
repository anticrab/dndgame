"""InteractableObject — двери, сундуки, бочки, окна.

Mutable entity (как Creature). Имеет ``state: dict`` со свободной
схемой — конкретные ключи зависят от ``kind``:

* DOOR: open (bool), locked (bool), hp (int), ac (int).
* CHEST: open (bool), locked (bool), contents (list[str]).
* BARREL: hp (int), broken (bool), contents (list[str]).
* WINDOW: hp (int), broken (bool).

Методы (``open()`` / ``take_damage()`` / ...) — конкретные операции,
которые валидируют state и меняют его на месте.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dnd.application.dto.ids import ObjectId
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square


@dataclass(slots=True)
class ObjectDamageResult:
    """Итог take_damage у InteractableObject."""

    raw: int
    final: int
    was_lethal: bool  # сломан / разрушен этой порцией


@dataclass(slots=True)
class InteractableObject:
    id: ObjectId
    kind: ObjectKind
    pos: Square
    state: dict[str, Any] = field(default_factory=dict)

    # --- door/chest --------------------------------------------------

    def open(self) -> list[str]:
        """Открыть. Возвращает loot (для CHEST) или [] для DOOR.

        DOOR: меняет ``open`` на True. RuntimeError если locked.
        CHEST: меняет ``open`` на True, возвращает contents и очищает.
        BARREL/WINDOW: RuntimeError (нельзя «открыть»).
        """
        if self.kind is ObjectKind.DOOR:
            if self.state.get("locked"):
                raise RuntimeError(f"door {self.id} is locked")
            self.state["open"] = True
            return []
        if self.kind is ObjectKind.CHEST:
            if self.state.get("locked"):
                raise RuntimeError(f"chest {self.id} is locked")
            if self.state.get("open"):
                return []
            self.state["open"] = True
            loot = list(self.state.get("contents", []))
            self.state["contents"] = []
            return loot
        if self.kind is ObjectKind.CORPSE:
            # Q-8: труп открывается, но contents НЕ очищаются — лут идёт
            # поштучно через PickupAction (инвентарь-экран), не моментально.
            self.state["open"] = True
            return []
        raise RuntimeError(f"{self.kind.value} cannot be opened")

    def close(self) -> None:
        """Закрыть DOOR. Прочие — RuntimeError."""
        if self.kind is ObjectKind.DOOR:
            self.state["open"] = False
            return
        raise RuntimeError(f"{self.kind.value} cannot be closed")

    # --- breakable ---------------------------------------------------

    def take_damage(self, damage: DamageInstance) -> ObjectDamageResult:
        """Принять урон. Может сломать BARREL/WINDOW/DOOR (если есть hp)."""
        if "hp" not in self.state:
            raise RuntimeError(f"{self.kind.value} has no hp; cannot take damage")
        hp_before = int(self.state["hp"])
        if hp_before <= 0:
            return ObjectDamageResult(raw=damage.amount, final=0, was_lethal=False)
        applied = min(damage.amount, hp_before)
        hp_after = hp_before - applied
        self.state["hp"] = hp_after
        was_lethal = hp_before > 0 and hp_after == 0
        if was_lethal:
            self.state["broken"] = True
            # сломанная дверь = открытая
            if self.kind is ObjectKind.DOOR:
                self.state["open"] = True
        return ObjectDamageResult(
            raw=damage.amount, final=applied, was_lethal=was_lethal
        )


__all__ = ["InteractableObject", "ObjectDamageResult"]
