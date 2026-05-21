"""Состояния (Conditions) — плагины по решению Q23.

Базовый интерфейс — :class:`~dnd.domain.conditions.base.Condition`.
Реестр — :class:`~dnd.domain.conditions.registry.ConditionRegistry`
(module-level, регистрация явная через ``register_default_conditions``
в composition root).

Восемь базовых состояний MVP (см. DESIGN.md §5.2):
``Prone, Poisoned, Unconscious, Stunned, Paralyzed, Frightened,
Invisible, Incapacitated``.
"""
