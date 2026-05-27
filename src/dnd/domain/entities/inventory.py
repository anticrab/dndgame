"""Inventory — mutable entity, рюкзак существа.

Содержит список :class:`ItemStack`. Mutable, потому что предметы
добавляются/тратятся горячо (Pickup/Drop/Use каждый ход).
Slots ограничения через ``slot_limit``; weight ограничение через
``weight_limit_lb``. Если лимит ноль/None — без ограничений
(для монстров и chest'ов).

API:
* :meth:`add` — кладёт стак, авто-стакает если items совпадают и
  stackable=True. Возвращает количество, которое НЕ влезло
  (overflow по slots/weight).
* :meth:`remove_by_id` — берёт стак по item_id; для not-stackable
  убирает один (qty=1 удаляется целиком), для stackable
  декрементит qty (или удаляет, если qty доходит до 0).
* :meth:`find_by_id` / :meth:`contains` — поиск без мутации.
* :meth:`total_weight_lb` — сумма по всем стакам.

Не входит сюда: equip-slot'ы (отдельный аспект Creature, O-8),
auto-sort, категории-вкладки UI (TUI-логика O-9).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dnd.domain.values.item import Item, ItemId
from dnd.domain.values.item_stack import ItemStack


@dataclass(slots=True)
class Inventory:
    stacks: list[ItemStack] = field(default_factory=list)
    slot_limit: int | None = None
    weight_limit_lb: float | None = None

    def __post_init__(self) -> None:
        if self.slot_limit is not None and self.slot_limit < 0:
            raise ValueError(f"slot_limit must be >= 0 (or None), got {self.slot_limit}")
        if self.weight_limit_lb is not None and self.weight_limit_lb < 0:
            raise ValueError(f"weight_limit_lb must be >= 0 (or None), got {self.weight_limit_lb}")

    # --- queries ----------------------------------------------------

    def find_by_id(self, item_id: ItemId) -> ItemStack | None:
        for s in self.stacks:
            if s.item.id == item_id:
                return s
        return None

    def contains(self, item_id: ItemId) -> bool:
        return self.find_by_id(item_id) is not None

    def total_weight_lb(self) -> float:
        return sum(s.total_weight_lb for s in self.stacks)

    def slot_count(self) -> int:
        return len(self.stacks)

    # --- mutation ---------------------------------------------------

    def add(self, item: Item, qty: int = 1) -> int:
        """Положить ``qty`` предметов. Возвращает overflow — сколько
        НЕ влезло (по слотам/весу). 0 — всё уместилось.

        Stackable item с уже существующим стаком пополняет его (один
        слот, не два). Non-stackable добавляет ``qty`` отдельных
        стаков по 1 (каждый занимает слот).
        """
        if qty < 1:
            raise ValueError(f"qty must be >= 1, got {qty}")

        remaining = qty
        if item.stackable:
            existing = self.find_by_id(item.id)
            allowed = self._fit_quantity(item, remaining, existing_stack=existing)
            if existing is None:
                if allowed > 0:
                    self.stacks.append(ItemStack(item, qty=allowed))
            else:
                existing.qty += allowed
            return remaining - allowed

        # non-stackable: каждая единица — отдельный слот
        placed = 0
        while placed < remaining:
            allowed_one = self._fit_quantity(item, 1, existing_stack=None)
            if allowed_one == 0:
                break
            self.stacks.append(ItemStack(item, qty=1))
            placed += 1
        return remaining - placed

    def remove_one(self, item_id: ItemId) -> Item | None:
        """Убрать одну единицу (1 stackable из стака, либо один
        non-stackable стак целиком). Возвращает Item, либо None
        если ничего не нашлось."""
        stack = self.find_by_id(item_id)
        if stack is None:
            return None
        item = stack.item
        if not item.stackable or stack.qty <= 1:
            self.stacks.remove(stack)
        else:
            stack.qty -= 1
        return item

    # --- internals --------------------------------------------------

    def _fit_quantity(
        self,
        item: Item,
        wanted: int,
        *,
        existing_stack: ItemStack | None,
    ) -> int:
        """Сколько из ``wanted`` штук влезает в текущие лимиты.

        Slot-лимит даёт +1 слот только если нет existing_stack
        (пополнение существующего слот не занимает).
        """
        if self.slot_limit is not None:
            new_slot_needed = existing_stack is None
            if new_slot_needed and self.slot_count() >= self.slot_limit:
                return 0
        if self.weight_limit_lb is None:
            return wanted
        free_weight = self.weight_limit_lb - self.total_weight_lb()
        if item.weight_lb <= 0:
            # бесвесные предметы (записки, токены) — только slot-лимит
            return wanted
        max_by_weight = int(free_weight // item.weight_lb)
        return max(0, min(wanted, max_by_weight))


__all__ = ["Inventory"]
