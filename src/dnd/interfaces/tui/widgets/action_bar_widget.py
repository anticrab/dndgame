"""ActionBarWidget — динамическая полоса хоткеев под картой.

``format_action_bar`` — чистая функция: тестируется без Textual,
вызывается из widget при каждом обновлении keymap. Сам widget — тонкая
обёртка над :class:`Static`, BattleScreen зовёт :meth:`set_keymap` после
смены актора (другой ``Creature.keybindings``) или регистрации новой
ability.

Footer от Textual мы оставляем для генерических биндингов (q/quit и
zoom), а ability-полоса живёт отдельно — её содержимое плавающее, а
Footer выводит фиксированный список из ``BINDINGS``-классаттрибута.
"""

from __future__ import annotations

from textual.widgets import Static

from dnd.application.abilities.ability import Ability


def format_action_bar(keymap: dict[str, Ability]) -> str:
    """Формат: ``'[a] Attack  [d] Dodge  …'``, отсортировано по hotkey'у.

    Сортировка — для предсказуемости (тест и визуально); без неё порядок
    зависел бы от insertion-order словаря и менялся при каждом
    переподключении ability.
    """
    if not keymap:
        return ""
    parts = [f"[{k}] {a.name}" for k, a in sorted(keymap.items())]
    return "  ".join(parts)


class ActionBarWidget(Static):
    DEFAULT_CSS = "ActionBarWidget { height: 1; padding: 0 1; }"

    def set_keymap(self, keymap: dict[str, Ability]) -> None:
        self.update(format_action_bar(keymap))


__all__ = ["ActionBarWidget", "format_action_bar"]
