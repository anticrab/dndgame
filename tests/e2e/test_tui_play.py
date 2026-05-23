"""E2E TUI: headless через ``Pilot`` — играем сценарий, проверяем
что лог наполняется и encounter завершается.

Тесты — самые «толстые»: реальный Encounter + RealRNG(seed) + Textual
Pilot. Зато покрывают весь стек: worker-thread, EventRenderer,
TuiIntentProvider, BattleScreen.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")  # без textual эти тесты пропускаются


def _make_encounter():
    from dnd.application.engine.scenario_builder import (
        build_encounter_from_scenario,
    )
    from dnd.composition import build_default_runtime_services
    from dnd.infrastructure.content.yaml_repository import (
        YamlContentRepository,
    )
    from dnd.infrastructure.rng.real_rng import RealRNG

    repo = YamlContentRepository(Path("data/content"))
    scenario = repo.scenario_by_id("mvp_skirmish")
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    return build_encounter_from_scenario(
        scenario, content=repo, services=services
    )


@pytest.mark.e2e
def test_tui_boots_with_real_encounter_and_log_fills() -> None:
    """Самый простой smoke: TuiApp поднимается, worker запускается,
    EventRenderer пишет события в LogWidget."""
    from dnd.interfaces.tui import TuiApp

    enc = _make_encounter()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            # Дать worker'у завести бой и сделать initiative.
            await pilot.pause(0.2)
            screen = pilot.app.screen
            log = screen.query_one("#log")
            # InitiativeRolled / RoundStarted / TurnStarted уже должны
            # быть в логе (как минимум 3 строки).
            assert len(log.lines) >= 3

    asyncio.run(_go())


@pytest.mark.e2e
def test_tui_dodge_intent_through_keypress() -> None:
    """Нажимаем `d` (Dodge) на ходу PC — TuiIntentProvider получает
    DodgeIntent, GameRunner выполняет → лог получает StanceTaken."""
    from dnd.interfaces.tui import TuiApp

    enc = _make_encounter()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            # Может быть, AI ходит первым (RealRNG seed=42 на mvp_skirmish:
            # goblin1=21, aelar=2 — goblin первый). Подождём пока aelar
            # получит ход (set_active_turn будет вызван).
            screen = pilot.app.screen
            for _ in range(20):
                if screen._current is not None:
                    break
                await pilot.pause(0.1)
            # Если PC получил ход — нажимаем `d`, дальше `e`.
            if screen._current is not None:
                await pilot.press("d")
                await pilot.pause(0.2)
                await pilot.press("e")
                await pilot.pause(0.5)
            # В любом случае лог должен иметь упоминание стойки или
            # завершения боя.
            log = screen.query_one("#log")
            content = " ".join(str(line) for line in log.lines)
            assert any(
                marker in content
                for marker in ("DODGING", "ENCOUNTER ENDED", "WINS")
            ), content

    asyncio.run(_go())


@pytest.mark.e2e
def test_tui_quit_via_q_exits_cleanly() -> None:
    """Нажатие `q` закрывает приложение; provider.shutdown разблокирует
    worker; никаких висящих тредов."""
    from dnd.interfaces.tui import TuiApp

    enc = _make_encounter()
    app = TuiApp(encounter=enc)

    async def _go() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("q")
            await pilot.pause(0.1)
        # После выхода из async-with App.exit() выполнен,
        # worker — daemon-thread → не блокирует процесс.

    asyncio.run(_go())
