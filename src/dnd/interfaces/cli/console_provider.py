"""ConsoleIntentProvider — интерактивный источник намерений через
``questionary``.

UX:

* В начале хода показываем меню действий: Attack / Move / Dodge /
  Dash / Disengage / End Turn.
* Для Attack — спрашиваем цель из списка живых врагов в reach
  (или предупреждаем, что нет валидных целей).
* Для Move — спрашиваем координату цели; путь строится прямо к ней
  (chebyshev).

Минимальный CLI. Полноценные подсказки/предпросмотр кубов/превью урона
— пост-MVP.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dnd.application.dto.action import Allowed
from dnd.application.dto.ids import CreatureId
from dnd.application.dto.player_intent import (
    AttackIntent,
    DashIntent,
    DisengageIntent,
    DodgeIntent,
    EndTurnIntent,
    MoveIntent,
    PlayerIntent,
)
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square

_ACTION_CHOICES = [
    "Attack",
    "Move",
    "Dodge",
    "Dash",
    "Disengage",
    "End turn",
]


@dataclass(slots=True)
class ConsoleIntentProvider:
    """Источник намерений через интерактивные prompt'ы.

    Поле ``prompt`` оставлено для тестов: можно подменить
    функцию-провайдера значений (например, цикл по списку). На
    практике использует ``questionary.select`` / ``questionary.text``.
    """

    prompt_action: Callable[[str, list[str]], str] | None = None
    prompt_choice: Callable[[str, list[str]], str] | None = None
    prompt_text: Callable[[str], str] | None = None

    def next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent:
        choice = self._select(
            f"[{actor.name}] choose action:", _ACTION_CHOICES
        )
        match choice:
            case "End turn":
                return EndTurnIntent()
            case "Dodge":
                return DodgeIntent()
            case "Dash":
                return DashIntent()
            case "Disengage":
                return DisengageIntent()
            case "Attack":
                return self._build_attack_intent(actor, ctx, encounter)
            case "Move":
                return self._build_move_intent(actor, ctx, encounter)
        return EndTurnIntent()

    # --- private -----------------------------------------------------

    def _select(self, message: str, choices: list[str]) -> str:
        if self.prompt_action is not None:
            return self.prompt_action(message, choices)
        import questionary

        result = questionary.select(message, choices=choices).ask()
        # questionary.ask() возвращает None при Ctrl+C — трактуем как End turn.
        return result if result is not None else "End turn"

    def _select_choice(self, message: str, choices: list[str]) -> str:
        if self.prompt_choice is not None:
            return self.prompt_choice(message, choices)
        import questionary

        result = questionary.select(message, choices=choices).ask()
        return result if result is not None else choices[0]

    def _ask_text(self, message: str) -> str:
        if self.prompt_text is not None:
            return self.prompt_text(message)
        import questionary

        result = questionary.text(message).ask()
        return result if result is not None else ""

    def _build_attack_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent:
        actor_faction = encounter.factions[actor.id]
        targets = _list_reachable_hostiles(actor, ctx, encounter, actor_faction)
        if not targets:
            return EndTurnIntent()  # некого атаковать
        labels = [
            f"{cid} ({encounter.participants[cid].name}, HP {encounter.participants[cid].hit_points.current}/{encounter.participants[cid].hit_points.maximum})"
            for cid in targets
        ]
        picked = self._select_choice("Target:", labels)
        # Берём индекс выбранной метки → CreatureId.
        idx = labels.index(picked)
        return AttackIntent(target_id=targets[idx])

    def _build_move_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent:
        raw = self._ask_text(
            f"[{actor.name}] move to (x,y), e.g. 2,3 — current "
            f"{ctx.battlefield.position_of(actor.id)}:"
        )
        try:
            x_str, y_str = raw.split(",", 1)
            target = Square(int(x_str.strip()), int(y_str.strip()))
        except (ValueError, AttributeError):
            return EndTurnIntent()
        # Строим прямой chebyshev-путь.
        path = _chebyshev_path(
            ctx.battlefield.position_of(actor.id), target
        )
        if not path:
            return EndTurnIntent()
        return MoveIntent(path=tuple(path))


def _list_reachable_hostiles(
    actor: Creature,
    ctx: TurnContext,
    encounter: Encounter,
    actor_faction: Faction,
) -> list[CreatureId]:
    """Список ID живых врагов, по которым ``actor`` может атаковать
    сейчас (учёт LoS, cover, range — через can_perform_against)."""
    if actor.equipped_weapon is None:
        return []
    attack = AttackAction()
    result: list[CreatureId] = []
    for cid, cr in encounter.participants.items():
        if cid == actor.id or not cr.is_alive:
            continue
        if encounter.factions[cid] is actor_faction:
            continue
        if encounter.factions[cid] is Faction.NEUTRAL:
            continue
        try:
            params = weapon_attack_params(actor, cid)
        except ValueError:
            continue
        if isinstance(attack.can_perform_against(actor, params, ctx), Allowed):
            result.append(cid)
    return result


def _chebyshev_path(start: Square, target: Square) -> list[Square]:
    """Прямой пошаговый путь по диагонали от start к target. Не
    проверяет проходимость — MoveAction.can_perform_against это
    сделает."""
    if start == target:
        return []
    path: list[Square] = []
    cur = start
    while cur != target:
        dx = (target.x > cur.x) - (target.x < cur.x)
        dy = (target.y > cur.y) - (target.y < cur.y)
        nxt = Square(cur.x + dx, cur.y + dy)
        path.append(nxt)
        cur = nxt
    return path


__all__ = ["ConsoleIntentProvider"]
