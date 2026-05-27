"""GameClock (X0) — единые игровые часы. Канон — раунд. Бой двигает +1 раунд на
границе раунда; исследование (X) будет двигать по стоимости действий. Монотонны
(только вперёд).
"""

from __future__ import annotations

from dnd.domain.values.duration import Duration


class GameClock:
    """Счётчик игрового времени в раундах (старт 0, неубывающий)."""

    def __init__(self, now_round: int = 0) -> None:
        if now_round < 0:
            raise ValueError(f"now_round must be >= 0, got {now_round}")
        self.now_round = now_round

    def advance(self, rounds: int) -> None:
        if rounds < 0:
            raise ValueError(f"advance requires rounds >= 0, got {rounds}")
        self.now_round += rounds

    def advance_minutes(self, n: int) -> None:
        self.advance(n * Duration.ROUNDS_PER_MINUTE)

    def advance_hours(self, n: int) -> None:
        self.advance(n * Duration.ROUNDS_PER_HOUR)

    def expires_at(self, duration: Duration) -> int | None:
        """Раунд, на котором эффект истечёт: ``now_round + duration``. ``None`` —
        длительность без счётного предела (эффект не снимается по часам)."""
        rounds = duration.to_rounds()
        return None if rounds is None else self.now_round + rounds


__all__ = ["GameClock"]
