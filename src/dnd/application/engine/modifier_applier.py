"""``ModifierApplier`` — сборщик и применитель модификаторов.

Спецификация — ``docs/MODIFIERS.md``. Здесь — MVP-реализация:

1. ``collect(owner_id, target_kind, purpose) -> list[Modifier]`` —
   находит все модификаторы из ``ModifierBag``, чьи ``owner_id`` и
   ``target_kind`` совпадают с запросом.
2. ``to_roll_adjustments(modifiers) -> RollAdjustments`` — сводит
   список в финальные параметры броска с учётом ``StackingPolicy``
   и книжного правила «advantage + disadvantage = обычный бросок»
   (стр. 11).

``ModifierBag`` — простой контейнер ``list[Modifier]``. В будущем
будет жить в ``GameState.modifiers``; пока ``ModifierApplier``
конструируется поверх любого источника модификаторов.

Полный набор условий (``ModifierCondition`` — Specification pattern)
из MODIFIERS.md §2.4 пока не реализован: все модификаторы считаются
``AlwaysApplies``. Когда понадобится первое условное правило
(например, «помеха только в воде», «преимущество против гуманоидов»),
здесь появится фильтр через предикаты.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from dnd.application.dto.ids import CreatureId
from dnd.application.dto.modifiers import (
    AdvantageEffect,
    DiceBonusEffect,
    DisadvantageEffect,
    Modifier,
    ModifierTargetKind,
    NumericBonusEffect,
    RollAdjustments,
    StackingPolicy,
)


class ModifierBag:
    """Контейнер активных модификаторов.

    Сейчас — простая обёртка над списком; в будущем заменится на поле
    ``GameState.modifiers`` без изменений в API ``ModifierApplier``.
    """

    def __init__(self, modifiers: Sequence[Modifier] = ()) -> None:
        self._modifiers: list[Modifier] = list(modifiers)

    def add(self, modifier: Modifier) -> None:
        self._modifiers.append(modifier)

    def remove_by_source(self, source_id: str) -> int:
        """Снять все модификаторы с этим ``source_id``. Возвращает количество снятых.

        Используется при истечении заклинания, удалении предмета,
        снятии состояния.
        """
        before = len(self._modifiers)
        self._modifiers = [m for m in self._modifiers if m.source_id != source_id]
        return before - len(self._modifiers)

    def all_for(self, owner_id: CreatureId) -> list[Modifier]:
        return [m for m in self._modifiers if m.owner_id == owner_id]

    def __len__(self) -> int:
        return len(self._modifiers)


class ModifierApplier:
    """Применяет модификаторы из :class:`ModifierBag` к конкретному броску.

    Бессостоятельный — поэтому потокобезопасный и тривиально мокаемый
    в тестах. Получает ``ModifierBag`` через конструктор; ничего больше
    не помнит.
    """

    def __init__(self, bag: ModifierBag) -> None:
        self._bag = bag

    def collect(
        self,
        *,
        owner_id: CreatureId,
        target_kind: ModifierTargetKind,
    ) -> list[Modifier]:
        """Найти все модификаторы, влияющие на этого существа и этот класс бросков."""
        return [m for m in self._bag.all_for(owner_id) if m.target_kind is target_kind]

    def to_roll_adjustments(self, modifiers: Sequence[Modifier]) -> RollAdjustments:
        """Свести список модификаторов в финальные параметры броска.

        Алгоритм:

        1. Группируем по ``stack_key``. Пустой ключ = уникальная группа
           (источник сам по себе, не конкурирует ни с чем).
        2. Внутри каждой группы применяем ``StackingPolicy``:
           - ``BEST_ONLY``: для NumericBonus — берём наибольший по
             значению; для DiceBonus/Advantage/Disadvantage — берём один
             любой (они и так не «складываются»).
           - ``STACK_ALL``: все модификаторы применяются.
           - ``REPLACE``: только первый (порядок добавления — приоритет).
        3. После свёртки внутри групп складываем NumericBonus всех групп
           в один итоговый, накапливаем extra_dice, объединяем
           advantage/disadvantage флаги.
        4. Книжное правило «advantage + disadvantage = обычный бросок»
           (стр. 11) применяется в самом конце: если оба True, обнуляем.

        Если несколько модификаторов одной группы имеют **разные** типы
        эффектов (например, NumericBonus и DiceBonus с одним stack_key) —
        они логически разные и группируются раздельно. Группировка идёт
        по паре ``(stack_key, type(effect))``.
        """
        # Группировка для stacking-разрешения:
        # * Пустой stack_key = модификатор сам по себе, не конкурирует
        #   ни с чем (каждый — своя группа). Это соответствует
        #   контракту в docs/MODIFIERS.md и docstring поля `stack_key`.
        # * Непустой stack_key + тип эффекта = совместная группа.
        #   Тип эффекта в ключе нужен, чтобы NumericBonus и DiceBonus
        #   с одинаковым stack_key (если такое случится) не мешали
        #   друг другу — они логически разные эффекты.
        groups: dict[object, list[Modifier]] = defaultdict(list)
        for m in modifiers:
            if m.stack_key == "":
                # Уникальная группа — используем id() модификатора как
                # ключ, чтобы каждый попал в свою группу.
                groups[id(m)].append(m)
            else:
                groups[(m.stack_key, type(m.effect))].append(m)

        numeric_total = 0
        extra_dice: list[str] = []
        advantage = False
        disadvantage = False
        sources: list[str] = []

        for group in groups.values():
            chosen = self._resolve_stacking(group)
            for m in chosen:
                sources.append(m.source_id)
                effect = m.effect
                if isinstance(effect, NumericBonusEffect):
                    numeric_total += effect.value
                elif isinstance(effect, DiceBonusEffect):
                    extra_dice.append(effect.dice)
                elif isinstance(effect, AdvantageEffect):
                    advantage = True
                elif isinstance(effect, DisadvantageEffect):
                    disadvantage = True

        # Книга стр. 11: оба флага гасят друг друга.
        if advantage and disadvantage:
            advantage = False
            disadvantage = False

        return RollAdjustments(
            numeric_bonus=numeric_total,
            extra_dice=tuple(extra_dice),
            advantage=advantage,
            disadvantage=disadvantage,
            sources=tuple(sources),
        )

    # --- внутреннее -----------------------------------------------------

    def _resolve_stacking(self, group: list[Modifier]) -> list[Modifier]:
        """Применить ``StackingPolicy`` к группе модификаторов одной группы.

        Полиси берётся из первого модификатора группы; считаем, что в
        одной группе политики совпадают (если нет — это баг контента,
        и `validate()` ContentService должен ловить заранее).
        """
        if not group:
            return []
        policy = group[0].stacking

        match policy:
            case StackingPolicy.STACK_ALL:
                return group
            case StackingPolicy.REPLACE:
                return [group[0]]
            case StackingPolicy.BEST_ONLY:
                return [self._best_in_group(group)]

    def _best_in_group(self, group: list[Modifier]) -> Modifier:
        """Выбрать «лучший» модификатор группы.

        Для NumericBonus — максимум по value. Для остальных типов
        порядок безразличен (берём первый), потому что советы вроде
        advantage/disadvantage/DiceBonus сами по себе не сравнимы
        «больше/меньше» — они либо есть, либо нет.
        """
        # NumericBonus специально — у нас может быть «+1 проф. бонус
        # vs +2 проф. бонус», нужно взять больший.
        numeric = [m for m in group if isinstance(m.effect, NumericBonusEffect)]
        if numeric:
            return max(numeric, key=lambda m: m.effect.value)  # type: ignore[union-attr]
        return group[0]


__all__ = ["ModifierApplier", "ModifierBag"]
