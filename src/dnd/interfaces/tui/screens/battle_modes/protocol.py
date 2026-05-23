"""BattleMode enum + ModeHandler Protocol + ModeScreenContext Protocol.

См. spec docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md §4.2.

ModeScreenContext декларирует **минимальный** набор атрибутов которые
handler требует от своего «screen». Это позволяет (1) тестировать
handler'ы через моки без поднятия BattleScreen, (2) mypy strict
проверяет контракт без циклических зависимостей.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dnd.application.dto.ids import CreatureId
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.values.square import Square


class BattleMode(Enum):
    NORMAL = "normal"
    MOVE = "move"
    TARGET = "target"


class ModeScreenContext(Protocol):
    """Контракт «screen»: атрибуты которые BattleScreen обещает иметь
    к моменту входа в mode. Установлены в `enter_mode` (L1-T9).

    ``_current_battlefield`` объявлен как ``Battlefield | None``, потому
    что BattleScreen инициализирует его лениво (в ``set_active_turn``).
    Handler'ы вызываются ТОЛЬКО когда BattleScreen уверен что
    battlefield установлен — это инвариант экрана; для mypy handler'ы
    могут `assert screen._current_battlefield is not None`.
    """

    _current_actor_position: Square
    _current_battlefield: Battlefield | None
    _reachable_targets: list[tuple[CreatureId, Square]]


class ModeHandler(Protocol):
    """Контракт для mode-handler'а. BattleScreen делегирует keypress'ы."""

    def on_enter(self, screen: ModeScreenContext) -> None:
        """Вызывается при входе в mode (после прошлого on_exit)."""
        ...

    def on_exit(self, screen: ModeScreenContext) -> None:
        """Вызывается при выходе. Очистка cursor/highlights."""
        ...

    def on_key(self, screen: ModeScreenContext, key: str) -> bool:
        """True если handler съел клавишу. False → bubble дальше."""
        ...

    def overlay_data(
        self,
    ) -> tuple[Square | None, dict[Square, str], tuple[Square, ...]]:
        """(cursor, highlights, path_preview) для MapWidget.refresh_from."""
        ...


__all__ = ["BattleMode", "ModeHandler", "ModeScreenContext"]
