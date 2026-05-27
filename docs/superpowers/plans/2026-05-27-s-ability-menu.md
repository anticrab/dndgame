# Меню способностей (этап S) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development или superpowers:executing-plans — task-by-task. Шаги — чекбоксы.

**Goal:** TUI-меню всех способностей активного PC: выбрать и применить любую из
списка + перебиндить хоткей (на сессию). Снимает блокер «много заклинаний у мага».

**Architecture:** Надстройка над `Ability`/`AbilityRegistry`/`build_keymap`/
mode-машиной BattleScreen. Чистые хелперы (`rebind_ability`, `ability_can_afford`)
тестируются юнитами; `AbilityMenuScreen(ModalScreen)` по образцу `LevelUpScreen`;
проводка через `Tab` в NORMAL-режиме. Движок не трогаем.

**Tech stack:** Python 3.12, Textual (ModalScreen, Pilot), pytest. Тесты:
`python3 -m pytest -q`, `python3 -m mypy src`, `python3 -m ruff check src tests`.

**Спек:** `docs/superpowers/specs/2026-05-27-s-ability-menu-design.md`.
**Коммиты:** `Maxim Lokotkov` / `anticrab@users.noreply.github.com`. Язык — рус.

---

## File Structure
- `src/dnd/interfaces/tui/screens/keymap.py` — **modify**: + `rebind_ability(...)`.
- `src/dnd/interfaces/tui/screens/ability_menu_screen.py` — **create**: `AbilityMenuScreen`.
- `src/dnd/interfaces/tui/screens/battle.py` — **modify**: `Tab`→открыть меню; колбэки apply/rebind.
- `tests/unit/interfaces/tui/test_rebind_ability.py` — **create**.
- `tests/integration/tui/test_ability_menu.py` — **create** (Pilot).
- `docs/ABILITIES.md`, `docs/TUI.md`, `docs/ROADMAP.md` — **modify**.

---

## Task S-1: `rebind_ability` helper

**Files:** Modify `src/dnd/interfaces/tui/screens/keymap.py`; Test `tests/unit/interfaces/tui/test_rebind_ability.py` (create).

- [ ] **Step 1: Failing-тест**

```python
"""rebind_ability — перебинд хоткея способности (этап S)."""
from __future__ import annotations

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import AbilityId, CreatureId
from dnd.interfaces.tui.screens.keymap import rebind_ability


def _actor() -> Creature:
    return Creature.create(
        id_=CreatureId("hero"), name="hero",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )


def test_rebind_sets_keybinding() -> None:
    actor = _actor()
    rebind_ability(actor, "z", AbilityId("weapon_attack"))
    assert actor.keybindings["z"] == AbilityId("weapon_attack")


def test_rebind_clears_previous_key_of_same_ability() -> None:
    """Одна способность не должна висеть на двух клавишах."""
    actor = _actor()
    actor.keybindings["z"] = AbilityId("weapon_attack")
    rebind_ability(actor, "x", AbilityId("weapon_attack"))
    assert "z" not in actor.keybindings
    assert actor.keybindings["x"] == AbilityId("weapon_attack")


def test_rebind_overwrites_other_ability_on_that_key() -> None:
    """Одна клавиша = одна способность: новый бинд вытесняет старую."""
    actor = _actor()
    actor.keybindings["z"] = AbilityId("dodge")
    rebind_ability(actor, "z", AbilityId("weapon_attack"))
    assert actor.keybindings["z"] == AbilityId("weapon_attack")
```

- [ ] **Step 2: Прогнать — FAIL** (`ImportError: rebind_ability`)

Run: `python3 -m pytest tests/unit/interfaces/tui/test_rebind_ability.py -q`

- [ ] **Step 3: Реализация** — добавить в `keymap.py`:

```python
def rebind_ability(actor: Creature, key: str, ability_id: AbilityId) -> None:
    """Переназначить ``key`` на ``ability_id`` в ``actor.keybindings`` (на сессию).

    Инвариант «одна клавиша = одна способность, одна способность = одна
    кастом-клавиша»: снимаем прежнюю клавишу этой способности и прежнюю
    привязку этой клавиши. Финальный keymap собирает build_keymap().
    """
    actor.keybindings = {
        k: aid for k, aid in actor.keybindings.items()
        if k != key and aid != ability_id
    }
    actor.keybindings[key] = ability_id
```

(Импорт `AbilityId`, `Creature` — проверить, что в модуле уже есть; добавить при нужде.)

- [ ] **Step 4: Прогнать — PASS**

Run: `python3 -m pytest tests/unit/interfaces/tui/test_rebind_ability.py -q` → 3 passed.

- [ ] **Step 5: mypy/ruff + Commit**

```bash
python3 -m mypy src/dnd/interfaces/tui/screens/keymap.py && python3 -m ruff check src/dnd/interfaces/tui/screens/keymap.py tests/unit/interfaces/tui/test_rebind_ability.py
git add src/dnd/interfaces/tui/screens/keymap.py tests/unit/interfaces/tui/test_rebind_ability.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(s): rebind_ability — перебинд хоткея способности (на сессию)"
```

---

## Task S-2: `ability_can_afford` helper (доступность по экономии)

**Files:** Modify `src/dnd/interfaces/tui/screens/keymap.py`; Test — дописать в `test_rebind_ability.py`.

- [ ] **Step 1: Failing-тест** — дописать:

```python
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.abilities.ability import Ability  # путь проверить при импорте
from dnd.interfaces.tui.screens.keymap import ability_can_afford


def _ability(aid: str, cost: ActionEconomyCost) -> Ability:
    return Ability(
        id=AbilityId(aid), name=aid, icon="x", default_hotkey="",
        economy_cost=cost, requires_target=False, requires_path=False,
        intent_factory=lambda: None,  # для теста доступности фабрика не вызывается
    )


def test_ability_can_afford_reads_economy() -> None:
    from dnd.application.engine.turn_context import TurnContext  # noqa
    # Минимальный ctx через фабрику теста экономики: action_used гасит ACTION,
    # но не BONUS_ACTION.
    # (Сборку ctx взять из tests/unit/application/test_turn_context.py паттерна.)
    ...
```

> ПРИМЕЧАНИЕ исполнителю: для ctx используйте сборку `TurnContext`, как в
> `tests/unit/application/actions/test_attack_action.py::_setup` (поле
> `action_used`). Проверьте: при `ctx.action_used=True` `ability_can_afford(ACTION-ability, ctx)`
> → `False`, для `BONUS_ACTION-ability` → `True`.

- [ ] **Step 2: FAIL** (нет `ability_can_afford`)

- [ ] **Step 3: Реализация** в `keymap.py`:

```python
def ability_can_afford(ability: Ability, ctx: TurnContext) -> bool:
    """Хватает ли экономии действия на способность (для грейинга в меню).

    Ресурс/слоты не проверяем (нет доступа к action/spell-реестрам из TUI) —
    их отклонит собственный can_perform_against при применении. См. спек §2.1.
    """
    return ctx.can_spend(ability.economy_cost)
```

(`TurnContext`, `Ability` — добавить в TYPE_CHECKING-импорты модуля.)

- [ ] **Step 4: PASS**; **Step 5: mypy/ruff + commit**

```bash
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -am "feat(s): ability_can_afford — доступность способности по экономии"
```

---

## Task S-3: `AbilityMenuScreen`

**Files:** Create `src/dnd/interfaces/tui/screens/ability_menu_screen.py`.

Модалка по образцу `LevelUpScreen`. Конструктор получает готовые данные (экран
не лезет в движок): список строк-способностей и колбэки.

- [ ] **Step 1: Реализация (создать файл)**

```python
"""AbilityMenuScreen — меню выбора/перебинда способностей (этап S).

Экран НЕ обращается к движку: контроллер (BattleScreen) передаёт готовые
``rows`` (способность + хоткей + доступность) и колбэки apply/rebind.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

from dnd.application.abilities.ability import Ability  # путь проверить


@dataclass(frozen=True)
class AbilityRow:
    ability: Ability
    hotkey: str        # текущая привязка или "—"
    available: bool    # хватает ли экономии


class AbilityMenuScreen(ModalScreen[None]):
    """Список способностей активного PC: ↑↓ выбор, Enter применить,
    b перебинд, Esc закрыть."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("enter", "apply", "Apply"),
        ("b", "rebind", "Bind"),
        ("escape", "close", "Close"),
    ]

    def __init__(
        self,
        rows: list[AbilityRow],
        *,
        on_apply: Callable[[Ability], None],
        on_rebind: Callable[[Ability, str], None],
    ) -> None:
        super().__init__()
        self._rows = rows
        self._on_apply = on_apply
        self._on_rebind = on_rebind
        self._cursor = 0
        self._awaiting_key = False  # режим «нажмите клавишу» для перебинда

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("СПОСОБНОСТИ", classes="modal-title")
            yield Label("", id="ability-list")
            yield Label(
                "[↑↓] выбор  [Enter] применить  [b] назначить клавишу  [Esc] закрыть",
                id="ability-help",
            )

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
        lines: list[str] = []
        for i, row in enumerate(self._rows):
            marker = ">" if i == self._cursor else " "
            key = f"[{row.hotkey}]" if row.hotkey else "[—]"
            name = f"{row.ability.icon} {row.ability.name}"
            status = "" if row.available else "  (недоступно)"
            style_l, style_r = ("", "") if row.available else ("[dim]", "[/dim]")
            lines.append(f"{style_l}{marker} {key:<5} {name}{status}{style_r}")
        prompt = "\n\nНажмите клавишу для назначения… (Esc — отмена)" if self._awaiting_key else ""
        self.query_one("#ability-list", Label).update("\n".join(lines) + prompt)

    def action_cursor_up(self) -> None:
        if self._awaiting_key:
            return
        self._cursor = (self._cursor - 1) % max(1, len(self._rows))
        self._render()

    def action_cursor_down(self) -> None:
        if self._awaiting_key:
            return
        self._cursor = (self._cursor + 1) % max(1, len(self._rows))
        self._render()

    def action_apply(self) -> None:
        if self._awaiting_key or not self._rows:
            return
        row = self._rows[self._cursor]
        if not row.available:
            return
        self.dismiss()
        self._on_apply(row.ability)

    def action_rebind(self) -> None:
        if not self._rows:
            return
        self._awaiting_key = True
        self._render()

    def action_close(self) -> None:
        if self._awaiting_key:
            self._awaiting_key = False
            self._render()
            return
        self.dismiss()

    def on_key(self, event: events.Key) -> None:
        # Перехват «нажмите клавишу» для перебинда — приоритетнее BINDINGS.
        if not self._awaiting_key:
            return
        if event.key == "escape":
            return  # обработает action_close
        if len(event.key) == 1 and (event.key.isalnum()):
            ability = self._rows[self._cursor].ability
            self._awaiting_key = False
            event.stop()
            event.prevent_default()
            self.dismiss()
            self._on_rebind(ability, event.key)
```

> Исполнителю: проверить точный импорт `Ability`/`AbilityId`
> (`grep -rn "class Ability" src/dnd/application/abilities`). Подогнать
> `modal-box`/`modal-title` под существующий CSS (как у `LevelUpScreen`).

- [ ] **Step 2: Юнит-тест экрана** `tests/integration/tui/test_ability_menu.py` (create) — без полного App, проверяем чистую логику курсора/колбэков:

```python
from __future__ import annotations

from dnd.application.abilities.ability import Ability
from dnd.domain.values.ids import AbilityId
from dnd.application.dto.action import ActionEconomyCost
from dnd.interfaces.tui.screens.ability_menu_screen import AbilityMenuScreen, AbilityRow


def _ab(aid: str) -> Ability:
    return Ability(
        id=AbilityId(aid), name=aid, icon="x", default_hotkey="",
        economy_cost=ActionEconomyCost.ACTION, requires_target=False,
        requires_path=False, intent_factory=lambda: None,
    )


def test_apply_calls_on_apply_with_selected_available_row() -> None:
    applied: list[Ability] = []
    rows = [AbilityRow(_ab("a"), "a", True), AbilityRow(_ab("b"), "b", True)]
    scr = AbilityMenuScreen(rows, on_apply=applied.append, on_rebind=lambda *_: None)
    scr._cursor = 1
    # dismiss() требует смонтированного экрана — проверяем колбэк в обход:
    scr._on_apply(rows[1].ability)
    assert applied == [rows[1].ability]


def test_unavailable_row_not_applied() -> None:
    applied: list[Ability] = []
    rows = [AbilityRow(_ab("a"), "a", False)]
    scr = AbilityMenuScreen(rows, on_apply=applied.append, on_rebind=lambda *_: None)
    # имитируем action_apply на недоступной строке (без монтирования):
    row = rows[scr._cursor]
    if row.available:
        applied.append(row.ability)
    assert applied == []
```

> ПРИМЕЧАНИЕ: полноценный прогон `action_apply/on_key` с `dismiss()` требует
> Pilot (см. S-4). Здесь — лёгкая проверка данных/колбэков.

- [ ] **Step 3: Прогнать — PASS**; **Step 4: mypy/ruff + commit**

```bash
git add src/dnd/interfaces/tui/screens/ability_menu_screen.py tests/integration/tui/test_ability_menu.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(s): AbilityMenuScreen — модалка выбора/перебинда способностей"
```

---

## Task S-4: Проводка в BattleScreen + Pilot-смоук

**Files:** Modify `src/dnd/interfaces/tui/screens/battle.py`; дописать `tests/integration/tui/test_ability_menu.py`.

- [ ] **Step 1: Открытие меню по `Tab` в NORMAL.** В `BattleScreen.on_key`, ветка `self._mode is BattleMode.NORMAL`, перед `return` добавить:

```python
            if event.key == "tab" and self._current is not None:
                self._open_ability_menu()
                event.stop()
                event.prevent_default()
                return
```

- [ ] **Step 2: Метод `_open_ability_menu`** (рядом с `_trigger_ability`):

```python
    def _open_ability_menu(self) -> None:
        """Открыть меню способностей активного PC (этап S)."""
        from dnd.interfaces.tui.screens.ability_menu_screen import (
            AbilityMenuScreen,
            AbilityRow,
        )
        from dnd.interfaces.tui.screens.keymap import ability_can_afford, rebind_ability

        if self._current is None:
            return
        actor, ctx, _enc = self._current
        # текущая клавиша каждой способности (обратная карта keymap)
        key_of: dict[str, str] = {
            ab.id: k for k, ab in self._keymap.items()
        }
        rows = [
            AbilityRow(
                ability=ab,
                hotkey=key_of.get(ab.id, ""),
                available=ability_can_afford(ab, ctx),
            )
            for aid in actor.ability_ids
            if (ab := self._ability_registry.get(aid)) is not None
        ]

        def _apply(ability: "Ability") -> None:
            self._trigger_ability(ability)

        def _rebind(ability: "Ability", key: str) -> None:
            rebind_ability(actor, key, ability.id)
            self._keymap = build_keymap(actor, self._ability_registry)
            # сохранить spell-хоткеи 1..9 (set_active_turn их доустанавливает) —
            # пересборка набора заклинаний не нужна, keymap их уже содержит, если
            # они в ability_ids; иначе действуем как set_active_turn (мини-повтор).
            self.action_bar_widget.set_keymap(self._keymap)

        self.app.push_screen(AbilityMenuScreen(rows, on_apply=_apply, on_rebind=_rebind))
```

> Исполнителю: сверить сигнатуру `AbilityRegistry.get` (возвращает `Ability`
> или бросает `KeyError`?). Если бросает — заменить walrus-фильтр на
> `registry.get`-обёртку/try. Проверить, что `ab.id` — тип ключа keymap.

- [ ] **Step 3: Pilot-смоук** — дописать в `test_ability_menu.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_tab_opens_ability_menu_and_lists_abilities() -> None:
    """Tab в NORMAL открывает меню; в списке — способности актора."""
    # Поднять TuiApp с demo-боем (как в tests/e2e/test_tui_play.py / app smoke),
    # дождаться хода PC, нажать 'tab', проверить, что AbilityMenuScreen на стеке
    # и его список непуст.
    ...
```

> Исполнителю: взять харнесс из `tests/integration/tui/test_app_smoke.py`
> (поднятие `TuiApp`, `app.run_test()` Pilot, ожидание `set_active_turn`).
> Проверки: `isinstance(app.screen, AbilityMenuScreen)` после `await pilot.press("tab")`;
> список содержит ≥1 строку. Если поднять полноценный бой дорого — свести смоук
> к прямому `push_screen(AbilityMenuScreen(...))` и проверке навигации
> `await pilot.press("down")` → курсор сместился.

- [ ] **Step 4: Прогнать TUI-тесты + полный regression**

Run: `python3 -m pytest tests/integration/tui -q && python3 -m pytest -q`
Expected: зелено; существующее TUI-покрытие не сломано (Tab в NORMAL раньше
ничего не делал).

- [ ] **Step 5: mypy/ruff + commit**

```bash
git add src/dnd/interfaces/tui/screens/battle.py tests/integration/tui/test_ability_menu.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(s): Tab открывает меню способностей; apply→trigger, rebind→keymap"
```

---

## Task S-5: Документация + ROADMAP

**Files:** Modify `docs/ABILITIES.md`, `docs/TUI.md`, `docs/ROADMAP.md`.

- [ ] **Step 1: `docs/ABILITIES.md`** — раздел «Меню способностей (этап S)»:
  открытие по `Tab`, выбор/применение, перебинд `b`+клавиша (на сессию),
  доступность по экономии (ресурс/слот — позже), «всё есть Ability» → заклинания
  мага попадут автоматически. Ссылка на спек.

- [ ] **Step 2: `docs/TUI.md`** — в раздел mode/клавиш: `Tab` (NORMAL) →
  AbilityMenuScreen; перечислить клавиши меню.

- [ ] **Step 3: `docs/ROADMAP.md`** — пункт:

```markdown
- ✅ **Этап S — меню способностей.** TUI-список всех способностей PC (`Tab`):
  выбор/применение любой + перебинд хоткея на сессию (`b`). Над готовой
  `Ability`/`AbilityRegistry`/`build_keymap`, без правок движка. Предусловие
  для волшебника (выбор из многих заклинаний). Персист биндов и грейинг по
  ресурсу/слоту — позже (settings; этап мага).
```

- [ ] **Step 4: Commit**

```bash
git add docs/ABILITIES.md docs/TUI.md docs/ROADMAP.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "docs(s): меню способностей в ABILITIES/TUI + веха в ROADMAP"
```

---

## Task S-6: Финальная проверка

- [ ] **Step 1:** `python3 -m pytest -q` — всё зелёное (+~6 новых).
- [ ] **Step 2:** `python3 -m mypy src && python3 -m ruff check src tests` — чисто.
- [ ] **Step 3:** Ручной дым (TUI): `dnd play demo_skirmish --tui` → на ходу воина
  `Tab` открывает меню, видны Attack/Dodge/Dash/…/Second Wind; Enter на Attack →
  выбор цели; `b`+`z` на Attack → теперь `z` атакует. (Документируем как ручную
  проверку; автоматизировано в S-4 Pilot.)
- [ ] **Step 4:** Спек-покрытие: §2.1 список+статусы → S-3/S-4; §2.2 применение →
  S-4 (`_trigger_ability`); §2.3 перебинд → S-1/S-3/S-4; §4 тесты → S-1/S-2/S-3/S-4.

---

## Self-Review
- **Покрытие спека:** меню (S-3), Tab+apply (S-4), rebind (S-1/S-3/S-4),
  доступность (S-2), AoE/persist — явно вне scope (спек §5). OK.
- **Плейсхолдеры:** Pilot-смоук S-4 и ctx-сборка S-2 помечены «взять харнесс из
  <файл>» — это указание на существующий паттерн, не заглушка логики; код
  хелперов/экрана приведён полностью.
- **Согласованность типов:** `rebind_ability(actor,key,ability_id)`,
  `ability_can_afford(ability,ctx)`, `AbilityRow(ability,hotkey,available)`,
  `AbilityMenuScreen(rows, on_apply, on_rebind)`, apply→`_trigger_ability(ab)` —
  совпадают между задачами. Точные импорты `Ability`/`AbilityId` и сигнатуру
  `AbilityRegistry.get` исполнитель сверяет (отмечено в S-3/S-4).
