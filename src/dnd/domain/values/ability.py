"""Характеристики и модификаторы (Глава 1 книги, «Шесть характеристик»)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Ability(StrEnum):
    """Шесть характеристик D&D."""

    STR = "STR"
    DEX = "DEX"
    CON = "CON"
    INT = "INT"
    WIS = "WIS"
    CHA = "CHA"

    @property
    def label_ru(self) -> str:
        return _RU_LABELS[self]


_RU_LABELS = {
    Ability.STR: "Сила",
    Ability.DEX: "Ловкость",
    Ability.CON: "Телосложение",
    Ability.INT: "Интеллект",
    Ability.WIS: "Мудрость",
    Ability.CHA: "Харизма",
}


def modifier(score: int) -> int:
    """Модификатор характеристики = floor((score − 10) / 2).

    Формула из книги, эквивалентна табличному значению на все 1..30.
    """
    if score < 1:
        raise ValueError(f"показатель характеристики не может быть < 1, получено {score}")
    return (score - 10) // 2


@dataclass(frozen=True, slots=True)
class AbilityScore:
    """Значение одной характеристики.

    Иммутабельный value-object. Любая модификация (баф/дебаф/повышение
    уровня) возвращает новый объект — это упрощает откат и сериализацию.
    """

    ability: Ability
    score: int

    def __post_init__(self) -> None:
        if not 1 <= self.score <= 30:
            raise ValueError(
                f"{self.ability.label_ru}: {self.score} вне диапазона 1..30"
            )

    @property
    def modifier(self) -> int:
        return modifier(self.score)

    def adjusted(self, delta: int, *, cap: int = 20) -> AbilityScore:
        """Прибавить к показателю ``delta``, но не выше ``cap`` (по умолчанию 20)."""
        new_score = min(self.score + delta, cap) if delta > 0 else self.score + delta
        return AbilityScore(self.ability, new_score)


@dataclass(frozen=True, slots=True)
class AbilityScores:
    """Полный набор из шести характеристик."""

    str_: AbilityScore
    dex: AbilityScore
    con: AbilityScore
    int_: AbilityScore
    wis: AbilityScore
    cha: AbilityScore

    @classmethod
    def of(
        cls,
        *,
        str_: int,
        dex: int,
        con: int,
        int_: int,
        wis: int,
        cha: int,
    ) -> AbilityScores:
        return cls(
            str_=AbilityScore(Ability.STR, str_),
            dex=AbilityScore(Ability.DEX, dex),
            con=AbilityScore(Ability.CON, con),
            int_=AbilityScore(Ability.INT, int_),
            wis=AbilityScore(Ability.WIS, wis),
            cha=AbilityScore(Ability.CHA, cha),
        )

    def get(self, ability: Ability) -> AbilityScore:
        return {
            Ability.STR: self.str_,
            Ability.DEX: self.dex,
            Ability.CON: self.con,
            Ability.INT: self.int_,
            Ability.WIS: self.wis,
            Ability.CHA: self.cha,
        }[ability]

    def modifier(self, ability: Ability) -> int:
        return self.get(ability).modifier
