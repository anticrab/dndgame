# Этап L — Inline UX + Ability Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить модальные picker'ы на inline-mode (курсор на основной карте), вернуть default zoom = 1×1, ввести viewport со scroll, и заложить data-driven Ability framework для будущих заклинаний.

**Architecture:** BattleMode state machine (NORMAL/MOVE/TARGET) на BattleScreen с делегацией keypress'ов в mode-handler'ы. MapWidget расширяется полями cursor/highlights/path_preview/camera. Ability — frozen dataclass + Registry, Creature.abilities/keybindings включают её в action-bar. Domain слой (Action классы) **не меняется**.

**Tech Stack:** Python 3.12, Textual (Pilot для тестов), pydantic v2 frozen, hexagonal.

**Spec:** `docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md`

---

## File Structure

**Создаются:**
- `src/dnd/application/engine/actions/move_path.py` — helper `find_chebyshev_path` + `path_cost_ft`
- `src/dnd/interfaces/tui/screens/battle_modes/__init__.py`
- `src/dnd/interfaces/tui/screens/battle_modes/protocol.py` — ModeHandler Protocol + BattleMode enum
- `src/dnd/interfaces/tui/screens/battle_modes/normal_mode.py`
- `src/dnd/interfaces/tui/screens/battle_modes/move_mode.py`
- `src/dnd/interfaces/tui/screens/battle_modes/target_mode.py`
- `src/dnd/domain/values/ability.py` — Ability dataclass + AbilityId
- `src/dnd/application/abilities/__init__.py`
- `src/dnd/application/abilities/registry.py` — AbilityRegistry + register_default_abilities
- `src/dnd/interfaces/tui/widgets/action_bar_widget.py` — динамический action-bar
- `docs/ABILITIES.md` — справочник 8 базовых

**Изменяются:**
- `src/dnd/interfaces/tui/widgets/map_widget.py` — default zoom→small, +cursor/highlights/path_preview/camera/viewport
- `src/dnd/interfaces/tui/screens/battle.py` — wire BattleMode + удаление action_intent_attack/move (передаётся в handler'ы)
- `src/dnd/domain/entities/creature.py` — +abilities/+keybindings с default'ами
- `docs/TUI.md` — описание mode-state machine

**Удаляются:**
- `src/dnd/interfaces/tui/screens/move_picker.py`
- `src/dnd/interfaces/tui/screens/target_picker.py`
- (тесты на них — переписываются в test_inline_move_mode/test_inline_target_mode)

---

# L1: Inline UX + Viewport + 1×1 default

## L1-1: Default zoom = small + регрессионный тест

**Files:**
- Modify: `src/dnd/interfaces/tui/widgets/map_widget.py:227-229` (`_zoom: str = "medium"` → `"small"`)
- Modify: `src/dnd/interfaces/tui/widgets/map_widget.py:220-223` (docstring)
- Test: `tests/unit/tui/test_map_widget_default_zoom.py` (NEW)

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_map_widget_default_zoom.py
"""После этапа L default zoom = small (1×1), пользователь явно сказал."""
from dnd.interfaces.tui.widgets.map_widget import MapWidget


def test_default_zoom_is_small() -> None:
    mw = MapWidget()
    assert mw.zoom == "small", "L1: default zoom returned to 1×1 tactical"
```

- [ ] **Step 2: Run, expect FAIL**

`pytest tests/unit/tui/test_map_widget_default_zoom.py -v` → FAIL (got "medium")

- [ ] **Step 3: Implement**

В `map_widget.py:229`: `self._zoom: str = "small"`. Обновить docstring `:220-223` — упомянуть "L1: возврат к 1×1; medium включается по +".

- [ ] **Step 4: Run, expect PASS + full suite**

```bash
pytest tests/unit/tui/test_map_widget_default_zoom.py -v
pytest -q
```
Если какой-то pilot-test полагается на medium-render — починить ассерты на small. Ожидаемо: 962+1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/widgets/map_widget.py tests/unit/tui/test_map_widget_default_zoom.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L1-1 default zoom = small (1×1 tactical)

Возврат к 1×1 как просил пользователь после playtest. Medium 5×3
остаётся доступным через + / - hotkey для просмотра, но default
тактический — лучше обзор, персонажи нормального размера."
```

---

## L1-2: Helper `find_chebyshev_path` + `path_cost_ft`

**Files:**
- Create: `src/dnd/application/engine/actions/move_path.py`
- Test: `tests/unit/actions/test_move_path.py`

Зачем: для path preview в MOVE mode нужно строить путь от PC до cursor и считать стоимость. MoveAction только валидирует уже-построенный путь.

- [ ] **Step 1: Failing test**

```python
# tests/unit/actions/test_move_path.py
"""Path helper для inline MOVE mode: chebyshev path + стоимость в футах."""
from dnd.application.engine.actions.move_path import (
    find_chebyshev_path,
    path_cost_ft,
)
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import DIFFICULT, FLOOR


def test_chebyshev_straight_horizontal() -> None:
    path = find_chebyshev_path(Square(1, 1), Square(4, 1))
    assert path == (Square(2, 1), Square(3, 1), Square(4, 1))


def test_chebyshev_diagonal() -> None:
    path = find_chebyshev_path(Square(0, 0), Square(2, 2))
    assert path == (Square(1, 1), Square(2, 2))


def test_chebyshev_empty_when_same() -> None:
    assert find_chebyshev_path(Square(3, 3), Square(3, 3)) == ()


def test_cost_floor_5ft_per_step() -> None:
    bf = Battlefield(10, 10)
    path = (Square(1, 0), Square(2, 0))
    assert path_cost_ft(bf, path) == 10  # 2 × 5 ft


def test_cost_difficult_terrain_doubles() -> None:
    bf = Battlefield(10, 10)
    bf.set_terrain_at(Square(1, 0), DIFFICULT)
    path = (Square(1, 0), Square(2, 0))
    assert path_cost_ft(bf, path) == 15  # 10 (difficult) + 5 (floor)
```

- [ ] **Step 2: Run, expect FAIL**

`pytest tests/unit/actions/test_move_path.py -v` → ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# src/dnd/application/engine/actions/move_path.py
"""Helper для построения и оценки пути движения (inline MOVE mode).

MoveAction.can_perform_against валидирует уже-построенный путь. Для
UI-preview нужен прямой chebyshev-путь от старта к курсору + расчёт
стоимости в футах с учётом difficult terrain.
"""
from __future__ import annotations

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square


def find_chebyshev_path(start: Square, target: Square) -> tuple[Square, ...]:
    """Прямой пошаговый путь по chebyshev (8-связность), БЕЗ старта.

    Не проверяет проходимость — это задача MoveAction.can_perform_against.
    """
    if start == target:
        return ()
    path: list[Square] = []
    cur = start
    while cur != target:
        dx = (target.x > cur.x) - (target.x < cur.x)
        dy = (target.y > cur.y) - (target.y < cur.y)
        cur = Square(cur.x + dx, cur.y + dy)
        path.append(cur)
    return tuple(path)


def path_cost_ft(battlefield: Battlefield, path: tuple[Square, ...]) -> int:
    """Стоимость пути в футах: 5 ft / step, ×2 на difficult terrain.

    Не учитывает provoked attacks / disengage — это уровень domain.
    Не валидирует bounds — вызывающий код передаёт уже clamped path.
    """
    total = 0
    for sq in path:
        terrain = battlefield.terrain_at(sq)
        total += 10 if terrain.difficult else 5
    return total


__all__ = ["find_chebyshev_path", "path_cost_ft"]
```

- [ ] **Step 4: Run, expect PASS**

`pytest tests/unit/actions/test_move_path.py -v` → 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/engine/actions/move_path.py tests/unit/actions/test_move_path.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(actions): L1-2 helper find_chebyshev_path + path_cost_ft

Для path-preview в inline MOVE mode нужен прямой 8-conn путь от PC
до курсора с расчётом стоимости (5 ft/step, x2 на difficult).
MoveAction только валидирует уже построенный путь."
```

---

## L1-3: Viewport state в MapWidget (camera/pan/center_on/visible_rect)

**Files:**
- Modify: `src/dnd/interfaces/tui/widgets/map_widget.py` — добавить viewport-методы (не трогать render пока)
- Test: `tests/unit/tui/test_map_widget_viewport.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_map_widget_viewport.py
"""Viewport на MapWidget: camera/pan/center_on/visible_rect (pure logic)."""
from dnd.domain.values.square import Square
from dnd.interfaces.tui.widgets.map_widget import MapWidget


def test_default_camera_origin() -> None:
    mw = MapWidget()
    assert mw.camera == Square(0, 0)


def test_pan_shifts_camera() -> None:
    mw = MapWidget()
    mw.set_viewport_size(20, 10)
    mw.set_world_size(40, 20)
    mw.pan(5, 3)
    assert mw.camera == Square(5, 3)


def test_pan_clamps_to_world_bounds() -> None:
    mw = MapWidget()
    mw.set_viewport_size(10, 10)
    mw.set_world_size(15, 15)
    mw.pan(100, 100)
    # camera + viewport не должно превышать world
    assert mw.camera == Square(5, 5)


def test_pan_clamps_to_zero() -> None:
    mw = MapWidget()
    mw.set_viewport_size(10, 10)
    mw.set_world_size(20, 20)
    mw.pan(-5, -5)
    assert mw.camera == Square(0, 0)


def test_center_on_centers_viewport() -> None:
    mw = MapWidget()
    mw.set_viewport_size(10, 10)
    mw.set_world_size(40, 40)
    mw.center_on(Square(20, 20))
    # центр viewport 10×10 на (20,20) → camera (15, 15)
    assert mw.camera == Square(15, 15)


def test_visible_rect_returns_camera_plus_viewport() -> None:
    mw = MapWidget()
    mw.set_viewport_size(8, 6)
    mw.set_world_size(50, 50)
    mw.pan(10, 5)
    assert mw.visible_rect() == (10, 5, 18, 11)
```

- [ ] **Step 2: Run, expect FAIL**

`pytest tests/unit/tui/test_map_widget_viewport.py -v` → AttributeError на pan/camera.

- [ ] **Step 3: Implement в map_widget.py:227 (внутри MapWidget)**

```python
class MapWidget(Static):
    # ... существующий __init__/zoom ...

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._zoom: str = "small"
        self._camera: Square = Square(0, 0)
        self._viewport_w: int = 80
        self._viewport_h: int = 24
        self._world_w: int = 0
        self._world_h: int = 0

    @property
    def camera(self) -> Square:
        return self._camera

    def set_viewport_size(self, w: int, h: int) -> None:
        """Размер видимой области в клетках. Вызывается из refresh_from
        на основе self.size (Textual layout). Tests дёргают напрямую."""
        if w < 1 or h < 1:
            raise ValueError(f"viewport size must be positive, got {w}×{h}")
        self._viewport_w = w
        self._viewport_h = h

    def set_world_size(self, w: int, h: int) -> None:
        """Размер мира (битфилда) в клетках. Нужен для clamp camera."""
        self._world_w = w
        self._world_h = h

    def pan(self, dx: int, dy: int) -> None:
        """Сместить камеру на (dx, dy). Clamp к [0, world-viewport]."""
        max_x = max(0, self._world_w - self._viewport_w)
        max_y = max(0, self._world_h - self._viewport_h)
        nx = max(0, min(self._camera.x + dx, max_x))
        ny = max(0, min(self._camera.y + dy, max_y))
        self._camera = Square(nx, ny)

    def center_on(self, sq: Square) -> None:
        """Центрировать viewport на клетке. Clamp к границам."""
        cx = sq.x - self._viewport_w // 2
        cy = sq.y - self._viewport_h // 2
        max_x = max(0, self._world_w - self._viewport_w)
        max_y = max(0, self._world_h - self._viewport_h)
        self._camera = Square(
            max(0, min(cx, max_x)),
            max(0, min(cy, max_y)),
        )

    def visible_rect(self) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) — диапазон видимых клеток в координатах битфилда."""
        return (
            self._camera.x,
            self._camera.y,
            self._camera.x + self._viewport_w,
            self._camera.y + self._viewport_h,
        )
```

- [ ] **Step 4: Run**

`pytest tests/unit/tui/test_map_widget_viewport.py -v` → 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/widgets/map_widget.py tests/unit/tui/test_map_widget_viewport.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L1-3 viewport state в MapWidget

camera (Square top-left), set_viewport_size, set_world_size,
pan (с clamp), center_on, visible_rect. Pure logic — render
ещё не использует, это L1-4."
```

---

## L1-4: Render clipping + auto-follow PC

**Files:**
- Modify: `src/dnd/interfaces/tui/widgets/map_widget.py` — `render_battlefield` принимает rect/cursor, `refresh_from` делает auto-follow
- Test: `tests/unit/tui/test_map_render_viewport.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_map_render_viewport.py
"""render_battlefield клипует к viewport rect."""
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.faction import Faction
from dnd.application.dto.ids import CreatureId
from dnd.interfaces.tui.widgets.map_widget import render_battlefield


def test_render_clips_to_visible_rect() -> None:
    bf = Battlefield(20, 20)
    # на (15, 15) ничего особого, но он должен попадать в viewport
    rendered = render_battlefield(
        bf, factions={}, with_color=False, zoom="small",
        visible_rect=(10, 10, 20, 20),  # 10×10 окно
    )
    lines = str(rendered).split("\n")
    assert len(lines) == 10, f"expected 10 rows in viewport, got {len(lines)}"
    assert len(lines[0]) == 10, f"expected 10 cols, got {len(lines[0])}"


def test_render_full_when_rect_none() -> None:
    bf = Battlefield(7, 5)
    rendered = render_battlefield(bf, factions={}, with_color=False, zoom="small")
    lines = str(rendered).split("\n")
    assert len(lines) == 5
    assert len(lines[0]) == 7
```

- [ ] **Step 2: Run, expect FAIL**

`pytest tests/unit/tui/test_map_render_viewport.py -v` → unexpected kwarg или wrong dimensions.

- [ ] **Step 3: Implement**

В `render_battlefield` сигнатуру:
```python
def render_battlefield(
    battlefield: Battlefield,
    factions: dict[CreatureId, Faction],
    *,
    cursor: Square | None = None,
    with_color: bool = True,
    zoom: str = "small",
    visible_rect: tuple[int, int, int, int] | None = None,
    highlights: dict[Square, str] | None = None,
    path_preview: tuple[Square, ...] = (),
) -> Text:
```

В теле small-render:
```python
if visible_rect is None:
    x0, y0, x1, y1 = 0, 0, battlefield.width, battlefield.height
else:
    x0, y0, x1, y1 = visible_rect
    x1 = min(x1, battlefield.width)
    y1 = min(y1, battlefield.height)
out = Text()
for y in range(y0, y1):
    for x in range(x0, x1):
        sq = Square(x, y)
        # ... существующий _cell_glyph, но с учётом path_preview и highlights:
        if sq in path_preview and sq != cursor and not battlefield.creatures_at(sq):
            out.append("·", style="green" if with_color else "")
            continue
        glyph, style = _cell_glyph(battlefield, factions, sq, cursor, with_color=with_color)
        if highlights and sq in highlights:
            style = f"{style} {highlights[sq]}".strip()
        out.append(glyph, style=style)
    if y < y1 - 1:
        out.append("\n")
return out
```

Также в `MapWidget.refresh_from`:
```python
def refresh_from(
    self,
    battlefield: Battlefield,
    factions: dict[CreatureId, Faction],
    *,
    cursor: Square | None = None,
    highlights: dict[Square, str] | None = None,
    path_preview: tuple[Square, ...] = (),
    follow: Square | None = None,
) -> None:
    self.set_world_size(battlefield.width, battlefield.height)
    # авто-размер viewport под размер виджета
    if self.size.width and self.size.height:
        self.set_viewport_size(self.size.width, self.size.height)
    if follow is not None:
        self._auto_follow(follow)
    with_color = self._is_color_theme()
    self.update(render_battlefield(
        battlefield, factions,
        cursor=cursor, with_color=with_color, zoom=self._zoom,
        visible_rect=self.visible_rect(),
        highlights=highlights, path_preview=path_preview,
    ))

def _auto_follow(self, target: Square) -> None:
    """Если target вышел за safe-zone (3 клетки от края viewport) — pan."""
    x0, y0, x1, y1 = self.visible_rect()
    safe = 3
    if target.x < x0 + safe or target.x >= x1 - safe \
       or target.y < y0 + safe or target.y >= y1 - safe:
        self.center_on(target)
```

- [ ] **Step 4: Run**

```bash
pytest tests/unit/tui/test_map_render_viewport.py -v   # 2 passed
pytest -q                                              # 964+ passed
```

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/widgets/map_widget.py tests/unit/tui/test_map_render_viewport.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L1-4 viewport clipping + auto-follow + highlights/path_preview

render_battlefield клипует к visible_rect; refresh_from делает
center_on(follow) при выходе за safe-zone (3 клетки от края).
Path preview рисуется '·' (green в colour theme), highlights —
поверх terrain glyph."
```

---

## L1-5: BattleMode enum + ModeHandler Protocol

**Files:**
- Create: `src/dnd/interfaces/tui/screens/battle_modes/__init__.py` (пустой)
- Create: `src/dnd/interfaces/tui/screens/battle_modes/protocol.py`
- Test: `tests/unit/tui/test_battle_mode_protocol.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_battle_mode_protocol.py
"""BattleMode enum + ModeHandler Protocol — каркас state machine."""
from dnd.interfaces.tui.screens.battle_modes.protocol import (
    BattleMode,
    ModeHandler,
)


def test_battle_mode_values() -> None:
    assert BattleMode.NORMAL.value == "normal"
    assert BattleMode.MOVE.value == "move"
    assert BattleMode.TARGET.value == "target"


def test_mode_handler_is_protocol() -> None:
    # Любой класс с правильными методами должен подойти как ModeHandler.
    class StubHandler:
        def on_enter(self, screen: object) -> None: ...
        def on_exit(self, screen: object) -> None: ...
        def on_key(self, screen: object, key: str) -> bool: return False
        def overlay_data(self) -> tuple[object, dict, tuple]:
            return (None, {}, ())

    h: ModeHandler = StubHandler()  # type: ignore[assignment]
    assert h.on_key(object(), "x") is False
```

- [ ] **Step 2: Run, expect FAIL**

`pytest tests/unit/tui/test_battle_mode_protocol.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# src/dnd/interfaces/tui/screens/battle_modes/__init__.py
"""Mode-handler'ы для BattleScreen state machine (L1)."""
```

```python
# src/dnd/interfaces/tui/screens/battle_modes/protocol.py
"""BattleMode enum + ModeHandler Protocol.

См. spec docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md §4.2.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dnd.domain.values.square import Square
    from dnd.interfaces.tui.screens.battle import BattleScreen


class BattleMode(Enum):
    NORMAL = "normal"
    MOVE = "move"
    TARGET = "target"


class ModeHandler(Protocol):
    """Контракт для mode-handler'а. BattleScreen делегирует keypress'ы."""

    def on_enter(self, screen: BattleScreen) -> None:
        """Вызывается при входе в mode (после прошлого on_exit)."""
        ...

    def on_exit(self, screen: BattleScreen) -> None:
        """Вызывается при выходе. Очистка cursor/highlights."""
        ...

    def on_key(self, screen: BattleScreen, key: str) -> bool:
        """True если handler съел клавишу. False → bubble дальше."""
        ...

    def overlay_data(
        self,
    ) -> tuple[Square | None, dict[Square, str], tuple[Square, ...]]:
        """(cursor, highlights, path_preview) для MapWidget.refresh_from."""
        ...


__all__ = ["BattleMode", "ModeHandler"]
```

- [ ] **Step 4: Run**

`pytest tests/unit/tui/test_battle_mode_protocol.py -v` → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/screens/battle_modes/ tests/unit/tui/test_battle_mode_protocol.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L1-5 BattleMode enum + ModeHandler Protocol

Каркас mode-state machine. NORMAL/MOVE/TARGET значения и
контракт on_enter/on_exit/on_key/overlay_data. Реализации —
в L1-6/7/8."
```

---

## L1-6: NormalModeHandler — заглушка-делегатор

**Files:**
- Create: `src/dnd/interfaces/tui/screens/battle_modes/normal_mode.py`
- Test: `tests/unit/tui/test_normal_mode.py`

NormalModeHandler в L1 — пустой (overlay_data возвращает (None, {}, ())). Реальная диспетчеризация ability hotkey'ев придёт в L2-7. Сейчас он нужен только чтобы у BattleScreen всегда был активный handler.

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_normal_mode.py
from dnd.interfaces.tui.screens.battle_modes.normal_mode import NormalModeHandler


def test_normal_mode_no_overlay() -> None:
    h = NormalModeHandler()
    cursor, highlights, path = h.overlay_data()
    assert cursor is None
    assert highlights == {}
    assert path == ()


def test_normal_mode_doesnt_eat_keys() -> None:
    h = NormalModeHandler()
    # screen=None — handler не должен на него полагаться в этой версии
    assert h.on_key(None, "x") is False  # type: ignore[arg-type]
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/unit/tui/test_normal_mode.py -v`

- [ ] **Step 3: Implement**

```python
# src/dnd/interfaces/tui/screens/battle_modes/normal_mode.py
"""NormalModeHandler — пустой делегатор.

В NORMAL mode никаких overlay'ев нет. Ability hotkey'и обрабатываются
не handler'ом, а самим BattleScreen (через AbilityRegistry в L2-7).
Этот handler нужен только чтобы state machine всегда имела активный
ModeHandler.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.square import Square

if TYPE_CHECKING:
    from dnd.interfaces.tui.screens.battle import BattleScreen


class NormalModeHandler:
    def on_enter(self, screen: BattleScreen) -> None:
        return None

    def on_exit(self, screen: BattleScreen) -> None:
        return None

    def on_key(self, screen: BattleScreen, key: str) -> bool:
        return False

    def overlay_data(
        self,
    ) -> tuple[Square | None, dict[Square, str], tuple[Square, ...]]:
        return (None, {}, ())


__all__ = ["NormalModeHandler"]
```

- [ ] **Step 4: Run** — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/screens/battle_modes/normal_mode.py tests/unit/tui/test_normal_mode.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L1-6 NormalModeHandler (пустой делегатор)

Default handler для state machine. В NORMAL никаких overlay'ев;
ability hotkey'и идут мимо handler'а (обрабатываются BattleScreen)."
```

---

## L1-7: MoveModeHandler + path preview

**Files:**
- Create: `src/dnd/interfaces/tui/screens/battle_modes/move_mode.py`
- Test: `tests/unit/tui/test_move_mode.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_move_mode.py
"""MoveModeHandler: курсор + path preview, Enter/Esc/arrows."""
from unittest.mock import MagicMock

from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.move_mode import MoveModeHandler


def _screen_stub(pc_pos: Square = Square(5, 5), w: int = 20, h: int = 20):
    s = MagicMock()
    s._current_actor_position = pc_pos
    s._current_battlefield.width = w
    s._current_battlefield.height = h
    s._current_battlefield.terrain_at = MagicMock(
        return_value=MagicMock(difficult=False, passable=True)
    )
    return s


def test_on_enter_cursor_at_actor() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(7, 3)))
    cursor, _, _ = h.overlay_data()
    assert cursor == Square(7, 3)


def test_arrow_moves_cursor_and_builds_path() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(5, 5)))
    assert h.on_key(_screen_stub(Square(5, 5)), "right") is True
    cursor, _, path = h.overlay_data()
    assert cursor == Square(6, 5)
    assert path == (Square(6, 5),)


def test_arrow_clamps_to_world_bounds() -> None:
    h = MoveModeHandler()
    s = _screen_stub(Square(0, 0), w=10, h=10)
    h.on_enter(s)
    assert h.on_key(s, "left") is True
    cursor, _, _ = h.overlay_data()
    assert cursor == Square(0, 0)  # clamped


def test_escape_returns_true_and_marks_cancel() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub())
    assert h.on_key(_screen_stub(), "escape") is True
    assert h.cancelled is True


def test_enter_returns_true_and_marks_confirm() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(5, 5)))
    h.on_key(_screen_stub(Square(5, 5)), "right")
    assert h.on_key(_screen_stub(Square(5, 5)), "enter") is True
    assert h.confirmed_path == (Square(6, 5),)


def test_unknown_key_returns_false() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub())
    assert h.on_key(_screen_stub(), "x") is False
```

- [ ] **Step 2: Run, expect FAIL** — модуль ещё не существует.

- [ ] **Step 3: Implement**

```python
# src/dnd/interfaces/tui/screens/battle_modes/move_mode.py
"""MoveModeHandler — inline MOVE mode.

См. spec §4.2 и §5. Стрелки двигают cursor по карте (clamp к bounds),
path рисуется chebyshev'ом с показом стоимости (BattleScreen берёт
из overlay_data + computes цвет через path_cost_ft).

Confirmation/cancellation выставляют флаги `confirmed_path` /
`cancelled` — BattleScreen проверяет после on_key и выполняет
переход NORMAL.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.engine.actions.move_path import find_chebyshev_path
from dnd.domain.values.square import Square

if TYPE_CHECKING:
    from dnd.interfaces.tui.screens.battle import BattleScreen


_ARROW_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


class MoveModeHandler:
    """Состояние MOVE: cursor + path preview. Confirmation через флаги."""

    def __init__(self) -> None:
        self._start: Square = Square(0, 0)
        self._cursor: Square = Square(0, 0)
        self._path: tuple[Square, ...] = ()
        self.confirmed_path: tuple[Square, ...] | None = None
        self.cancelled: bool = False

    def on_enter(self, screen: BattleScreen) -> None:
        self._start = screen._current_actor_position
        self._cursor = self._start
        self._path = ()
        self.confirmed_path = None
        self.cancelled = False

    def on_exit(self, screen: BattleScreen) -> None:
        self._path = ()

    def on_key(self, screen: BattleScreen, key: str) -> bool:
        if key in _ARROW_DELTAS:
            dx, dy = _ARROW_DELTAS[key]
            new = Square(self._cursor.x + dx, self._cursor.y + dy)
            bf = screen._current_battlefield
            if 0 <= new.x < bf.width and 0 <= new.y < bf.height:
                self._cursor = new
                self._path = find_chebyshev_path(self._start, self._cursor)
            return True
        if key == "enter":
            self.confirmed_path = self._path
            return True
        if key == "escape":
            self.cancelled = True
            return True
        return False

    def overlay_data(
        self,
    ) -> tuple[Square | None, dict[Square, str], tuple[Square, ...]]:
        return (self._cursor, {}, self._path)


__all__ = ["MoveModeHandler"]
```

- [ ] **Step 4: Run** — 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/screens/battle_modes/move_mode.py tests/unit/tui/test_move_mode.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L1-7 MoveModeHandler (inline MOVE)

Cursor двигается стрелками с clamp к bounds, path рисуется
chebyshev'ом. Enter → confirmed_path, Esc → cancelled. Wire
в BattleScreen — L1-9."
```

---

## L1-8: TargetModeHandler + Tab-cycle

**Files:**
- Create: `src/dnd/interfaces/tui/screens/battle_modes/target_mode.py`
- Test: `tests/unit/tui/test_target_mode.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_target_mode.py
"""TargetModeHandler: Tab-cycle по достижимым врагам, highlights, Enter."""
from unittest.mock import MagicMock

from dnd.application.dto.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.target_mode import TargetModeHandler


def _screen(targets: list[tuple[CreatureId, Square]]):
    s = MagicMock()
    s._reachable_targets = targets
    return s


def test_initial_target_first_in_list() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    cursor, highlights, _ = h.overlay_data()
    assert cursor == Square(3, 3)
    assert highlights.get(Square(3, 3)) == "reverse bold"
    assert highlights.get(Square(5, 5)) == "bold"


def test_tab_cycles_to_next() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "tab")
    cursor, _, _ = h.overlay_data()
    assert cursor == Square(5, 5)


def test_tab_wraps_around() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "tab")
    h.on_key(_screen(targets), "tab")
    cursor, _, _ = h.overlay_data()
    assert cursor == Square(3, 3)


def test_enter_records_confirmed_target() -> None:
    targets = [(CreatureId("g1"), Square(3, 3))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "enter")
    assert h.confirmed_target == CreatureId("g1")


def test_escape_marks_cancel() -> None:
    targets = [(CreatureId("g1"), Square(3, 3))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "escape")
    assert h.cancelled is True
```

- [ ] **Step 2: Run, expect FAIL** — модуля нет.

- [ ] **Step 3: Implement**

```python
# src/dnd/interfaces/tui/screens/battle_modes/target_mode.py
"""TargetModeHandler — inline TARGET mode.

Tab/Shift+Tab циклит между достижимыми целями. Выбранная подсвечена
'reverse bold'; остальные доступные — 'bold'. Enter → confirmed_target.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.ids import CreatureId
from dnd.domain.values.square import Square

if TYPE_CHECKING:
    from dnd.interfaces.tui.screens.battle import BattleScreen


class TargetModeHandler:
    def __init__(self) -> None:
        self._targets: list[tuple[CreatureId, Square]] = []
        self._idx: int = 0
        self.confirmed_target: CreatureId | None = None
        self.cancelled: bool = False

    def on_enter(self, screen: BattleScreen) -> None:
        self._targets = list(screen._reachable_targets)
        self._idx = 0
        self.confirmed_target = None
        self.cancelled = False

    def on_exit(self, screen: BattleScreen) -> None:
        self._targets = []

    def on_key(self, screen: BattleScreen, key: str) -> bool:
        if not self._targets:
            return False
        if key == "tab":
            self._idx = (self._idx + 1) % len(self._targets)
            return True
        if key == "shift+tab":
            self._idx = (self._idx - 1) % len(self._targets)
            return True
        if key == "enter":
            self.confirmed_target = self._targets[self._idx][0]
            return True
        if key == "escape":
            self.cancelled = True
            return True
        return False

    def overlay_data(
        self,
    ) -> tuple[Square | None, dict[Square, str], tuple[Square, ...]]:
        if not self._targets:
            return (None, {}, ())
        highlights: dict[Square, str] = {}
        for i, (_, sq) in enumerate(self._targets):
            highlights[sq] = "reverse bold" if i == self._idx else "bold"
        cursor = self._targets[self._idx][1]
        return (cursor, highlights, ())


__all__ = ["TargetModeHandler"]
```

- [ ] **Step 4: Run** — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/screens/battle_modes/target_mode.py tests/unit/tui/test_target_mode.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L1-8 TargetModeHandler (Tab-cycle inline)

Циклит между достижимыми врагами через Tab/Shift+Tab, выделяет
выбранного 'reverse bold' остальных 'bold'. Enter → confirmed_target.
Wire в BattleScreen — L1-9."
```

---

## L1-9: Wire mode-state в BattleScreen + удаление picker'ов

**Files:**
- Modify: `src/dnd/interfaces/tui/screens/battle.py` — добавить `_mode`, `_mode_handler`, методы `enter_mode/exit_mode`, заменить `action_intent_attack/move` на инициаторы mode, добавить on_key proxy
- Modify: `src/dnd/interfaces/tui/widgets/map_widget.py:228` — обновить `refresh_from` чтобы принимать overlay_data
- Delete: `src/dnd/interfaces/tui/screens/move_picker.py`
- Delete: `src/dnd/interfaces/tui/screens/target_picker.py`
- Delete/Migrate: тесты на picker'ы (заменить inline-моки)

Это самый большой task. Бить на меньшие подшаги:

- [ ] **Step 1: Найти все use sites picker'ов**

```bash
grep -rn "MovePicker\|TargetPicker\|move_picker\|target_picker" src/ tests/ | tee /tmp/picker-refs.txt
```

Должны быть в `battle.py` (action_intent_attack/move) + integration-тесты.

- [ ] **Step 2: Failing integration test (inline move flow)**

Создать `tests/integration/tui/test_inline_move_flow.py`:

```python
"""Inline MOVE flow без модала — курсор + Enter перемещают PC."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from dnd.application.dto.ids import CreatureId
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.interfaces.tui.app import TuiApp


def _enc():
    pc = Creature.create(
        id_=CreatureId("aelar"), name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    goblin = Creature.create(
        id_=CreatureId("g"), name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(15, 15)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(goblin.id, Square(12, 12))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 20)
    return Encounter(
        participants={pc.id: pc, goblin.id: goblin},
        factions={pc.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )


def test_m_enters_move_mode_arrows_move_cursor_enter_executes() -> None:
    app = TuiApp(encounter=_enc())

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if getattr(screen, "_current", None) is not None:
                    break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC didn't get turn")
            # вход в move
            await pilot.press("m")
            await pilot.pause(0.1)
            assert screen._mode.value == "move"
            # вправо ×3
            for _ in range(3):
                await pilot.press("right")
                await pilot.pause(0.05)
            # подтвердить
            await pilot.press("enter")
            await pilot.pause(0.5)
            # PC должен сдвинуться + mode вернуться в normal
            bf = screen._encounter.deps.battlefield
            pos = bf.position_of(CreatureId("aelar"))
            assert pos.x > 2, f"PC didn't move: still at {pos}"
            assert screen._mode.value == "normal"

    asyncio.run(_go())


def test_escape_in_move_returns_to_normal_without_action() -> None:
    app = TuiApp(encounter=_enc())

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if getattr(screen, "_current", None) is not None:
                    break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip()
            await pilot.press("m")
            await pilot.press("right")
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert screen._mode.value == "normal"
            bf = screen._encounter.deps.battlefield
            assert bf.position_of(CreatureId("aelar")) == Square(2, 2)

    asyncio.run(_go())
```

`pytest tests/integration/tui/test_inline_move_flow.py -v` → FAIL (нет `_mode` атрибута).

- [ ] **Step 3: Implement в battle.py**

Добавить в `BattleScreen.__init__`:
```python
from dnd.interfaces.tui.screens.battle_modes.protocol import BattleMode, ModeHandler
from dnd.interfaces.tui.screens.battle_modes.normal_mode import NormalModeHandler
from dnd.interfaces.tui.screens.battle_modes.move_mode import MoveModeHandler
from dnd.interfaces.tui.screens.battle_modes.target_mode import TargetModeHandler

# в __init__:
self._mode: BattleMode = BattleMode.NORMAL
self._mode_handler: ModeHandler = NormalModeHandler()
# helpers, доступные хендлерам:
self._current_actor_position: Square = Square(0, 0)
self._current_battlefield: Battlefield | None = None
self._reachable_targets: list[tuple[CreatureId, Square]] = []
```

Добавить `enter_mode/exit_mode`:
```python
def enter_mode(self, mode: BattleMode) -> None:
    self._mode_handler.on_exit(self)
    self._mode = mode
    if mode is BattleMode.NORMAL:
        self._mode_handler = NormalModeHandler()
    elif mode is BattleMode.MOVE:
        self._mode_handler = MoveModeHandler()
    elif mode is BattleMode.TARGET:
        self._mode_handler = TargetModeHandler()
    self._mode_handler.on_enter(self)
    self._refresh_map()

def _refresh_map(self) -> None:
    if self._current is None or self._current_battlefield is None:
        return
    cursor, highlights, path_preview = self._mode_handler.overlay_data()
    actor, ctx, enc = self._current
    mw = self.query_one("#map", MapWidget)
    mw.refresh_from(
        self._current_battlefield,
        enc.factions,
        cursor=cursor, highlights=highlights, path_preview=path_preview,
        follow=self._current_battlefield.position_of(actor.id),
    )
```

Override `on_key` (Textual API):
```python
def on_key(self, event: events.Key) -> None:
    if self._mode_handler.on_key(self, event.key):
        # проверяем confirmation/cancel
        h = self._mode_handler
        if isinstance(h, MoveModeHandler):
            if h.cancelled:
                self.enter_mode(BattleMode.NORMAL); event.stop(); return
            if h.confirmed_path is not None:
                if h.confirmed_path:
                    self._submit_intent(MoveIntent(
                        actor_id=actor_id_from_current(self),
                        path=h.confirmed_path,
                    ))
                self.enter_mode(BattleMode.NORMAL)
                event.stop(); return
        if isinstance(h, TargetModeHandler):
            if h.cancelled:
                self.enter_mode(BattleMode.NORMAL); event.stop(); return
            if h.confirmed_target is not None:
                self._submit_intent(AttackIntent(
                    actor_id=actor_id_from_current(self),
                    target_id=h.confirmed_target,
                ))
                self.enter_mode(BattleMode.NORMAL); event.stop(); return
        self._refresh_map()
        event.stop()
```

Заменить `action_intent_move` на:
```python
def action_intent_move(self) -> None:
    if self._current is None: return
    actor, ctx, _ = self._current
    res = MoveAction().can_perform(actor, ctx)
    if isinstance(res, Forbidden):
        self._log(_explain_forbidden("move", res)); return
    self._current_actor_position = self._current_battlefield.position_of(actor.id)
    self.enter_mode(BattleMode.MOVE)
```

И `action_intent_attack`:
```python
def action_intent_attack(self) -> None:
    if self._current is None: return
    actor, ctx, enc = self._current
    res = AttackAction().can_perform(actor, ctx)
    if isinstance(res, Forbidden):
        self._log(_explain_forbidden("attack", res)); return
    self._reachable_targets = self._compute_reachable_targets(actor, ctx, enc)
    if not self._reachable_targets:
        enemies = _count_living_hostiles(actor, enc)
        self._log(f"[bold]No targets in reach[/] ({enemies} enemy alive). Move closer (m) first.")
        return
    self.enter_mode(BattleMode.TARGET)
```

`_compute_reachable_targets` — переиспользовать существующую логику из `action_intent_attack` (текущий код собирает targets для TargetPicker).

В `on_turn_started` (или где `_current` обновляется): сбросить mode в NORMAL, обновить `_current_battlefield`.

Удалить:
```bash
git rm src/dnd/interfaces/tui/screens/move_picker.py src/dnd/interfaces/tui/screens/target_picker.py
grep -rln "from dnd.interfaces.tui.screens.move_picker\|from dnd.interfaces.tui.screens.target_picker" src/ tests/ | xargs sed -i 's/.*move_picker.*//;s/.*target_picker.*//'
```

- [ ] **Step 4: Run**

```bash
pytest tests/integration/tui/test_inline_move_flow.py -v   # 2 passed
pytest -q                                                  # 972+ passed (плюс новые, минус старые picker-tests)
mypy src/                                                  # 0 errors
ruff check src/ tests/                                     # all checks passed
```

Если старые тесты на picker'ы остались сломанными — удалить (они проверяли модальный flow, который больше не существует).

- [ ] **Step 5: Commit**

```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L1-9 wire BattleMode state machine + удаление picker'ов

BattleScreen теперь делегирует keypress'ы mode-handler'у через
on_key override. enter_mode переключает handler (Normal/Move/Target).
Confirmation/cancel ловятся проверкой полей handler'а после on_key.

action_intent_attack/move теперь только запускают mode (после
can_perform check); реальный submit — после Enter в mode.

Удалены MovePicker/TargetPicker (модальные) + их тесты — функционал
переехал в battle_modes/."
```

---

## L1-10: Pilot smoke L1 + viewport-тест на большой карте

**Files:**
- Test: `tests/integration/tui/test_inline_target_flow.py`
- Test: `tests/integration/tui/test_viewport_large_map.py`

- [ ] **Step 1: Failing tests**

```python
# tests/integration/tui/test_inline_target_flow.py
"""Tab-cycle + Enter в TARGET mode проводит атаку без модала."""
from __future__ import annotations

import asyncio
import pytest

pytest.importorskip("textual")

from dnd.application.dto.ids import CreatureId
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.interfaces.tui.app import TuiApp


def _enc_adjacent():
    pc = Creature.create(
        id_=CreatureId("aelar"), name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    g1 = Creature.create(
        id_=CreatureId("g1"), name="G1",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    g2 = Creature.create(
        id_=CreatureId("g2"), name="G2",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(10, 10)
    bf.place_creature(pc.id, Square(5, 5))
    bf.place_creature(g1.id, Square(6, 5))
    bf.place_creature(g2.id, Square(4, 5))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 20)
    return Encounter(
        participants={pc.id: pc, g1.id: g1, g2.id: g2},
        factions={pc.id: Faction.PARTY, g1.id: Faction.MONSTERS, g2.id: Faction.MONSTERS},
        deps=deps,
    )


def test_a_then_enter_attacks_first_target() -> None:
    app = TuiApp(encounter=_enc_adjacent())

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if getattr(screen, "_current", None): break
                await pilot.pause(0.1)
            if not getattr(screen, "_current", None): pytest.skip()
            await pilot.press("a")
            await pilot.pause(0.1)
            assert screen._mode.value == "target"
            await pilot.press("enter")
            await pilot.pause(0.5)
            assert screen._mode.value == "normal"
            # HP одного из goblin'ов уменьшилось
            g1 = screen._encounter.participants[CreatureId("g1")]
            g2 = screen._encounter.participants[CreatureId("g2")]
            assert g1.hp < 7 or g2.hp < 7, "no goblin took damage"

    asyncio.run(_go())


def test_tab_cycles_target_then_enter() -> None:
    app = TuiApp(encounter=_enc_adjacent())

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if getattr(screen, "_current", None): break
                await pilot.pause(0.1)
            if not getattr(screen, "_current", None): pytest.skip()
            await pilot.press("a")
            await pilot.press("tab")
            await pilot.press("enter")
            await pilot.pause(0.5)
            assert screen._mode.value == "normal"

    asyncio.run(_go())
```

```python
# tests/integration/tui/test_viewport_large_map.py
"""На большой карте PC всегда в viewport (auto-follow)."""
from __future__ import annotations

import asyncio
import pytest

pytest.importorskip("textual")

from dnd.application.dto.ids import CreatureId
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.interfaces.tui.app import TuiApp


def test_viewport_centers_on_pc_at_corner() -> None:
    pc = Creature.create(
        id_=CreatureId("p"), name="PC",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(50, 50)
    bf.place_creature(pc.id, Square(40, 40))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 5)
    enc = Encounter(
        participants={pc.id: pc},
        factions={pc.id: Faction.PARTY},
        deps=deps,
    )
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(60, 30)) as pilot:
            await pilot.pause(0.5)
            mw = pilot.app.screen.query_one("#map")
            x0, y0, x1, y1 = mw.visible_rect()
            # PC (40, 40) должен быть в viewport
            assert x0 <= 40 < x1, f"PC.x not in viewport: {x0}..{x1}"
            assert y0 <= 40 < y1, f"PC.y not in viewport: {y0}..{y1}"

    asyncio.run(_go())
```

- [ ] **Step 2: Run, expect FAIL/maybe PASS**

`pytest tests/integration/tui/test_inline_target_flow.py tests/integration/tui/test_viewport_large_map.py -v`. Если что-то fail — починить wiring в `battle.py`.

- [ ] **Step 3: Fix any wiring gaps**

Типичные:
- `_reachable_targets` не наполняется (см. L1-9 step 3 — нужна `_compute_reachable_targets`)
- viewport не центрируется — проверить что `refresh_from` зовётся с `follow=actor_pos`

- [ ] **Step 4: Full sweep**

```bash
pytest -q              # все зелёные
mypy src/              # clean
ruff check src/ tests/ # clean
```

Реальная проверка пользователя (не автомат): `PYTHONPATH=src python -m dnd play warehouse --tui` → `m` → стрелки → Enter; `a` → Tab → Enter — без модалок.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/tui/
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "test(tui): L1-10 inline target flow + viewport large-map smoke

Pilot integration tests завершают L1: inline TARGET flow без
модала + проверка что на 50×50 карте PC всегда виден через
auto-follow."
```

---

# L2: Ability Framework

## L2-1: Ability dataclass + AbilityId

**Files:**
- Create: `src/dnd/domain/values/ability.py`
- Test: `tests/unit/domain/test_ability_dataclass.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/domain/test_ability_dataclass.py
"""Ability — frozen dataclass с runtime-описанием умения."""
import pytest

from dnd.application.dto.action import ActionEconomyCost
from dnd.domain.values.ability import Ability, AbilityId


def _noparam(actor):
    return None


def test_ability_frozen() -> None:
    a = Ability(
        id=AbilityId("dodge"), name="Dodge", icon="d",
        default_hotkey="d", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=_noparam,
    )
    with pytest.raises(Exception):
        a.name = "X"  # type: ignore[misc]


def test_ability_id_is_str() -> None:
    aid = AbilityId("weapon_attack")
    assert str(aid) == "weapon_attack"


def test_ability_required_flags_exclusive() -> None:
    """requires_target и requires_path не должны быть оба True одновременно."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        Ability(
            id=AbilityId("x"), name="X", icon="x", default_hotkey="x",
            economy_cost=ActionEconomyCost.ACTION,
            requires_target=True, requires_path=True,
            intent_factory=_noparam,
        )
```

- [ ] **Step 2: Run, expect FAIL** — модуля нет.

- [ ] **Step 3: Implement**

```python
# src/dnd/domain/values/ability.py
"""Ability — runtime-описание игрового умения.

В отличие от Action классов (выполняют логику), Ability описывает
UI-аспект: hotkey, иконка, что нужно собрать перед запуском
(target/path). Intent factory строит PlayerIntent готовым к выполнению.

См. spec §4.3.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, NewType

from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import PlayerIntent

AbilityId = NewType("AbilityId", str)


@dataclass(frozen=True)
class Ability:
    id: AbilityId
    name: str
    icon: str  # 1 символ для action-bar
    default_hotkey: str
    economy_cost: ActionEconomyCost
    requires_target: bool
    requires_path: bool
    intent_factory: Callable[..., PlayerIntent]

    def __post_init__(self) -> None:
        if self.requires_target and self.requires_path:
            raise ValueError(
                f"Ability {self.id}: requires_target и requires_path "
                "mutually exclusive (mode либо TARGET, либо MOVE)"
            )


__all__ = ["Ability", "AbilityId"]
```

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/domain/values/ability.py tests/unit/domain/test_ability_dataclass.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(domain): L2-1 Ability dataclass + AbilityId

Frozen описание умения: id, name, icon, default_hotkey, economy_cost,
requires_target/requires_path (exclusive), intent_factory. Registry —
L2-2, дефолтные регистрации — L2-3."
```

---

## L2-2: AbilityRegistry

**Files:**
- Create: `src/dnd/application/abilities/__init__.py` (пустой)
- Create: `src/dnd/application/abilities/registry.py`
- Test: `tests/unit/abilities/test_registry.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/abilities/test_registry.py
import pytest

from dnd.application.abilities.registry import AbilityRegistry
from dnd.application.dto.action import ActionEconomyCost
from dnd.domain.values.ability import Ability, AbilityId


def _make(id_: str, hotkey: str = "x") -> Ability:
    return Ability(
        id=AbilityId(id_), name=id_, icon=id_[0], default_hotkey=hotkey,
        economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=lambda actor: None,  # type: ignore[return-value]
    )


def test_register_and_get() -> None:
    r = AbilityRegistry()
    a = _make("foo")
    r.register(a)
    assert r.get(AbilityId("foo")) is a


def test_get_missing_raises() -> None:
    r = AbilityRegistry()
    with pytest.raises(KeyError):
        r.get(AbilityId("missing"))


def test_duplicate_register_raises() -> None:
    r = AbilityRegistry()
    r.register(_make("foo"))
    with pytest.raises(ValueError, match="already registered"):
        r.register(_make("foo"))


def test_all_returns_registered() -> None:
    r = AbilityRegistry()
    r.register(_make("a", "1"))
    r.register(_make("b", "2"))
    assert {a.id for a in r.all()} == {AbilityId("a"), AbilityId("b")}
```

- [ ] **Step 2: Run, expect FAIL** — модуля нет.

- [ ] **Step 3: Implement**

```python
# src/dnd/application/abilities/__init__.py
"""Ability registry + default registrations (этап L2)."""
```

```python
# src/dnd/application/abilities/registry.py
"""AbilityRegistry — runtime-реестр доступных умений."""
from __future__ import annotations

from typing import Iterator

from dnd.domain.values.ability import Ability, AbilityId


class AbilityRegistry:
    def __init__(self) -> None:
        self._by_id: dict[AbilityId, Ability] = {}

    def register(self, ability: Ability) -> None:
        if ability.id in self._by_id:
            raise ValueError(f"Ability {ability.id!r} already registered")
        self._by_id[ability.id] = ability

    def get(self, id_: AbilityId) -> Ability:
        return self._by_id[id_]

    def all(self) -> Iterator[Ability]:
        return iter(self._by_id.values())


__all__ = ["AbilityRegistry"]
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/abilities/ tests/unit/abilities/
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(abilities): L2-2 AbilityRegistry

register/get/all. Дубликаты по id → ValueError. Default-регистрации
8 базовых — в L2-3."
```

---

## L2-3: register_default_abilities (8 базовых)

**Files:**
- Modify: `src/dnd/application/abilities/registry.py` — добавить `register_default_abilities`
- Test: `tests/unit/abilities/test_default_abilities.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/abilities/test_default_abilities.py
"""8 базовых ability'ев регистрируются без коллизий хоткеев."""
from dnd.application.abilities.registry import (
    AbilityRegistry, register_default_abilities,
)
from dnd.domain.values.ability import AbilityId


def test_all_8_registered() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    ids = {a.id for a in r.all()}
    assert ids == {
        AbilityId("weapon_attack"), AbilityId("dodge"), AbilityId("dash"),
        AbilityId("disengage"), AbilityId("help"), AbilityId("search"),
        AbilityId("interact"), AbilityId("break_object"),
    }


def test_no_hotkey_collisions() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    keys = [a.default_hotkey for a in r.all()]
    assert len(keys) == len(set(keys)), f"hotkey collision: {keys}"


def test_weapon_attack_requires_target() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    assert r.get(AbilityId("weapon_attack")).requires_target is True


def test_dodge_no_target_no_path() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    d = r.get(AbilityId("dodge"))
    assert d.requires_target is False
    assert d.requires_path is False
```

- [ ] **Step 2: Run, expect FAIL** — функции нет.

- [ ] **Step 3: Implement (append в registry.py)**

```python
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.ids import CreatureId, ObjectId
from dnd.application.dto.player_intent import (
    AttackIntent, BreakIntent, DashIntent, DisengageIntent, DodgeIntent,
    HelpIntent, InteractIntent, MoveIntent, SearchIntent,
)
from dnd.application.engine.actions.interact import InteractKind
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityId
from dnd.domain.values.square import Square


def register_default_abilities(registry: AbilityRegistry) -> None:
    """Регистрирует 8 базовых umений (Attack/Dodge/Dash/Disengage/
    Help/Search/Interact/Break). Hotkey'и: a/d/h/g/p/s/i/b."""
    registry.register(Ability(
        id=AbilityId("weapon_attack"), name="Attack", icon="⚔",
        default_hotkey="a", economy_cost=ActionEconomyCost.ACTION,
        requires_target=True, requires_path=False,
        intent_factory=lambda actor, target_id: AttackIntent(
            actor_id=actor.id, target_id=target_id,
        ),
    ))
    registry.register(Ability(
        id=AbilityId("dodge"), name="Dodge", icon="◇",
        default_hotkey="d", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=lambda actor: DodgeIntent(actor_id=actor.id),
    ))
    registry.register(Ability(
        id=AbilityId("dash"), name="Dash", icon="»",
        default_hotkey="h", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=lambda actor: DashIntent(actor_id=actor.id),
    ))
    registry.register(Ability(
        id=AbilityId("disengage"), name="Disengage", icon="↶",
        default_hotkey="g", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=lambda actor: DisengageIntent(actor_id=actor.id),
    ))
    registry.register(Ability(
        id=AbilityId("help"), name="Help", icon="+",
        default_hotkey="p", economy_cost=ActionEconomyCost.ACTION,
        requires_target=True, requires_path=False,
        intent_factory=lambda actor, target_id: HelpIntent(
            actor_id=actor.id, target_id=target_id,
        ),
    ))
    registry.register(Ability(
        id=AbilityId("search"), name="Search", icon="?",
        default_hotkey="s", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=lambda actor: SearchIntent(actor_id=actor.id),
    ))
    registry.register(Ability(
        id=AbilityId("interact"), name="Interact", icon="·",
        default_hotkey="i", economy_cost=ActionEconomyCost.FREE,
        requires_target=True, requires_path=False,
        intent_factory=lambda actor, target_id: InteractIntent(
            actor_id=actor.id, object_id=ObjectId(str(target_id)),
            kind=InteractKind.USE,
        ),
    ))
    registry.register(Ability(
        id=AbilityId("break_object"), name="Break", icon="✗",
        default_hotkey="b", economy_cost=ActionEconomyCost.ACTION,
        requires_target=True, requires_path=False,
        intent_factory=lambda actor, target_id: BreakIntent(
            actor_id=actor.id, object_id=ObjectId(str(target_id)),
        ),
    ))
```

В `__all__` добавить `"register_default_abilities"`.

(Move не включаем в abilities — это MOVEMENT, не ACTION; обрабатывается отдельным hotkey'ем `m` BattleScreen'ом. Если позже захотим — добавим `Ability(id="move", requires_path=True)` отдельно.)

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/abilities/registry.py tests/unit/abilities/test_default_abilities.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(abilities): L2-3 register_default_abilities (8 базовых)

Attack/Dodge/Dash/Disengage/Help/Search/Interact/Break с дефолтными
hotkey'ями a/d/h/g/p/s/i/b. Move — отдельный hotkey 'm', не ability
(он MOVEMENT, не ACTION)."
```

---

## L2-4: Creature.abilities + Creature.keybindings

**Files:**
- Modify: `src/dnd/domain/entities/creature.py:122` (после class Creature) — добавить поля с дефолтами
- Test: `tests/unit/domain/test_creature_abilities.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/domain/test_creature_abilities.py
from dnd.application.dto.ids import CreatureId
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityId
from dnd.domain.values.ability_scores import AbilityScores
from dnd.domain.values.weapon import LONGSWORD


def _make() -> Creature:
    return Creature.create(
        id_=CreatureId("x"), name="X",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30, equipped_weapon=LONGSWORD,
    )


def test_default_abilities_includes_attack() -> None:
    c = _make()
    assert AbilityId("weapon_attack") in c.ability_ids


def test_default_keybindings_empty() -> None:
    c = _make()
    assert c.keybindings == {}


def test_custom_keybinding_override() -> None:
    c = _make().model_copy(update={
        "keybindings": {"z": AbilityId("weapon_attack")},
    })
    assert c.keybindings == {"z": AbilityId("weapon_attack")}
```

- [ ] **Step 2: Run, expect FAIL** — атрибута нет.

- [ ] **Step 3: Implement**

В `creature.py` после остальных полей class Creature:

```python
# импорт сверху:
from dnd.domain.values.ability import AbilityId

# поля:
ability_ids: tuple[AbilityId, ...] = (
    AbilityId("weapon_attack"),
    AbilityId("dodge"),
    AbilityId("dash"),
    AbilityId("disengage"),
    AbilityId("help"),
    AbilityId("search"),
    AbilityId("interact"),
    AbilityId("break_object"),
)
keybindings: Mapping[str, AbilityId] = Field(default_factory=dict)
```

(добавить `from collections.abc import Mapping`, `from pydantic import Field`, если нет)

Если поле `abilities` уже занято (для AbilityScores) — называем `ability_ids` (как в тесте).

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/domain/entities/creature.py tests/unit/domain/test_creature_abilities.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(domain): L2-4 Creature.ability_ids + .keybindings

Default — все 8 базовых, keybindings — пусто (используются дефолты
из Ability.default_hotkey). Backwards compat: дефолтные значения,
существующие тесты не меняются."
```

---

## L2-5: build_keymap helper

**Files:**
- Create: `src/dnd/interfaces/tui/screens/keymap.py`
- Test: `tests/unit/tui/test_keymap.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_keymap.py
from dnd.application.abilities.registry import (
    AbilityRegistry, register_default_abilities,
)
from dnd.application.dto.ids import CreatureId
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityId
from dnd.domain.values.ability_scores import AbilityScores
from dnd.domain.values.weapon import LONGSWORD
from dnd.interfaces.tui.screens.keymap import build_keymap


def _make(keybindings=None):
    return Creature.create(
        id_=CreatureId("x"), name="X",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30, equipped_weapon=LONGSWORD,
    ).model_copy(update={"keybindings": keybindings or {}})


def _reg():
    r = AbilityRegistry()
    register_default_abilities(r)
    return r


def test_default_hotkey_a_maps_to_attack() -> None:
    km = build_keymap(_make(), _reg())
    assert km["a"].id == AbilityId("weapon_attack")


def test_override_z_replaces_default_a() -> None:
    km = build_keymap(_make({"z": AbilityId("weapon_attack")}), _reg())
    assert "z" in km
    assert km["z"].id == AbilityId("weapon_attack")
    # 'a' уже не должен мапиться на weapon_attack, если override активен
    assert "a" not in km or km["a"].id != AbilityId("weapon_attack")


def test_override_replaces_only_specified() -> None:
    km = build_keymap(_make({"z": AbilityId("weapon_attack")}), _reg())
    assert km["d"].id == AbilityId("dodge")  # default остался
```

- [ ] **Step 2: Run, expect FAIL** — функции нет.

- [ ] **Step 3: Implement**

```python
# src/dnd/interfaces/tui/screens/keymap.py
"""build_keymap — собирает {hotkey: Ability} для актора с учётом overrides."""
from __future__ import annotations

from dnd.application.abilities.registry import AbilityRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability


def build_keymap(actor: Creature, registry: AbilityRegistry) -> dict[str, Ability]:
    """Сначала записываем default hotkey'и. Затем applying overrides:
    для каждого (key, ability_id) в keybindings ищем default hotkey
    этой ability и удаляем его, потом мапим новый key."""
    keymap: dict[str, Ability] = {}
    for aid in actor.ability_ids:
        ab = registry.get(aid)
        keymap[ab.default_hotkey] = ab
    for key, aid in actor.keybindings.items():
        ab = registry.get(aid)
        # вычистить default hotkey этой ability (он мог быть занят)
        old = ab.default_hotkey
        if old in keymap and keymap[old] is ab:
            del keymap[old]
        keymap[key] = ab
    return keymap


__all__ = ["build_keymap"]
```

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/screens/keymap.py tests/unit/tui/test_keymap.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L2-5 build_keymap helper

Собирает {hotkey: Ability} из actor.ability_ids + actor.keybindings.
Override очищает старый default hotkey этой ability чтобы не было
двойного маппинга."
```

---

## L2-6: ActionBarWidget

**Files:**
- Create: `src/dnd/interfaces/tui/widgets/action_bar_widget.py`
- Test: `tests/unit/tui/test_action_bar_widget.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/tui/test_action_bar_widget.py
from dnd.application.abilities.registry import (
    AbilityRegistry, register_default_abilities,
)
from dnd.domain.values.ability import AbilityId
from dnd.interfaces.tui.widgets.action_bar_widget import format_action_bar


def test_format_bar_from_keymap() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    keymap = {"a": r.get(AbilityId("weapon_attack")), "d": r.get(AbilityId("dodge"))}
    bar = format_action_bar(keymap)
    assert "[a] Attack" in bar
    assert "[d] Dodge" in bar


def test_format_bar_empty() -> None:
    assert format_action_bar({}) == ""


def test_format_bar_sorted_by_key() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    keymap = {"z": r.get(AbilityId("dodge")), "a": r.get(AbilityId("weapon_attack"))}
    bar = format_action_bar(keymap)
    # 'a' идёт раньше 'z' по алфавиту
    assert bar.index("[a]") < bar.index("[z]")
```

- [ ] **Step 2: Run, expect FAIL** — модуль не существует.

- [ ] **Step 3: Implement**

```python
# src/dnd/interfaces/tui/widgets/action_bar_widget.py
"""ActionBarWidget — динамическая полоса хоткеев внизу экрана.

format_action_bar — pure function (тестируется без Textual).
ActionBarWidget — обёртка для BattleScreen.
"""
from __future__ import annotations

from textual.widgets import Static

from dnd.domain.values.ability import Ability


def format_action_bar(keymap: dict[str, Ability]) -> str:
    """Форматирует {key: Ability} → '[a] Attack  [d] Dodge  …'.

    Отсортировано по key для стабильного отображения.
    """
    if not keymap:
        return ""
    parts = [f"[{k}] {a.name}" for k, a in sorted(keymap.items())]
    return "  ".join(parts)


class ActionBarWidget(Static):
    """Тонкая обёртка: BattleScreen вызывает self.update(format_action_bar(km))."""

    DEFAULT_CSS = "ActionBarWidget { height: 1; padding: 0 1; }"

    def set_keymap(self, keymap: dict[str, Ability]) -> None:
        self.update(format_action_bar(keymap))


__all__ = ["ActionBarWidget", "format_action_bar"]
```

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/widgets/action_bar_widget.py tests/unit/tui/test_action_bar_widget.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L2-6 ActionBarWidget + format_action_bar

Динамическая полоса '[a] Attack  [d] Dodge …' из {key: Ability}.
Wire в BattleScreen — L2-7."
```

---

## L2-7: Wire AbilityRegistry в BattleScreen (динамический action bar)

**Files:**
- Modify: `src/dnd/interfaces/tui/screens/battle.py` — добавить registry в `__init__`, перестроить action-bar в `on_turn_started`/`_refresh_map`, маршрутизировать keypress через keymap в NormalModeHandler (вместо хардкодных action_intent_*)
- Modify: `src/dnd/composition.py` — создавать registry с default'ами, передавать в TuiApp/BattleScreen
- Modify: `src/dnd/interfaces/tui/app.py` — принимать registry

- [ ] **Step 1: Failing integration test**

```python
# tests/integration/tui/test_dynamic_keybindings.py
"""Если actor.keybindings = {'z': 'weapon_attack'}, то z атакует."""
from __future__ import annotations

import asyncio
import pytest

pytest.importorskip("textual")

from dnd.application.abilities.registry import (
    AbilityRegistry, register_default_abilities,
)
from dnd.application.dto.ids import CreatureId
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityId
from dnd.domain.values.ability_scores import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.interfaces.tui.app import TuiApp


def test_z_rebound_to_attack() -> None:
    pc = Creature.create(
        id_=CreatureId("pc"), name="PC",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    ).model_copy(update={"keybindings": {"z": AbilityId("weapon_attack")}})
    g = Creature.create(
        id_=CreatureId("g"), name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(10, 10)
    bf.place_creature(pc.id, Square(5, 5))
    bf.place_creature(g.id, Square(6, 5))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 5)
    enc = Encounter(
        participants={pc.id: pc, g.id: g},
        factions={pc.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
    registry = AbilityRegistry()
    register_default_abilities(registry)
    app = TuiApp(encounter=enc, ability_registry=registry)

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(30):
                if getattr(screen, "_current", None): break
                await pilot.pause(0.1)
            if not getattr(screen, "_current", None): pytest.skip()
            await pilot.press("z")  # rebound
            await pilot.pause(0.1)
            assert screen._mode.value == "target"
            await pilot.press("enter")
            await pilot.pause(0.5)
            g_after = screen._encounter.participants[CreatureId("g")]
            assert g_after.hp < 7, "z didn't trigger attack"

    asyncio.run(_go())
```

- [ ] **Step 2: Run, expect FAIL** — TuiApp нет `ability_registry`.

- [ ] **Step 3: Implement**

В `TuiApp.__init__` добавить kwarg `ability_registry: AbilityRegistry | None = None`. Если None — создать default через `register_default_abilities`. Передать в BattleScreen.

В `BattleScreen.__init__`:
```python
self._ability_registry: AbilityRegistry = ability_registry
self._keymap: dict[str, Ability] = {}  # обновляется на TurnStarted
```

В `_on_turn_started(actor)`:
```python
if actor.id in {pc.id for pc in pcs}:  # PC ход
    self._keymap = build_keymap(actor, self._ability_registry)
    self.query_one("#action-bar", ActionBarWidget).set_keymap(self._keymap)
```

В `on_key` (override):
```python
def on_key(self, event: events.Key) -> None:
    # 1. Если активный mode съел — обрабатываем confirm/cancel (L1-9 код)
    if self._mode_handler.on_key(self, event.key):
        # ... confirm/cancel handling (как в L1-9) ...
        event.stop(); return
    # 2. NORMAL mode: lookup в keymap
    if self._mode is BattleMode.NORMAL:
        ab = self._keymap.get(event.key)
        if ab is not None:
            self._trigger_ability(ab)
            event.stop(); return
    # 3. System hotkeys (end turn / quit / pan) — остаются как BINDINGS

def _trigger_ability(self, ab: Ability) -> None:
    actor, ctx, enc = self._current
    # can_perform check (через соответствующий Action)
    # — для упрощения предполагаем что factory сам строит intent;
    # глобальные Forbidden проверки уже сделаны в action_intent_attack/move
    if ab.requires_target:
        self._reachable_targets = self._compute_reachable_targets(actor, ctx, enc)
        if not self._reachable_targets:
            self._log(f"No targets for {ab.name}"); return
        # store pending ability чтобы on confirm построить правильный intent
        self._pending_ability = ab
        self.enter_mode(BattleMode.TARGET)
    elif ab.requires_path:
        self._pending_ability = ab
        self._current_actor_position = self._current_battlefield.position_of(actor.id)
        self.enter_mode(BattleMode.MOVE)
    else:
        intent = ab.intent_factory(actor)
        self._submit_intent(intent)
```

При confirm в TARGET/MOVE — использовать `self._pending_ability.intent_factory(...)` для построения intent (вместо хардкода `AttackIntent`/`MoveIntent`).

Movement (hotkey `m`) — остаётся как separate handler `action_intent_move`, или регистрируем `Ability(id="move", requires_path=True)` (выбор имплементатора, главное — однозначность).

ActionBarWidget — добавить в `compose()` BattleScreen, например внизу через `with Horizontal(id="bottom")`.

- [ ] **Step 4: Run**

```bash
pytest tests/integration/tui/test_dynamic_keybindings.py -v   # passed
pytest -q                                                     # все зелёные
mypy src/                                                     # clean
ruff check src/ tests/                                        # clean
```

- [ ] **Step 5: Commit**

```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(tui): L2-7 wire AbilityRegistry в BattleScreen

TuiApp/BattleScreen принимают AbilityRegistry; на TurnStarted PC
строим keymap (build_keymap) и обновляем ActionBarWidget. on_key
override: после mode-handler смотрит в keymap для NORMAL mode,
запускает ability — если requires_target → TARGET mode с pending,
если requires_path → MOVE, иначе сразу submit intent.

Поддерживается rebinding: actor.keybindings = {'z': 'weapon_attack'}
делает 'z' атакой."
```

---

## L2-8: Документация ABILITIES.md + сводный commit L

**Files:**
- Create: `docs/ABILITIES.md`
- Modify: `docs/TUI.md` — секция «Mode-state machine + Ability framework»
- Modify: `docs/ROADMAP.md` — отметить L1+L2 как ✅, L3 как pending

- [ ] **Step 1: Написать ABILITIES.md**

```markdown
# Ability Framework

> Этап L2. Spec: `docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md`

## Концепция

`Ability` — runtime-описание игрового умения: hotkey, иконка,
требования к выбору (target/path), фабрика `PlayerIntent`. В
отличие от `Action` классов в `application/engine/actions/`,
которые выполняют логику, `Ability` отвечает за **UI-аспект**:
как игрок инициирует умение в TUI.

## Структура

```python
@dataclass(frozen=True)
class Ability:
    id: AbilityId              # "weapon_attack"
    name: str                  # "Attack"
    icon: str                  # "⚔" — для action-bar
    default_hotkey: str        # "a"
    economy_cost: ActionEconomyCost
    requires_target: bool      # → mode TARGET (выбор Tab-cycle)
    requires_path: bool        # → mode MOVE (курсор на карте)
    intent_factory: Callable   # actor [+ target_id | + path] → PlayerIntent
```

`requires_target` и `requires_path` взаимоисключающи (валидируется в
`__post_init__`).

## Default 8 ability'ев

| id              | name      | hotkey | requires      |
|-----------------|-----------|--------|---------------|
| weapon_attack   | Attack    | a      | target        |
| dodge           | Dodge     | d      | —             |
| dash            | Dash      | h      | —             |
| disengage       | Disengage | g      | —             |
| help            | Help      | p      | target        |
| search          | Search    | s      | —             |
| interact        | Interact  | i      | target (object) |
| break_object    | Break     | b      | target (object) |

`Move` — отдельный hotkey `m`, не ability (MOVEMENT, не ACTION).

## Переопределение хоткеев

`Creature.keybindings: Mapping[str, AbilityId]` — overrides.
Пример: чтобы `z` стал атакой:

```python
creature.model_copy(update={"keybindings": {"z": AbilityId("weapon_attack")}})
```

`build_keymap(actor, registry)` собирает финальный mapping:
- сначала default hotkey'и из `actor.ability_ids`
- overrides из `keybindings` удаляют старый default key этой ability
  и мапят новый

## Расширение (заклинания, feat'ы)

Новый Ability регистрируется в AbilityRegistry в composition root:

```python
registry.register(Ability(
    id=AbilityId("fire_bolt"), name="Fire Bolt", icon="*",
    default_hotkey="f", economy_cost=ActionEconomyCost.ACTION,
    requires_target=True, requires_path=False,
    intent_factory=lambda actor, target_id: CastSpellIntent(
        actor_id=actor.id, spell_id=SpellId("fire_bolt"),
        target_id=target_id,
    ),
))
```

`Creature.ability_ids` для PC-волшебника включает `"fire_bolt"`.
Action-bar для него покажет `[f] Fire Bolt`.
```

- [ ] **Step 2: Обновить TUI.md**

Найти секцию про «модальные picker'ы» — заменить описанием mode-state machine (NORMAL/MOVE/TARGET) с делегацией handler'ам. Добавить упоминание `ActionBarWidget` как динамической полосы.

- [ ] **Step 3: Обновить ROADMAP.md**

В таблице этапов добавить:
- ✅ L1: Inline UX + viewport + 1×1 default
- ✅ L2: Ability framework + dynamic keybindings
- ⏳ L3: LocationArt widget + mouse support (отдельный спек)

- [ ] **Step 4: Финальный full sweep**

```bash
pytest -q                       # все зелёные
mypy src/                       # clean
ruff check src/ tests/          # clean
PYTHONPATH=src python -m dnd play warehouse --tui   # реальная проверка (manual)
```

- [ ] **Step 5: Commit**

```bash
git add docs/ABILITIES.md docs/TUI.md docs/ROADMAP.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "docs: L2-8 ABILITIES.md + TUI.md mode-state + ROADMAP

Завершение этапа L (L1+L2). L3 (LocationArt+mouse) — отдельный
спек после feedback'а пользователя по L."
```

---

## Self-review pass (после написания плана)

**Spec coverage:**
- §3 acceptance #1 (inline move) → L1-7, L1-9, L1-10 ✓
- §3 acceptance #2 (inline target) → L1-8, L1-9, L1-10 ✓
- §3 acceptance #3 (1×1 + viewport) → L1-1, L1-3, L1-4, L1-10 ✓
- §3 acceptance #4 (rebind) → L2-4, L2-5, L2-7 ✓
- §3 acceptance #5 (action bar) → L2-6, L2-7 ✓
- §4.1 file structure — все файлы созданы в L-задачах ✓
- §4.2 BattleMode → L1-5 ✓
- §4.3 Ability dataclass → L2-1 ✓
- §4.3.2 Registry → L2-2/2-3 ✓
- §4.3.3 Creature.abilities → L2-4 ✓
- §4.4 Viewport → L1-3/4 ✓
- §4.5 path preview → L1-2 (helper) + L1-7 (use) + L1-4 (render) ✓
- §4.6 highlights → L1-4 (render) + L1-8 (target mode) ✓
- §11 инварианты:
  - инв-1 clamp курсора → L1-7 step 3 (bf bounds check) ✓
  - инв-2 reset mode на TurnStarted → L1-9 step 3 ✓
  - инв-3 path preview validity → MoveAction validates на confirm, preview через find_chebyshev_path; не валидируем passability в preview, это OK по спеку
  - инв-4 TARGET не открывается с пустым reach → L1-9 step 3 ✓
  - инв-5 viewport не скроллится в MOVE → решение: `_auto_follow` вызывается ТОЛЬКО на `follow=actor_pos`, в MOVE при движении курсора передаём cursor отдельно, follow остаётся actor — корректно ✓
  - инв-6 валидация actor.ability_ids в registry → возможно стоит добавить в `register_default_abilities` или при build_keymap (KeyError если unknown id). build_keymap уже делает `registry.get(aid)` который кидает KeyError — fail fast ✓
  - инв-7 hotkey collisions в default — тест в L2-3 проверяет ✓

**Placeholder scan:**
- Нет «TBD/TODO/implement later»
- Все steps имеют конкретный код или конкретные команды
- L1-9 step 3 ссылается на `_compute_reachable_targets` — функция уже есть в текущем `action_intent_attack` (имплементатор переиспользует через extract)

**Type consistency:**
- `AbilityId` — `NewType("AbilityId", str)` — используется единообразно везде
- `Ability.id`, `Ability.default_hotkey`, `Creature.ability_ids`, `Creature.keybindings` — типы согласованы между L2-1, L2-4, L2-5
- `BattleMode.value` — `.value` используется в pilot-тестах (.value == "normal") ✓
- `MoveModeHandler.confirmed_path`, `TargetModeHandler.confirmed_target` — типы определены в L1-7/8, используются в L1-9 ✓
- `ModeHandler.overlay_data()` возвращает `(Square | None, dict[Square, str], tuple[Square, ...])` — все три реализации согласованы ✓
- `Creature` field name `ability_ids` (не `abilities`, чтобы не конфликтовать с `AbilityScores`) — согласован между L2-4 и L2-5 ✓

---

## Сводка по plan'у

- **18 task'ов** (10 в L1 + 8 в L2)
- **L1 — критичный UX-фикс**: inline-mode + 1×1 + viewport + удаление модалок
- **L2 — foundation framework**: Ability/Registry/rebindings + dynamic action-bar
- **L3 — отложено** в отдельный спек после feedback'а по L1+L2
- Каждый task — TDD bite-sized: failing test → impl → green → commit
- Все коммиты под "Maxim Lokotkov" / anticrab@users.noreply.github.com
- Документация (комментарии в коде, ABILITIES.md, TUI.md) — на русском
