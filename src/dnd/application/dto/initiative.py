"""InitiativeEntry — запись результата броска инициативы для одного
participant'а.

См. ``docs/ENCOUNTER.md`` §2.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dnd.domain.values.ids import CreatureId, RollId


class InitiativeEntry(BaseModel):
    """Бросок инициативы одного существа.

    Поля для tie-break:

    * ``total`` — основной ключ сортировки (DESC);
    * ``d20_raw`` — сырой d20 (DESC) на случай равенства total;
    * ``dex_score`` — DEX score (DESC) при равенстве d20;
    * ``insertion_order`` — стабильный fallback (ASC).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    creature_id: CreatureId
    total: int
    d20_raw: int
    dex_score: int
    insertion_order: int
    roll_id: RollId


__all__ = ["InitiativeEntry"]
