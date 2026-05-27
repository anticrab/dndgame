"""TurnContext — мутабельный контекст одного хода существа.

См. ``docs/ACTIONS.md`` §3.

Содержит:

* зависимости движка (battlefield, dice_roller, modifier_applier,
  condition_service, event_bus, rng);
* счётчики экономики действий (action_used, bonus_action_used,
  reaction_used, movement_remaining_ft, free_object_interaction_used);
* информацию о порядке хода (round_number, turn_number_in_round).

**Не** делает:

* не выбирает действия (это AI / UI);
* не публикует события (это сами Action.execute);
* не проверяет правила атаки/движения — делегирует зависимостям.

Создаётся ``Encounter`` (этап F) для каждого хода каждого существа.
В этом MVP — ручная сборка в тестах и в composition-root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dnd.application.dto.action import ActionEconomyCost
from dnd.domain.entities.game_clock import GameClock
from dnd.domain.values.ids import CreatureId

if TYPE_CHECKING:
    from dnd.application.engine.condition_service import ConditionService
    from dnd.application.engine.modifier_applier import ModifierApplier
    from dnd.application.ports.dice_roller import DiceRoller
    from dnd.application.ports.event_bus import EventBus
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.ports.rng import RNG
    from dnd.domain.values.faction import Faction


@dataclass(slots=True)
class TurnContext:
    """Контекст одного хода. Mutable; меняется по ходу действий.

    Поля экономики обновляются только через ``spend()`` / ``spend_movement()``
    / ``start_new_round()`` — чтобы инвариант «не больше, чем разрешено
    PHB» проверялся в одном месте.
    """

    actor_id: CreatureId
    battlefield: Battlefield
    dice_roller: DiceRoller
    modifier_applier: ModifierApplier
    condition_service: ConditionService
    event_bus: EventBus
    rng: RNG

    # Все участники текущего боя (живые и нет). Действия лукапят цель
    # по CreatureId, не таская Creature в params (params — pydantic-DTO
    # без mutable-объектов). Encounter (этап F) заполняет это.
    participants: dict[CreatureId, Creature]

    movement_remaining_ft: int  # = speed * 1.0 в начале хода

    # Нужно MoveAction'у для PHB-2024 стр. 24: проход сквозь враждебных
    # запрещён, через союзника — стоит как difficult terrain (×2),
    # завершить ход в чужой клетке нельзя. Если ctx собирают вручную
    # без factions — fallback: «другие» трактуются как союзники
    # (легально для unit-тестов MoveAction без полноценного Encounter).
    factions: dict[CreatureId, Faction] = field(default_factory=dict)

    round_number: int = 1
    turn_number_in_round: int = 0

    # X0: общие игровые часы. Реальный общий clock проставляет Encounter
    # (X0-6); default_factory — чтобы ручная сборка ctx в тестах не ломалась.
    clock: GameClock = field(default_factory=GameClock)

    action_used: bool = False
    bonus_action_used: bool = False
    reaction_used: bool = False  # переживает между ходами в раунде
    free_object_interaction_used: bool = False

    # Флаг Disengage'а на этом ходу (PHB-2024 стр. 22): пока True,
    # выход из threatens-зоны не провоцирует opportunity attacks.
    # Устанавливается DisengageAction (E4); MoveAction (E3) уже читает.
    disengaged: bool = False

    # для отладки/UI — что уже произошло на этом ходу
    history: list[str] = field(default_factory=list)

    # --- проверки бюджета ---------------------------------------------

    def can_spend(self, cost: ActionEconomyCost) -> bool:
        """Можно ли потратить ресурс. Не мутирует состояние."""
        match cost:
            case ActionEconomyCost.ACTION:
                return not self.action_used
            case ActionEconomyCost.BONUS_ACTION:
                return not self.bonus_action_used
            case ActionEconomyCost.REACTION:
                return not self.reaction_used
            case ActionEconomyCost.MOVEMENT:
                # У движения нет «булевого» резерва — всегда True, конкретное
                # количество футов проверяется через can_move(feet).
                return True
            case ActionEconomyCost.FREE:
                # FREE покрывает и object interaction (1/ход), и речь (∞).
                # Конкретное действие, помеченное FREE, должно само
                # решать, использовать ли object_interaction. На уровне
                # TurnContext FREE всегда разрешён; для одного-в-ход
                # object interaction есть отдельная пара
                # can_use_object_interaction / use_object_interaction.
                return True

    def can_move(self, feet: int) -> bool:
        """Хватит ли футов движения. ``feet`` должен быть кратен 5."""
        if feet < 0 or feet % 5 != 0:
            raise ValueError(f"feet must be a non-negative multiple of 5, got {feet}")
        return feet <= self.movement_remaining_ft

    def can_use_object_interaction(self) -> bool:
        """Свободное object-interaction (PHB-2024 стр. 21) — 1 в ход."""
        return not self.free_object_interaction_used

    # --- траты --------------------------------------------------------

    def spend(self, cost: ActionEconomyCost) -> None:
        """Списать ресурс. ValueError, если бюджета нет.

        Контракт: вызывающий обязан вызвать ``can_spend(cost)`` до
        ``spend(cost)``. Парный API нужен, чтобы можно было «спросить»
        UI ещё до подтверждения действия — без побочных эффектов.
        """
        if not self.can_spend(cost):
            raise ValueError(f"no economy budget for {cost.value}")
        match cost:
            case ActionEconomyCost.ACTION:
                self.action_used = True
            case ActionEconomyCost.BONUS_ACTION:
                self.bonus_action_used = True
            case ActionEconomyCost.REACTION:
                self.reaction_used = True
            case ActionEconomyCost.MOVEMENT:
                # MOVEMENT тратится через spend_movement(feet) — у него
                # есть числовой аргумент. spend() ничего не делает.
                pass
            case ActionEconomyCost.FREE:
                # FREE сама по себе не отнимает; object-interaction —
                # через use_object_interaction().
                pass

    def spend_movement(self, feet: int) -> None:
        """Потратить футы движения. ValueError, если не хватает или
        некратно 5.
        """
        if not self.can_move(feet):
            raise ValueError(
                f"not enough movement: requested {feet} ft, have {self.movement_remaining_ft} ft"
            )
        self.movement_remaining_ft -= feet

    def use_object_interaction(self) -> None:
        """Потратить одно свободное object-interaction. ValueError, если
        уже использовано (PHB-2024 стр. 21).
        """
        if self.free_object_interaction_used:
            raise ValueError("free object interaction is already used this turn")
        self.free_object_interaction_used = True

    # --- между ходами / раундами --------------------------------------

    def start_new_round(self) -> None:
        """Сбросить ресурсы, которые «живут раунд» (reaction).

        Вызывается ``Encounter`` между раундами. Ход-зависимые ресурсы
        (action, bonus_action, movement, object_interaction) **не** трогаем —
        они принадлежат конкретному ходу и пересоздаются вместе с
        TurnContext.
        """
        self.reaction_used = False
        self.round_number += 1
