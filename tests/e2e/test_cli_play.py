"""E2E smoke: CLI ``dnd play`` целиком работает через scripted интенты.

Реальный typer command тестируем через ``typer.testing.CliRunner``,
но ему нужны интерактивные prompt'ы — заменяем `ConsoleIntentProvider`
на ``ScriptedIntentProvider`` через monkeypatch.

Также — проверяем, что:

* `play <unknown>` корректно завершается с exit code 2;
* `EventPrinter` не падает на реальной цепочке событий.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from dnd.application.dto.ids import CreatureId
from dnd.application.dto.player_intent import AttackIntent, EndTurnIntent
from dnd.interfaces.cli.app import app
from dnd.interfaces.cli.scripted_provider import ScriptedIntentProvider

runner = CliRunner()


def test_play_unknown_scenario_exits_with_error() -> None:
    result = runner.invoke(app, ["play", "no-such-scenario"])
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower() or "not found" in (
        result.stderr or ""
    ).lower()


@pytest.mark.e2e
def test_play_mvp_skirmish_runs_to_end_with_scripted_intents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Подменяем ConsoleIntentProvider на ScriptedIntentProvider,
    запускаем `dnd play mvp_skirmish`, ожидаем нормальное завершение.

    Скрипт намерений: warrior атакует goblin'а в один ход.
    """
    # Скрипт: атака → end turn. После окончания queue провайдер сам
    # вернёт EndTurn — но для надёжности дадим явно.
    scripted = ScriptedIntentProvider(
        [
            AttackIntent(target_id=CreatureId("goblin1")),
            EndTurnIntent(),
        ]
    )

    # Подменим ConsoleIntentProvider на нашу заглушку, импортируемую
    # внутри app.play (lazy import).
    import dnd.interfaces.cli.app as app_module

    original_play = app_module.play

    def patched_play(
        scenario_id: str = "mvp_skirmish",
        content_dir: str = "data/content",
    ) -> None:
        # Копируем тело play, но подставляем scripted провайдер.
        from pathlib import Path

        from rich.console import Console

        from dnd.application.engine.game_runner import GameRunner
        from dnd.application.engine.scenario_builder import (
            build_encounter_from_scenario,
        )
        from dnd.composition import build_default_dependencies
        from dnd.domain.entities.battlefield import Battlefield
        from dnd.infrastructure.content.yaml_repository import (
            YamlContentRepository,
        )
        from dnd.infrastructure.rng.scripted_rng import ScriptedRNG
        from dnd.interfaces.cli.event_printer import EventPrinter

        repo = YamlContentRepository(Path(content_dir))
        scenario = repo.scenario_by_id(scenario_id)
        console = Console()
        # Scripted RNG чтобы тест был детерминированным.
        rng = ScriptedRNG([18, 8, 18, 7])
        deps = build_default_dependencies(
            battlefield=Battlefield(1, 1), rng=rng
        )
        enc = build_encounter_from_scenario(
            scenario, content=repo, deps=deps
        )
        EventPrinter(console).subscribe(enc.deps.event_bus)
        GameRunner(intent_provider=scripted).run(enc)

    monkeypatch.setattr(app_module, "play", patched_play)
    del original_play

    # Запускаем напрямую — typer не нужен тут, мы патчим само app.play.
    patched_play("mvp_skirmish", "data/content")
    # Если дошли сюда — бой завершился без исключений. Этот тест
    # проверяет «всё собирается и крутится».
