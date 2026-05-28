"""ItemUseSpec (U) — как предмет доставляет эффект-пакет.

Единый slotless-каст (см. ``application/engine/spells/resolve.py``): сам эффект
живёт в каталоге заклинаний (``data/content/spells.yaml``), а предмет лишь
ссылается на запись через ``effect_id`` — никакого дублирования логики
лечения/баффа/урона.

Domain не зависит от application: ``economy`` хранится строкой
(``"action"``/``"bonus_action"``), конверсию в ``ActionEconomyCost`` делает
``UseItemAction``. Флаг ``is_scroll`` развязывает ввод «силы» эффекта —
``UseItemAction`` подставит ``SpellPower.scroll(spell.level)`` или
``SpellPower.potion()`` (см. ``SpellPower``).
"""

from __future__ import annotations

from dataclasses import dataclass

from dnd.domain.values.ids import SpellId

_ECONOMY: frozenset[str] = frozenset({"action", "bonus_action"})


@dataclass(frozen=True, slots=True)
class ItemUseSpec:
    """Обвязка доставки эффекта предмета.

    :param effect_id: id записи эффект-пакета в каталоге заклинаний.
    :param economy: какая часть экономики тратится (``"action"`` / ``"bonus_action"``).
    :param consumed: списывается ли единица из инвентаря по использованию.
    :param is_scroll: True → ``SpellPower.scroll(level)`` (фикс-Сл PHB);
        False → ``SpellPower.potion()`` (ability_mod=0). Подменяется в
        ``UseItemAction`` при вызове ``resolve_and_apply_spell``.
    """

    effect_id: SpellId
    economy: str = "action"
    consumed: bool = True
    is_scroll: bool = False

    def __post_init__(self) -> None:
        if self.economy not in _ECONOMY:
            raise ValueError(f"economy must be one of {sorted(_ECONOMY)}, got {self.economy!r}")


__all__ = ["ItemUseSpec"]
