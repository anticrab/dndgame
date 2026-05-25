"""PlayerIntent — намерения игрока за PC в ход.

Discriminated union вариантов: атака / движение / Dodge / Dash /
Disengage / EndTurn. Парсится pydantic'ом по полю ``kind``, как и
``MasterIntent``.

UI/AI собирает intent на каждом шаге хода; ``GameRunner`` транслирует
его в вызов соответствующего Action.

См. ``docs/ACTIONS.md`` §3 / §6.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from dnd.application.dto.ids import CreatureId, ObjectId, SpellId
from dnd.application.engine.actions.interact import InteractKind
from dnd.domain.values.direction import Direction
from dnd.domain.values.item import ItemId
from dnd.domain.values.square import Square


class _IntentBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AttackIntent(_IntentBase):
    """Атака экипированным оружием по цели."""

    kind: Literal["attack"] = "attack"
    target_id: CreatureId


class MoveIntent(_IntentBase):
    """Движение по пути. ``path`` — последовательность клеток без
    стартовой; каждая соседняя предыдущей."""

    kind: Literal["move"] = "move"
    path: tuple[Square, ...]


class DodgeIntent(_IntentBase):
    kind: Literal["dodge"] = "dodge"


class DashIntent(_IntentBase):
    kind: Literal["dash"] = "dash"


class DisengageIntent(_IntentBase):
    kind: Literal["disengage"] = "disengage"


class EndTurnIntent(_IntentBase):
    """Игрок завершает ход (явно). GameRunner после этого
    вызывает ``encounter.end_turn``."""

    kind: Literal["end_turn"] = "end_turn"


class InteractIntent(_IntentBase):
    """Игрок взаимодействует с интерактивным объектом (free action).

    ``interact_kind`` различает open/close/examine — конкретную
    семантику разруливает :class:`InteractAction`. Цель — объект в
    reach (5ft); проверка происходит в action'е, GameRunner лишь
    собирает params и логирует Forbidden.
    """

    kind: Literal["interact"] = "interact"
    target_object_id: ObjectId
    interact_kind: InteractKind


class BreakIntent(_IntentBase):
    """Игрок ломает интерактивный объект (action: атака по объекту с HP).

    ``attack_bonus`` и ``damage_expr`` GameRunner вычислит из
    ``actor.equipped_weapon`` (через ``weapon_attack_params``-логику);
    в intent'е нет — UI знает только id цели, не должен лезть в
    weapon-маталогию.
    """

    kind: Literal["break"] = "break"
    target_object_id: ObjectId


class PickupIntent(_IntentBase):
    """Игрок забирает предмет из сундука / другого контейнера (этап O-8).

    Free object interaction (как и Interact-open) — не тратит action.
    Контейнер должен быть в reach (5 ft) и открыт (или будет открыт
    автоматически, если ``locked=False``).

    ``qty`` — сколько единиц взять. ``None`` означает «всё из этого
    стака»; для non-stackable items эквивалентно 1.
    """

    kind: Literal["pickup"] = "pickup"
    target_object_id: ObjectId
    item_id: ItemId
    qty: int | None = Field(default=None, ge=1)


class StabilizeIntent(_IntentBase):
    """Игрок стабилизирует умирающего союзника (Медицина DC 10, action).

    Цель должна быть в dying (0 HP, спасброски) и в reach (5 фт);
    проверки — в :class:`StabilizeAction`, GameRunner лишь собирает params.
    """

    kind: Literal["stabilize"] = "stabilize"
    target_id: CreatureId


class CastSpellIntent(_IntentBase):
    """Игрок сотворяет заклинание (этап P1).

    ``target_id`` — None для SELF-заклинаний. Проверки (кастер, слот, цель,
    дальность) — в :class:`CastSpellAction`; GameRunner лишь собирает params.
    """

    kind: Literal["cast_spell"] = "cast_spell"
    spell_id: SpellId
    target_id: CreatureId | None = None
    # AoE (P2): точка прицеливания (AT_POINT) или направление (FROM_CASTER).
    target_point: Square | None = None
    direction: Direction | None = None


PlayerIntent = Annotated[
    AttackIntent
    | MoveIntent
    | DodgeIntent
    | DashIntent
    | DisengageIntent
    | EndTurnIntent
    | InteractIntent
    | BreakIntent
    | PickupIntent
    | StabilizeIntent
    | CastSpellIntent,
    Field(discriminator="kind"),
]


__all__ = [
    "AttackIntent",
    "BreakIntent",
    "CastSpellIntent",
    "DashIntent",
    "DisengageIntent",
    "DodgeIntent",
    "EndTurnIntent",
    "InteractIntent",
    "MoveIntent",
    "PickupIntent",
    "PlayerIntent",
    "StabilizeIntent",
]
