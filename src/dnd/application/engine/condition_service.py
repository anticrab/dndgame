"""``ConditionService`` — каскадное применение состояний с учётом implies.

Когда на существо накладывается Unconscious, по книге также активируются
Incapacitated и Prone (стр. 367, глоссарий). ``Creature.apply_condition``
сам по себе наложит только один ConditionId — он не знает про реестр.
Этот сервис делает транзитивное замыкание через
:class:`ConditionRegistry` и накладывает всё.

Сервис **не** хранит состояние — он бессостоятельная функция-обёртка,
параметризованная registry. Это позволяет использовать его и в Encounter,
и в тестах.

Поведение при снятии: симметричное снятие implies **не** делается
автоматически. Книга 2024 не предполагает «снять Unconscious — снять
Incapacitated и Prone», потому что Incapacitated и Prone могут быть
наложены другими источниками. Снятие каждого состояния — отдельным
явным вызовом.
"""

from __future__ import annotations

from dataclasses import dataclass

from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import ConditionId


@dataclass(frozen=True, slots=True)
class ConditionApplyResult:
    """Что произошло при apply_with_implies.

    * ``applied`` — все ConditionId, которые реально были добавлены
      (с учётом implies, исключая immunities и уже наложенные).
    * ``skipped_immune`` — отказы из-за immunity. Полезно для лога:
      «Скелет иммунен к отравлению».
    * ``already_present`` — состояния, которые уже были (не ошибка,
      но в логе можно отметить).
    """

    applied: frozenset[ConditionId]
    skipped_immune: frozenset[ConditionId]
    already_present: frozenset[ConditionId]


class ConditionService:
    """Каскадное применение состояний по правилам ``implies``."""

    def __init__(self, registry: ConditionRegistry) -> None:
        self._registry = registry

    def apply_with_implies(
        self,
        creature: Creature,
        condition_id: ConditionId,
    ) -> ConditionApplyResult:
        """Наложить состояние и все его транзитивные ``implies``.

        Поведение:

        * Если состояние не в registry — KeyError (контент-баг).
        * Иммунитет к корневому состоянию — ничего не накладывается,
          ``skipped_immune={condition_id}`` (правило книги: иммунитет
          против Unconscious означает «не падаешь в сон», и каскад в
          этом случае тоже не запускается).
        * Иммунитет к одному из implies — пропускается **только** этот
          implies, остальное накладывается. Это сознательный выбор:
          существо может быть иммунно к Prone (например, плавающий
          дракон), но всё ещё стать Unconscious.
        """
        if not self._registry.has(condition_id):
            raise KeyError(f"condition {condition_id!r} is not in registry")

        if condition_id in creature.condition_immunities:
            return ConditionApplyResult(
                applied=frozenset(),
                skipped_immune=frozenset({condition_id}),
                already_present=frozenset(),
            )

        applied: set[ConditionId] = set()
        skipped: set[ConditionId] = set()
        already: set[ConditionId] = set()

        # BFS/DFS по графу implies. Защита от циклов через `seen`.
        to_apply: list[ConditionId] = [condition_id]
        seen: set[ConditionId] = set()
        while to_apply:
            cid = to_apply.pop()
            if cid in seen:
                continue
            seen.add(cid)

            if cid in creature.condition_immunities:
                skipped.add(cid)
                continue
            if creature.has_condition(cid):
                already.add(cid)
                # Уже есть → каскад implies не запускаем заново
                # (модификаторы уже наложены при первоначальном наложении).
                continue

            added = creature.apply_condition(cid)
            if added:
                applied.add(cid)
                # Раскручиваем implies этого состояния.
                cond = self._registry.get(cid)
                for implied in cond.implies:
                    if implied not in seen:
                        to_apply.append(implied)

        return ConditionApplyResult(
            applied=frozenset(applied),
            skipped_immune=frozenset(skipped),
            already_present=frozenset(already),
        )


__all__ = ["ConditionApplyResult", "ConditionService"]
