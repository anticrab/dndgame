"""BattleMode enum + ModeHandler Protocol + ModeScreenContext Protocol.

См. spec docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md §4.2.

ModeScreenContext декларирует **минимальный** набор атрибутов которые
handler требует от своего «screen». Это позволяет (1) тестировать
handler'ы через моки без поднятия BattleScreen, (2) mypy strict
проверяет контракт без циклических зависимостей.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dnd.application.engine.spells.area import AreaShapeRegistry
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ids import CreatureId
    from dnd.domain.values.spell import TargetingSpec
    from dnd.domain.values.square import Square


class BattleMode(Enum):
    NORMAL = "normal"
    MOVE = "move"
    TARGET = "target"
    AREA = "area"  # выбор зоны AoE-заклинания (P2)
    MULTI_TARGET = "multi_target"  # выбор нескольких целей (P2b)


@dataclass(frozen=True)
class OverlayData:
    """Что handler хочет показать на карте + в hint-полосе.

    Поля:
    * ``cursor`` — где рисовать курсор (или None);
    * ``highlights`` — ``{sq: style}``, рисуется поверх terrain'а
      (используется TARGET mode для подсветки целей);
    * ``path_preview`` — клетки маршрута для MOVE mode;
    * ``path_styles`` — override стиля для отдельных клеток пути
      (по-умолчанию все клетки рисуются ``green``; здесь можно
      пометить «жёлтые» — нужен Dash, или «красные» — overflow);
    * ``hint`` — короткая строка для ModeHintWidget'а (типа
      «MOVE: cursor=(15,8) cost=25/30 ft»).
    """

    cursor: Square | None = None
    highlights: dict[Square, str] = field(default_factory=dict)
    path_preview: tuple[Square, ...] = ()
    path_styles: dict[Square, str] = field(default_factory=dict)
    hint: str = ""


class ModeScreenContext(Protocol):
    """Контракт «screen»: атрибуты которые BattleScreen обещает иметь
    к моменту входа в mode. Установлены в `enter_mode` (L1-T9).

    ``_current_battlefield`` объявлен как ``Battlefield | None``, потому
    что BattleScreen инициализирует его лениво (в ``set_active_turn``).
    Handler'ы вызываются ТОЛЬКО когда BattleScreen уверен что
    battlefield установлен — это инвариант экрана; для mypy handler'ы
    могут `assert screen._current_battlefield is not None`.

    ``_current_actor_speed_ft`` нужен MOVE-mode для раскраски пути
    (зелёный в пределах speed_ft, жёлтый — Dash, красный — overflow).
    """

    _current_actor_position: Square
    _current_actor_speed_ft: int
    _current_battlefield: Battlefield | None
    _reachable_targets: list[tuple[CreatureId, Square]]
    # Нужен TargetModeHandler'у, чтобы достать HP/AC для hint'а
    # выбранной цели. Пусто для не-PC ходов; устанавливается в
    # set_active_turn вместе с остальным контекстом.
    _participants: dict[CreatureId, Creature]

    # AREA mode (P2): заклинание-зона, его дальность и реестр форм.
    _pending_area_spec: TargetingSpec | None
    _pending_area_range_ft: int
    _area_registry: AreaShapeRegistry

    # MULTI_TARGET mode (P2b): лимит выборов и разрешены ли повторы.
    _multi_max_targets: int
    _multi_allow_repeat: bool

    def _is_alive_lookup(self, cid: CreatureId) -> bool:
        """Жив ли participant. MoveModeHandler передаёт это в
        find_walkable_path, чтобы трупы не блокировали маршрут."""
        ...


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

    def overlay(self) -> OverlayData:
        """Что показывать сейчас (cursor / highlights / path / hint)."""
        ...


__all__ = ["BattleMode", "ModeHandler", "ModeScreenContext", "OverlayData"]
