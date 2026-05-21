"""Composition root приложения.

Здесь и только здесь происходит **связывание зависимостей**: чтение
конфигурации, создание реализаций портов, подписка обработчиков на
``EventBus``, сборка ``GameEngine``. Сюда **не** попадает ни typer-обвязка,
ни бизнес-логика правил — оба слоя отдельно.

Зачем выделено отдельным модулем (см. ``docs/ARCHITECTURE.md`` §4,
ADR-0001):

1. Тесты могут собирать движок одной строкой ``build_engine(...)``,
   подменяя любой порт через kwargs (``rng=ScriptedRNG([...])``).
2. CLI-обвязка (`app.py`) и сетевой сервер (пост-MVP) переиспользуют
   одну и ту же сборку.
3. Регистрация плагинов (Feature/Condition/Action/MonsterAI) делается
   здесь **явно** — без побочного эффекта при импорте модулей. См.
   ``docs/ARCHITECTURE.md`` §1, §3.12.

Текущее состояние: функции — заглушки, возвращают ``NotImplemented`` или
поднимают ``NotImplementedError``. Они будут наполнены по мере появления
``GameEngine``, ``ContentRepository``, ``SaveRepository``, ``Translator``,
``UserInterface``. Сигнатуры стабильны — это контракт.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dnd.domain.ports.rng import RNG


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Куда писать БД, контент, конфиг, логи.

    По умолчанию используются ``platformdirs`` (XDG-стандарт на Linux):

    * БД:      ``~/.local/share/dnd/dnd.sqlite``
    * контент: ``~/.local/share/dnd/content/``
    * конфиг:  ``~/.config/dnd/config.toml``
    * логи:    ``~/.local/state/dnd/logs/``

    Флаг CLI ``--workdir DIR`` поднимает все пути под ``DIR/`` (для
    разработки и преподавания).
    """

    db: Path
    content: Path
    config: Path
    logs: Path

    @classmethod
    def default(cls) -> AppPaths:
        raise NotImplementedError(
            "AppPaths.default — будет реализовано после подключения platformdirs "
            "(см. docs/ARCHITECTURE.md §9)."
        )

    @classmethod
    def under(cls, workdir: Path) -> AppPaths:
        return cls(
            db=workdir / "dnd.sqlite",
            content=workdir / "content",
            config=workdir / "config.toml",
            logs=workdir / "logs",
        )


def build_engine(
    *,
    workdir: Path | None = None,
    rng: RNG | None = None,
    # ui, content_repo, save_repo, translator, clock, event_bus — добавятся
    # по мере появления портов и сервисов; сейчас сознательно не входят в
    # сигнатуру (нечего собирать).
) -> object:
    """Собрать ``GameEngine`` со всеми зависимостями.

    Параметры (все опциональны): любые ``None`` заменяются дефолтными
    инфраструктурными реализациями (`RealRNG`, `SystemClock`,
    `BabelTranslator`, ...). Это «точки переопределения» для тестов и
    альтернативных сборок (LiveDiceRoller, RecordingUI и т.д.).

    Returns:
        GameEngine — пока ``NotImplementedError``, потому что движка ещё
        нет.
    """
    raise NotImplementedError(
        "build_engine — будет реализован вместе с GameEngine. "
        "Сейчас сигнатура зафиксирована как контракт; реализация в "
        "следующей вертикальной серии (см. ROADMAP.md §2)."
    )


def register_default_plugins() -> None:
    """Зарегистрировать встроенные плагины в module-level регистрах.

    Вызывается из ``build_engine`` **один раз** при старте приложения.
    Регистрация — **явная**, не через декораторы при импорте (см.
    ``docs/ARCHITECTURE.md`` §1, §3.12).

    Пример (будет реализован вместе с домен-классами):

        from dnd.domain.features.registry import FeatureRegistry
        from dnd.domain.features.second_wind import SecondWind
        FeatureRegistry.register("second_wind", SecondWind)
    """
    # Сейчас регистров и плагинов ещё нет — заготовка под будущее.
    return None
