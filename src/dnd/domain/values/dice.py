"""Бросок костей и нотация D&D.

Поддерживаемый синтаксис выражений::

    d20            один к20
    1d20           то же самое
    2d6+3          две к6 плюс модификатор
    4d6kh3         четыре к6, оставить три старших (генерация stats)
    4d6kl1         четыре к6, оставить один младший
    8d6            восемь к6 (например, урон Огненного шара)
    1k20+5         кириллическая «к» допускается синонимом

Программный API::

    expr = DiceExpr.parse("2d6+3")
    result = expr.roll(rng)
    result.total                 # сумма
    result.kept                  # значения, которые попали в total
    result.dropped               # отброшенные (для khN/klN)

    # к20 с преимуществом / помехой / критом
    d20 = DiceExpr.parse("d20+5")
    d20.roll(rng, advantage=True)
    weapon = DiceExpr.parse("1d8+3")
    weapon.roll(rng, crit=True)  # кости удваиваются, модификатор — нет

Этот модуль — низкоуровневая механика костей. Семантические броски движка
(атака, спасбросок, проверка) делаются через ``DiceRoller`` поверх
``RNG``, не через ``DiceExpr.roll(rng)`` напрямую — см. ``ENGINE.md`` §7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from dnd.domain.ports.rng import RNG

# Регулярка покрывает варианты "NdM", "NdMkhK"/"NdMklK", "+N"/"-N", "d20".
_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    ^\s*
    (?P<count>\d+)?              # число кубов (по умолчанию 1)
    [dк]                         # 'd' или 'к'
    (?P<sides>\d+)               # количество граней
    (?:                          # опц. оставить N старших/младших
        (?P<keep_mode>kh|kl)
        (?P<keep>\d+)
    )?
    \s*
    (?P<mod>[+-]\s*\d+)?         # опциональный модификатор
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


class DiceParseError(ValueError):
    """Raised when the dice expression syntax is invalid."""


@dataclass(frozen=True, slots=True)
class DiceExpr:
    """Иммутабельное выражение броска костей."""

    count: int
    sides: int
    modifier: int = 0
    keep_highest: int | None = None  # None → берём все
    keep_lowest: int | None = None

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError(f"dice count must be >= 1, got {self.count}")
        if self.sides < 1:
            raise ValueError(f"die sides must be >= 1, got {self.sides}")
        if self.keep_highest is not None and self.keep_lowest is not None:
            raise ValueError("cannot combine keep_highest and keep_lowest")
        keep = self.keep_highest if self.keep_highest is not None else self.keep_lowest
        if keep is not None and not 1 <= keep <= self.count:
            raise ValueError(f"keep={keep} is out of range 1..{self.count}")

    # --- разбор / печать --------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> DiceExpr:
        match = _PATTERN.match(text)
        if match is None:
            raise DiceParseError(f"cannot parse dice expression: {text!r}")
        count = int(match.group("count") or 1)
        sides = int(match.group("sides"))
        modifier_str = match.group("mod")
        mod = int(modifier_str.replace(" ", "")) if modifier_str else 0
        keep_mode = match.group("keep_mode")
        keep = int(match.group("keep")) if match.group("keep") else None
        kh = keep if keep_mode and keep_mode.lower() == "kh" else None
        kl = keep if keep_mode and keep_mode.lower() == "kl" else None
        try:
            return cls(count=count, sides=sides, modifier=mod, keep_highest=kh, keep_lowest=kl)
        except ValueError as exc:
            # Семантически невалидные значения (0d6, 1d0, 2d6kh5, ...) — это
            # тоже разновидность parse-ошибки с точки зрения вызывающего.
            raise DiceParseError(str(exc)) from exc

    def __str__(self) -> str:
        base = f"{self.count}d{self.sides}"
        if self.keep_highest is not None:
            base += f"kh{self.keep_highest}"
        elif self.keep_lowest is not None:
            base += f"kl{self.keep_lowest}"
        if self.modifier:
            base += f"{self.modifier:+d}"
        return base

    @property
    def is_single_d20(self) -> bool:
        """Это одиночный k20 (без kh/kl)?

        Преимущество/помеха применимы **только** к таким выражениям —
        это требование правил книги.
        """
        return (
            self.count == 1
            and self.sides == 20
            and self.keep_highest is None
            and self.keep_lowest is None
        )

    # --- бросок ----------------------------------------------------------

    def roll(
        self,
        rng: RNG,
        *,
        advantage: bool = False,
        disadvantage: bool = False,
        crit: bool = False,
    ) -> RollResult:
        """Бросить кости.

        ``advantage``/``disadvantage`` применимы **только** к одиночному
        d20 (механика «двух к20, берём больший/меньший» из правил книги).
        Применение этих флагов к другим выражениям (например, к броскам
        урона) — программная ошибка вызывающего, поднимается
        ``ValueError``.

        Преимущество и помеха одновременно взаимно гасятся (правило книги).

        ``crit`` удваивает количество брошенных костей; модификатор
        остаётся одиночным (см. книгу, «Критические попадания»). Крит
        применим к любому выражению и совместим с kh/kl: для ``4d6kh3``
        с ``crit=True`` бросаем 8 костей и оставляем 3 старших.
        """
        if (advantage or disadvantage) and not self.is_single_d20:
            raise ValueError(
                "advantage/disadvantage are applicable only to a single d20; "
                f"got {self} — use a plain roll instead"
            )

        if advantage and disadvantage:
            advantage = disadvantage = False  # взаимно гасятся

        if self.is_single_d20 and (advantage or disadvantage):
            a = rng.roll(20)
            b = rng.roll(20)
            chosen = max(a, b) if advantage else min(a, b)
            return RollResult(
                expr=self,
                rolls=(a, b),
                kept=(chosen,),
                dropped=(b if chosen == a else a,),
                modifier=self.modifier,
                total=chosen + self.modifier,
                advantage=advantage,
                disadvantage=disadvantage,
                crit=False,
            )

        count = self.count * (2 if crit else 1)
        rolls = tuple(rng.roll(self.sides) for _ in range(count))

        kept, dropped = self._select(rolls)
        return RollResult(
            expr=self,
            rolls=rolls,
            kept=kept,
            dropped=dropped,
            modifier=self.modifier,
            total=sum(kept) + self.modifier,
            advantage=False,
            disadvantage=False,
            crit=crit,
        )

    def _select(self, rolls: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
        if self.keep_highest is None and self.keep_lowest is None:
            return rolls, ()
        sorted_desc = sorted(rolls, reverse=True)
        if self.keep_highest is not None:
            # При crit количество костей удваивается; оставляем top-K от ВСЕХ.
            kept = tuple(sorted_desc[: self.keep_highest])
            dropped = tuple(sorted_desc[self.keep_highest :])
        else:
            assert self.keep_lowest is not None
            sorted_asc = sorted(rolls)
            kept = tuple(sorted_asc[: self.keep_lowest])
            dropped = tuple(sorted_asc[self.keep_lowest :])
        return kept, dropped


@dataclass(frozen=True, slots=True)
class RollResult:
    """Результат броска: все промежуточные данные доступны для UI и тестов."""

    expr: DiceExpr
    rolls: tuple[int, ...]
    kept: tuple[int, ...]
    modifier: int
    total: int
    dropped: tuple[int, ...] = field(default_factory=tuple)
    advantage: bool = False
    disadvantage: bool = False
    crit: bool = False

    @property
    def is_natural_20(self) -> bool:
        """Натуральная 20 на одиночном d20 (с учётом преимущества/помехи).

        Считаем натуральной 20 — выпадение 20 на оставленном к20.
        ``kept`` для одиночного d20 — это итоговая к20 (одна, даже при
        преимуществе); проверка `kept[0] == 20` корректна.
        """
        return (
            self.expr.is_single_d20
            and len(self.kept) == 1
            and self.kept[0] == 20
        )

    @property
    def is_natural_1(self) -> bool:
        return (
            self.expr.is_single_d20
            and len(self.kept) == 1
            and self.kept[0] == 1
        )

    @property
    def d20_raw(self) -> int | None:
        """Сырой результат одиночного k20 без бонусов — для статистики.

        Возвращает ``None`` для других выражений. Используется
        ``DiceStatisticsService`` (см. ``ENGINE.md`` §7.6).
        """
        if self.expr.is_single_d20 and len(self.kept) == 1:
            return self.kept[0]
        return None

    def describe(self) -> str:
        """Debug-only человекочитаемое описание.

        НЕ использовать для отображения игроку — UI-строки идут через
        Translator (см. ``I18N.md``). Этот метод только для логов и
        отладки; язык — английский, чтобы соответствовать правилу про
        технические сообщения.
        """
        parts = [f"{self.expr}"]
        rolls_text = ",".join(str(r) for r in self.rolls)
        parts.append(f"[{rolls_text}]")
        if self.dropped:
            dropped_text = ",".join(str(r) for r in self.dropped)
            parts.append(f"(dropped: {dropped_text})")
        if self.advantage:
            parts.append("with advantage")
        if self.disadvantage:
            parts.append("with disadvantage")
        if self.crit:
            parts.append("crit x2 dice")
        parts.append(f"= {self.total}")
        return " ".join(parts)
