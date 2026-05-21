"""Хиты: текущие, максимум, временные.

Книга 2024, «Урон и лечение» (стр. 26):

* **Текущие хиты** — от 0 до **максимума** (от ран до полного здоровья).
* **Максимум хитов** определяется классом и Телосложением, а также
  эффектами вроде «высасывания жизни» (могут временно понижать максимум).
* **Временные хиты** — буфер **перед** текущими; не складываются
  между собой (новые временные хиты заменяют старые, если новые >);
  лечение их **не** восстанавливает; не повышают «текущие хиты»
  относительно максимума.
* **Получение урона**: сначала вычитается из временных хитов, потом из
  текущих. Лишний урон по временным **переносится** на текущие.
* **Лечение**: восстанавливает текущие хиты до максимума, не выше.
* При снижении максимума ниже текущих — текущие тоже снижаются.

Этот модуль — **value-object** (иммутабельный). Любая операция
возвращает **новый** объект `HitPoints` — это упрощает откат, replay
и сериализацию.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HitPoints:
    """Структура хитов существа.

    Инварианты:

    * ``0 <= current <= maximum``
    * ``0 <= temporary``
    * ``maximum >= 0`` (`0` означает существо мертво или некропост — но
      это редкий случай; обычно `maximum >= 1`).
    """

    current: int
    maximum: int
    temporary: int = 0

    def __post_init__(self) -> None:
        if self.maximum < 0:
            raise ValueError(f"max HP must be >= 0, got {self.maximum}")
        if self.temporary < 0:
            raise ValueError(f"temp HP must be >= 0, got {self.temporary}")
        if not 0 <= self.current <= self.maximum:
            raise ValueError(f"current HP {self.current} is out of range 0..{self.maximum}")

    # --- состояния ---------------------------------------------------------

    @property
    def is_unconscious(self) -> bool:
        """Существо в 0 HP считается бессознательным (см. книгу, стр. 27)."""
        return self.current == 0

    @property
    def is_at_full(self) -> bool:
        return self.current == self.maximum

    # --- операции ---------------------------------------------------------

    def take_damage(self, amount: int) -> HitPoints:
        """Получить ``amount`` урона.

        Сначала вычитается из временных хитов, потом из текущих. Лишний
        урон от временных хитов переносится на текущие. Текущие не могут
        стать меньше 0 (свыше — это «огромный урон», но управляется
        отдельным правилом в `Creature`, а не в этом VO).
        """
        if amount < 0:
            raise ValueError(f"damage must be >= 0, got {amount}")
        if amount == 0:
            return self
        if self.temporary >= amount:
            return HitPoints(
                current=self.current,
                maximum=self.maximum,
                temporary=self.temporary - amount,
            )
        remainder = amount - self.temporary
        new_current = max(0, self.current - remainder)
        return HitPoints(current=new_current, maximum=self.maximum, temporary=0)

    def heal(self, amount: int) -> HitPoints:
        """Восстановить ``amount`` хитов. Не выше максимума. Временные хиты не трогает."""
        if amount < 0:
            raise ValueError(f"heal must be >= 0, got {amount}")
        if amount == 0 or self.is_at_full:
            return HitPoints(current=self.current, maximum=self.maximum, temporary=self.temporary)
        return HitPoints(
            current=min(self.maximum, self.current + amount),
            maximum=self.maximum,
            temporary=self.temporary,
        )

    def with_temporary(self, amount: int) -> HitPoints:
        """Получить временные хиты. Не складываются — берётся **больший** буфер.

        Книга: «если у вас уже есть временные хиты, и вы получаете новые,
        вы можете оставить старые или взять новые, но не сложить».
        Реализуем выбор автоматически: берём больший — это безопасный
        дефолт (игрок не теряет ничего). В будущем можно сделать
        `prefer_new`-параметр, если архитектор захочет.
        """
        if amount < 0:
            raise ValueError(f"temp HP must be >= 0, got {amount}")
        return HitPoints(
            current=self.current,
            maximum=self.maximum,
            temporary=max(self.temporary, amount),
        )

    def with_maximum(self, new_maximum: int) -> HitPoints:
        """Установить новый максимум. Если текущие выше — снижаются."""
        if new_maximum < 0:
            raise ValueError(f"max HP must be >= 0, got {new_maximum}")
        return HitPoints(
            current=min(self.current, new_maximum),
            maximum=new_maximum,
            temporary=self.temporary,
        )

    def restored_to_full(self) -> HitPoints:
        """Полностью восстановить (например, после продолжительного отдыха).

        Восстанавливает current до maximum. Временные хиты **снимаются**
        (книга: «при продолжительном отдыхе временные хиты сбрасываются»).
        """
        return HitPoints(current=self.maximum, maximum=self.maximum, temporary=0)
