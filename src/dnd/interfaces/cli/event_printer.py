"""EventPrinter — рендерит события движка в консоль через ``rich``.

Минимальный «гейм-лог»: одна строка на событие. UI красивее — TUI этап.

Подписывается на ``EngineEvent`` и форматирует под человеческий вид.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any, ClassVar

from rich.console import Console

from dnd.application.dto.engine_event import (
    AttackResolved,
    AttackRolled,
    ConcentrationBroken,
    CreatureDied,
    CreatureStabilized,
    DamageDealt,
    DeathSaveRolled,
    EncounterEnded,
    EngineEvent,
    HealingApplied,
    HelpGranted,
    InitiativeRolled,
    ItemPickedUp,
    LeveledUp,
    MoveCompleted,
    MoveStepTaken,
    ObjectDamaged,
    ObjectInteracted,
    OpportunityAttackProvoked,
    RoundEnded,
    RoundStarted,
    SearchPerformed,
    SpellCast,
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

    def __init__(
        self,
        console: Console | None = None,
        *,
        sink: Callable[[str], None] | None = None,
    ) -> None:
        """Если ``sink`` задан — каждый сформатированный markup-string
        идёт туда (для TUI: подаём в RichLog.write с markup=True,
        чтобы Textual сам разобрал разметку). Если нет — печатаем
        в rich.Console (CLI-режим)."""
        self._console = console or Console()
        self._sink = sink

    def subscribe(self, bus: EventBus) -> Callable[[], None]:
        return bus.subscribe(EngineEvent, self._on_event)

    def dispatch_event(self, event: EngineEvent) -> None:
        """Публичная точка для форматирования одного события без шины.

        Нужна, например, LogWidget'у в TUI, чтобы переиспользовать
        форматтер без подписки на bus.
        """
        self._on_event(event)

    # --- private ----------------------------------------------------

    def _on_event(self, event: EngineEvent) -> None:
        handler = self._dispatch.get(type(event))
        if handler is None:
            return  # Roll*, прочее — не показываем в gamelog
        handler(self, event)

    def _print(self, text: str) -> None:
        if self._sink is not None:
            # sink получает rich-markup строку как есть; интерпретация —
            # на стороне получателя (Textual RichLog с markup=True).
            self._sink(text)
            return
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

    def _on_interacted(self, event: ObjectInteracted) -> None:
        # K9 S1-3: лог InteractAction (free object interaction PHB-2024 стр. 21).
        loot_part = (
            f" → loot: {', '.join(event.loot)}" if event.loot else ""
        )
        self._print(
            f"  ✋ {event.actor_id} {event.kind} {event.object_id}"
            f"{loot_part}"
        )

    def _on_obj_damaged(self, event: ObjectDamaged) -> None:
        # K9 S1-3: лог BreakAction по InteractableObject.
        tag = " [bold red]BROKEN[/]" if event.broken else ""
        self._print(
            f"  💥 {event.attacker_id} hits {event.object_id} for "
            f"{event.final_amount} (HP {event.hp_after}){tag}"
        )

    def _on_death_save(self, event: DeathSaveRolled) -> None:
        # Q-6: спасброски от смерти (PHB-2024 стр. 27).
        tag = {
            "success": "[green]success[/]",
            "failure": "[red]failure[/]",
            "recovered": "[bold green]RECOVERED (1 HP)[/]",
        }[event.result]
        self._print(
            f"  🎲 {event.actor_id} death save: {event.d20_raw} → {tag} "
            f"([green]{event.successes}[/]/[red]{event.failures}[/])"
        )

    def _on_died(self, event: CreatureDied) -> None:
        self._print(f"  💀 [bold red]{event.actor_id} died[/]")

    def _on_stabilized(self, event: CreatureStabilized) -> None:
        self._print(f"  ✚ [green]{event.by} stabilizes {event.actor_id}[/]")

    def _on_concentration_broken(self, event: ConcentrationBroken) -> None:
        self._print(
            f"  ✘ [magenta]{event.actor_id} теряет концентрацию[/] "
            f"({event.spell_id}; спасбросок {event.roll_total} < {event.dc})"
        )

    def _on_leveled_up(self, event: LeveledUp) -> None:
        feats = (
            f" ({', '.join(event.features_gained)})" if event.features_gained else ""
        )
        self._print(
            f"  ⭐ [bold yellow]{event.actor_id} reaches level {event.new_level}![/] "
            f"+{event.hp_gained} HP{feats}"
        )

    def _on_spell_cast(self, event: SpellCast) -> None:
        # ✨ caster casts Spell [at target(s)]. MULTI → перечисляем цели с
        # числом попаданий (✦×N), SINGLE — одна цель, AoE/SELF — без целей.
        if event.target_ids:
            counts = Counter(event.target_ids)
            targets = ", ".join(
                f"{cid}×{n}" if n > 1 else f"{cid}" for cid, n in counts.items()
            )
            at = f" at {targets}"
        elif event.target_id is not None:
            at = f" at {event.target_id}"
        else:
            at = ""
        self._print(f"  ✨ [magenta]{event.caster_id} casts {event.spell_name}[/]{at}")

    def _on_healing(self, event: HealingApplied) -> None:
        self._print(
            f"  ✚ [green]{event.target_id} heals {event.amount}[/] "
            f"(HP {event.hp_after}/{event.hp_max})"
        )

    def _on_picked_up(self, event: ItemPickedUp) -> None:
        # O-audit MAJOR-2: без этого лог был пуст при pickup.
        qty_part = f"{event.qty}× " if event.qty > 1 else ""
        self._print(
            f"  [green]✋ {event.actor_id} picked up "
            f"{qty_part}{event.item_name}[/] [dim]from {event.source}[/]"
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
        ObjectInteracted: lambda self, e: self._on_interacted(e),
        ObjectDamaged: lambda self, e: self._on_obj_damaged(e),
        ItemPickedUp: lambda self, e: self._on_picked_up(e),
        DeathSaveRolled: lambda self, e: self._on_death_save(e),
        CreatureDied: lambda self, e: self._on_died(e),
        CreatureStabilized: lambda self, e: self._on_stabilized(e),
        ConcentrationBroken: lambda self, e: self._on_concentration_broken(e),
        SpellCast: lambda self, e: self._on_spell_cast(e),
        LeveledUp: lambda self, e: self._on_leveled_up(e),
        HealingApplied: lambda self, e: self._on_healing(e),
    }


__all__ = ["EventPrinter"]
