"""ItemStack — пара (item, qty) для штабелируемых предметов.

В инвентаре одна и та же «вещь» может быть в нескольких экземплярах
(зелья, монеты, факелы). ItemStack — единица учёта: ссылка на
:class:`Item` + количество. Для не-stackable предметов qty всегда 1
(валидация в __post_init__).

Mutable qty специально: операции пополнения/расхода частые
(``inv.add(potion)`` ищет уже существующий стак и увеличивает qty),
делать каждый раз новый frozen-instance дорого и приводит к гонке
ссылок. Сам Item внутри — frozen, поэтому identity сохраняется.
"""

from __future__ import annotations

from dataclasses import dataclass

from dnd.domain.values.item import Item


@dataclass(slots=True)
class ItemStack:
    item: Item
    qty: int = 1

    def __post_init__(self) -> None:
        if self.qty < 1:
            raise ValueError(
                f"ItemStack qty must be >= 1, got {self.qty} "
                f"for {self.item.id} (нулевой стак следует удалять, "
                f"а не хранить)"
            )
        if not self.item.stackable and self.qty != 1:
            raise ValueError(
                f"ItemStack qty=1 only for non-stackable {self.item.id} "
                f"(kind={self.item.kind.value})"
            )

    @property
    def total_weight_lb(self) -> float:
        return self.item.weight_lb * self.qty


__all__ = ["ItemStack"]
