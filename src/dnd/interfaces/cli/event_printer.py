"""EventPrinter — рендерит события движка в консоль через ``rich``.

Минимальный «гейм-лог»: одна строка на событие. UI красивее — TUI этап.

Подписывается на ``EngineEvent`` и форматирует под человеческий вид.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from rich.console import Console

from dnd.application.dto.engine_event import (
    AttackResolved,
    AttackRolled,
    DamageDealt,
    EncounterEnded,
    EngineEvent,
    HelpGranted,
    InitiativeRolled,
    MoveCompleted,
    MoveStepTaken,
    OpportunityAttackProvoked,
    RoundEnded,
    RoundStarted,
    SearchPerformed,
    StanceTaken,
    TurnEnded,
    TurnStarted,
)
from dnd.application.ports.event_bus import EventBus


class EventPrinter:
    """Подписчик-печатник.

    Использование::

        printer = EventPrinter(console)
        unsubscribe = printer.subscribe(event_bus)
        # ...игровой цикл...
        unsubscribe()
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def subscribe(self, bus: EventBus) -> Callable[[], None]:
        return bus.subscribe(EngineEvent, self._on_event)

    # --- private ----------------------------------------------------

    def _on_event(self, event: EngineEvent) -> None:
        handler = self._dispatch.get(type(event))
        if handler is None:
            return  # Roll*, прочее — не показываем в gamelog
        handler(self, event)

    def _print(self, text: str) -> None:
        self._console.print(text, highlight=False)

    # форматеры для конкретных событий ----------------------------------

    def _on_initiative(self, event: InitiativeRolled) -> None:
        order = ", ".join(
            f"{e.creature_id} ({e.total})" for e in event.order
        )
        self._print(f"[bold cyan]Initiative[/]: {order}")

    def _on_round_started(self, event: RoundStarted) -> None:
        self._print(f"\n[bold yellow]=== Round {event.round_number} ===[/]")

    def _on_round_ended(self, event: RoundEnded) -> None:
        self._print(f"[dim]— round {event.round_number} ended —[/]")

    def _on_turn_started(self, event: TurnStarted) -> None:
        tag = " (skipped)" if event.skipped else ""
        self._print(f"[bold]{event.actor_id}'s turn[/]{tag}")

    def _on_turn_ended(self, event: TurnEnded) -> None:
        # тихо
        del event

    def _on_attack(self, event: AttackRolled) -> None:
        if event.is_critical_hit:
            outcome = "[bold red]CRITICAL HIT[/]"
        elif event.is_critical_miss:
            outcome = "[dim]critical miss[/]"
        elif event.hit:
            outcome = "[green]hit[/]"
        else:
            outcome = "[red]miss[/]"
        adv_tag = ""
        if event.advantage and not event.disadvantage:
            adv_tag = " [cyan]adv[/]"
        elif event.disadvantage and not event.advantage:
            adv_tag = " [yellow]dis[/]"
        elif event.advantage and event.disadvantage:
            adv_tag = " [dim]adv+dis→flat[/]"
        roll_tag = (
            f"d20={event.d20_raw}→{event.total}{adv_tag}"
            if event.d20_raw
            else f"total={event.total}{adv_tag}"
        )
        # Круглые скобки, а не квадратные — rich-разметка съедает
        # `[...]` как inline style и весь блок исчез бы из вывода.
        self._print(
            f"  {event.attacker_id} attacks {event.target_id} "
            f"({roll_tag} vs AC {event.effective_ac}): {outcome}"
        )

    def _on_damage(self, event: DamageDealt) -> None:
        crit = " [bold]crit![/]" if event.is_critical else ""
        hp_tag = f" (HP {event.hp_after}/{event.hp_max})"
        self._print(
            f"  → {event.target_id} takes [red]{event.final_amount}[/] "
            f"{event.damage_type.value}{crit}{hp_tag}"
        )

    def _on_attack_resolved(self, event: AttackResolved) -> None:
        if event.downed:
            self._print(f"  ☠ {event.target_id} falls!")

    def _on_move_step(self, event: MoveStepTaken) -> None:
        # тихо — детали в MoveCompleted
        del event

    def _on_move_completed(self, event: MoveCompleted) -> None:
        self._print(
            f"  {event.actor_id}: {event.start_pos} → {event.end_pos} "
            f"({event.total_spent_ft} ft)"
        )

    def _on_provoked(self, event: OpportunityAttackProvoked) -> None:
        self._print(
            f"  ⚡ {event.actor_id} provokes opportunity from "
            f"{event.threatener_id}"
        )

    def _on_help(self, event: HelpGranted) -> None:
        self._print(
            f"  🤝 {event.helper_id} helps {event.ally_id} vs "
            f"{event.target_id}"
        )

    def _on_search(self, event: SearchPerformed) -> None:
        self._print(
            f"  🔍 {event.actor_id} {event.skill_kind}: {event.total}"
        )

    def _on_encounter_ended(self, event: EncounterEnded) -> None:
        if event.winners is None:
            verdict = "[bold yellow]DRAW[/]"
        else:
            verdict = f"[bold green]{event.winners.value.upper()} WINS[/]"
        if event.survivors:
            survivors = ", ".join(event.survivors)
            tail = f"\nSurvivors: {survivors}"
        else:
            tail = "\nNo survivors."
        self._print(
            f"\n[bold]=== ENCOUNTER ENDED ===[/]\n{verdict} "
            f"(round {event.round_number}){tail}"
        )

    def _on_stance(self, event: StanceTaken) -> None:
        # CL-UX002: Dodge/Dash/Disengage больше не «беззвучные».
        self._print(
            f"  [cyan]{event.actor_id} takes {event.stance.upper()}[/]"
        )

    # Карта типов → обработчики. ClassVar т.к. shared, не per-instance.
    _dispatch: ClassVar[dict[type[EngineEvent], Callable[[Any, Any], None]]] = {
        InitiativeRolled: lambda self, e: self._on_initiative(e),
        RoundStarted: lambda self, e: self._on_round_started(e),
        RoundEnded: lambda self, e: self._on_round_ended(e),
        TurnStarted: lambda self, e: self._on_turn_started(e),
        TurnEnded: lambda self, e: self._on_turn_ended(e),
        AttackRolled: lambda self, e: self._on_attack(e),
        DamageDealt: lambda self, e: self._on_damage(e),
        AttackResolved: lambda self, e: self._on_attack_resolved(e),
        MoveStepTaken: lambda self, e: self._on_move_step(e),
        MoveCompleted: lambda self, e: self._on_move_completed(e),
        OpportunityAttackProvoked: lambda self, e: self._on_provoked(e),
        HelpGranted: lambda self, e: self._on_help(e),
        SearchPerformed: lambda self, e: self._on_search(e),
        EncounterEnded: lambda self, e: self._on_encounter_ended(e),
        StanceTaken: lambda self, e: self._on_stance(e),
    }


__all__ = ["EventPrinter"]
