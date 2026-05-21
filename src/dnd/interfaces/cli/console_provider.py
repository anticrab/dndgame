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


# Защита от бесконечной рекурсии в re-prompt'ах. Аудит 15 CL-UX001:
# если игрок упорно выбирает «Attack без целей», после N циклов
# принудительно завершаем ход (последняя соломинка против бага UI).
_MAX_REPROMPTS = 5


@dataclass(slots=True)
class ConsoleIntentProvider:
    """Источник намерений через интерактивные prompt'ы.

    Поля ``prompt_*`` — слоты для подмены prompt'ов в тестах:
    функции принимают сообщение и список выборов, возвращают строку.
    В рантайме используют ``questionary`` (lazy import).
    """

    prompt_action: Callable[[str, list[str]], str] | None = None
    prompt_choice: Callable[[str, list[str]], str] | None = None
    prompt_text: Callable[[str], str] | None = None
    notify: Callable[[str], None] | None = None

    def next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent:
        return self._next_intent(actor, ctx, encounter, depth=0)

    def _next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
        depth: int,
    ) -> PlayerIntent:
        if depth >= _MAX_REPROMPTS:
            # Защита от циклической ошибки: «Attack без целей» снова и
            # снова. Завершаем ход, не теряем сессию.
            self._notify_user(
                "Too many invalid attempts — ending turn."
            )
            return EndTurnIntent()

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
                return self._build_attack_intent(actor, ctx, encounter, depth)
            case "Move":
                return self._build_move_intent(actor, ctx, encounter, depth)
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

    def _notify_user(self, message: str) -> None:
        """Сообщение игроку (warning / hint). Не теряет ход."""
        if self.notify is not None:
            self.notify(message)

    def _build_attack_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
        depth: int,
    ) -> PlayerIntent:
        actor_faction = encounter.factions[actor.id]
        targets = _list_reachable_hostiles(actor, ctx, encounter, actor_faction)
        if not targets:
            # Аудит 15 CL-UX001: не теряем ход тихо — сообщаем и снова
            # показываем меню.
            self._notify_user("No reachable targets — choose another action.")
            return self._next_intent(actor, ctx, encounter, depth + 1)
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
        depth: int,
    ) -> PlayerIntent:
        raw = self._ask_text(
            f"[{actor.name}] move to (x,y), e.g. 2,3 — current "
            f"{ctx.battlefield.position_of(actor.id)}:"
        )
        try:
            x_str, y_str = raw.split(",", 1)
            target = Square(int(x_str.strip()), int(y_str.strip()))
        except (ValueError, AttributeError):
            # Аудит 15 CL-UX001: невалидный ввод — re-prompt, не end turn.
            self._notify_user(
                f"Cannot parse coordinates from {raw!r}. Use format: x,y"
            )
            return self._next_intent(actor, ctx, encounter, depth + 1)
        if not ctx.battlefield.in_bounds(target):
            self._notify_user(
                f"{target} is out of bounds — pick coordinates within "
                f"{ctx.battlefield.width}x{ctx.battlefield.height}."
            )
            return self._next_intent(actor, ctx, encounter, depth + 1)
        # Строим прямой chebyshev-путь.
        path = _chebyshev_path(
            ctx.battlefield.position_of(actor.id), target
        )
        if not path:
            self._notify_user("Already at the target square.")
            return self._next_intent(actor, ctx, encounter, depth + 1)
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
