"""Спасброски от смерти PC.

Книга 2024, «Падение до 0 хитов» (стр. 27). Применяется только к
персонажам игроков (Character). NPC при 0 HP мгновенно мертвы.

Жизненный цикл состояния:

1. PC падает в 0 HP → ``successes=0, failures=0, stable=False``.
2. На начале **своего** хода с 0 HP и не stable → бросок d20:

   * ``>= 10`` — успех (``successes += 1``);
   * ``< 10`` — провал (``failures += 1``);
   * **нат-20** — восстановление 1 HP, состояние сбрасывается;
   * **нат-1** — два провала.

3. Получение урона при 0 HP:

   * обычный удар — один провал;
   * критическое попадание — два провала;
   * урон, **превышающий максимум HP** одним ударом — мгновенная смерть.

4. **3 успеха** → stable. Спасброски прекращаются; через 1 час
   восстанавливается 1 HP (это уже забота времени, не этого VO).
5. **3 провала** → смерть.
6. **Любое лечение** (>0 HP) — состояние сбрасывается, PC приходит в сознание.
7. **Стабилизация Медициной** другого существа (WIS-Medicine DC 10) →
   stable, но не выводит в сознание.

VO иммутабельный. Любая операция возвращает новый ``DeathSaveState``.
Бросок d20 делается **снаружи** (через ``DiceRoller``); этот VO лишь
интерпретирует уже выпавший результат.
"""

from __future__ import annotations

from dataclasses import dataclass

_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class DeathSaveState:
    """Состояние спасбросков от смерти.

    Инвариант: ``successes`` и ``failures`` принимают значения 0..3.
    Их «выход за порог» означает терминальное состояние:

    * ``successes == 3`` → ``stable=True`` (не нужны новые броски).
    * ``failures == 3`` → :attr:`is_dead` (см. ниже).
    """

    successes: int = 0
    failures: int = 0
    stable: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.successes <= _THRESHOLD:
            raise ValueError(f"successes must be in 0..{_THRESHOLD}, got {self.successes}")
        if not 0 <= self.failures <= _THRESHOLD:
            raise ValueError(f"failures must be in 0..{_THRESHOLD}, got {self.failures}")
        # Не валидируем stable отдельно: state с stable=True и successes<3
        # допустим (стабилизация Медициной).

    @property
    def is_dead(self) -> bool:
        return self.failures >= _THRESHOLD

    @property
    def is_stable(self) -> bool:
        return self.stable or self.successes >= _THRESHOLD

    # --- операции -------------------------------------------------------

    def apply_save_roll(self, d20_raw: int) -> DeathSaveState:
        """Применить результат бросаемого спасброска от смерти.

        ``d20_raw`` — сырое значение d20 (без модификаторов). У спасбросков
        от смерти модификаторов в принципе нет (книга, стр. 27).

        Поведение:

        * stable или dead — больше не бросаем (возвращаем self).
        * нат-20 → ``recovered()`` (1 HP, обнуление состояния);
        * нат-1 → два провала;
        * >= 10 → один успех;
        * < 10 → один провал.

        После 3 успехов автоматически становится stable;
        после 3 провалов — :attr:`is_dead`.
        """
        if not 1 <= d20_raw <= 20:
            raise ValueError(f"d20 raw value must be in 1..20, got {d20_raw}")
        if self.is_dead or self.is_stable:
            return self
        if d20_raw == 20:
            # Особый случай: воскрешение на 1 HP — обрабатывается на
            # уровне Character, потому что требует изменения HP. Здесь —
            # просто сбрасываем счётчики; флаг recovered несёт смысл наружу.
            return DeathSaveState(successes=0, failures=0, stable=False)
        if d20_raw == 1:
            return self._with_failures(self.failures + 2)
        if d20_raw >= 10:
            return self._with_successes(self.successes + 1)
        return self._with_failures(self.failures + 1)

    def apply_damage_at_zero(self, *, is_critical: bool = False) -> DeathSaveState:
        """Зафиксировать провал от полученного урона на 0 HP.

        * Обычный удар → один провал.
        * Критический → два провала.

        Если урон **превысил максимум HP** (massive damage) — это
        мгновенная смерть, обрабатывается на уровне Creature
        (через переход в DeathSaveState(failures=3)).
        """
        if self.is_dead or self.is_stable:
            return self
        delta = 2 if is_critical else 1
        return self._with_failures(self.failures + delta)

    def stabilized(self) -> DeathSaveState:
        """Стабилизирован (Медициной, заклинанием Spare the Dying и т.п.).

        Сохраняет накопленные счётчики (для логики «трижды спасся —
        получил inspiration»), но снимает необходимость дальнейших
        бросков. Лечение всё ещё нужно, чтобы поднять в сознание.
        """
        if self.is_dead:
            return self
        return DeathSaveState(successes=self.successes, failures=self.failures, stable=True)

    def reset(self) -> DeathSaveState:
        """Сбросить в исходное (лечение к >0 HP, эффект нат-20, и т.п.)."""
        return DeathSaveState()

    # --- внутреннее -----------------------------------------------------

    def _with_successes(self, n: int) -> DeathSaveState:
        n = min(n, _THRESHOLD)
        return DeathSaveState(
            successes=n,
            failures=self.failures,
            stable=self.stable or n >= _THRESHOLD,
        )

    def _with_failures(self, n: int) -> DeathSaveState:
        n = min(n, _THRESHOLD)
        return DeathSaveState(successes=self.successes, failures=n, stable=self.stable)
