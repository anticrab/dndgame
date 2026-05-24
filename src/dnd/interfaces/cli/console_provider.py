"""ConsoleIntentProvider — интерактивный источник намерений через
``questionary``.

UX:

* В начале хода показываем меню действий: Attack / Move / Dodge /
  Dash / Disengage / End Turn.
* Для Attack — спрашиваем цель из списка живых врагов в reach
  (или предупреждаем, что нет валидных целей).
* Для Move — спрашиваем координату цели; путь строится прямо к ней
  (chebyshev).

Минимальный CLI. Полноценные подсказки/предпросмотр кубов/превью урона
— пост-MVP.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dnd.application.dto.action import Allowed
from dnd.application.dto.ids import CreatureId, ObjectId
from dnd.application.dto.player_intent import (
    AttackIntent,
    BreakIntent,
    DashIntent,
    DisengageIntent,
    DodgeIntent,
    EndTurnIntent,
    InteractIntent,
    MoveIntent,
    PickupIntent,
    PlayerIntent,
)
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.interact import InteractKind
from dnd.application.engine.actions.move_path import find_walkable_path
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.turn_context import TurnContext
from dnd.application.inventory.loot_helpers import parse_loot
from dnd.application.ports.item_repository import ItemRepository
from dnd.domain.entities.creature import Creature
from dnd.domain.values.faction import Faction
from dnd.domain.values.item import ItemId
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square

_ACTION_CHOICES = [
    "Attack",
    "Move",
    "Dodge",
    "Dash",
    "Disengage",
    "Interact",
    "Break",
    "Pickup",
    "End turn",
]


# Защита от бесконечной рекурсии в re-prompt'ах. Аудит 15 CL-UX001:
# если игрок упорно выбирает «Attack без целей», после N циклов
# принудительно завершаем ход (последняя соломинка против бага UI).
_MAX_REPROMPTS = 5


@dataclass(slots=True)
class ConsoleIntentProvider:
    """Источник намерений через интерактивные prompt'ы.

    Поля ``prompt_*`` — слоты для подмены prompt'ов в тестах:
    функции принимают сообщение и список выборов, возвращают строку.
    В рантайме используют ``questionary`` (lazy import).
    """

    prompt_action: Callable[[str, list[str]], str] | None = None
    prompt_choice: Callable[[str, list[str]], str] | None = None
    prompt_text: Callable[[str], str] | None = None
    notify: Callable[[str], None] | None = None
    item_repository: ItemRepository | None = None
    """Каталог Item-ов для Pickup-меню (показывает name/qty вместо
    голых item_id). Если None — пункт 'Pickup' доступен, но названия
    будут сырые. Передаётся из CLI app.py (build_default_item_repo)."""

    def next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent:
        return self._next_intent(actor, ctx, encounter, depth=0)

    def _next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
        depth: int,
    ) -> PlayerIntent:
        if depth >= _MAX_REPROMPTS:
            # Защита от циклической ошибки: «Attack без целей» снова и
            # снова. Завершаем ход, не теряем сессию.
            self._notify_user(
                "Too many invalid attempts — ending turn."
            )
            return EndTurnIntent()

        choice = self._select(
            f"[{actor.name}] choose action:", _ACTION_CHOICES
        )
        match choice:
            case "End turn":
                return EndTurnIntent()
            case "Dodge":
                return DodgeIntent()
            case "Dash":
                return DashIntent()
            case "Disengage":
                return DisengageIntent()
            case "Attack":
                return self._build_attack_intent(actor, ctx, encounter, depth)
            case "Move":
                return self._build_move_intent(actor, ctx, encounter, depth)
            case "Interact":
                return self._build_object_intent(
                    actor, ctx, encounter, depth, kind="interact"
                )
            case "Break":
                return self._build_object_intent(
                    actor, ctx, encounter, depth, kind="break"
                )
            case "Pickup":
                return self._build_pickup_intent(actor, ctx, encounter, depth)
        return EndTurnIntent()

    # --- private -----------------------------------------------------

    def _select(self, message: str, choices: list[str]) -> str:
        if self.prompt_action is not None:
            return self.prompt_action(message, choices)
        import questionary

        result = questionary.select(message, choices=choices).ask()
        # questionary.ask() возвращает None при Ctrl+C — трактуем как End turn.
        return result if result is not None else "End turn"

    def _select_choice(self, message: str, choices: list[str]) -> str:
        if self.prompt_choice is not None:
            return self.prompt_choice(message, choices)
        import questionary

        result = questionary.select(message, choices=choices).ask()
        return result if result is not None else choices[0]

    def _ask_text(self, message: str) -> str:
        if self.prompt_text is not None:
            return self.prompt_text(message)
        import questionary

        result = questionary.text(message).ask()
        return result if result is not None else ""

    def _notify_user(self, message: str) -> None:
        """Сообщение игроку (warning / hint). Не теряет ход."""
        if self.notify is not None:
            self.notify(message)

    def _build_attack_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
        depth: int,
    ) -> PlayerIntent:
        actor_faction = encounter.factions[actor.id]
        targets = _list_reachable_hostiles(actor, ctx, encounter, actor_faction)
        if not targets:
            # Аудит 15 CL-UX001: не теряем ход тихо — сообщаем и снова
            # показываем меню.
            self._notify_user("No reachable targets — choose another action.")
            return self._next_intent(actor, ctx, encounter, depth + 1)
        labels = [
            f"{cid} ({encounter.participants[cid].name}, HP {encounter.participants[cid].hit_points.current}/{encounter.participants[cid].hit_points.maximum})"
            for cid in targets
        ]
        picked = self._select_choice("Target:", labels)
        # Берём индекс выбранной метки → CreatureId.
        idx = labels.index(picked)
        return AttackIntent(target_id=targets[idx])

    def _build_move_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
        depth: int,
    ) -> PlayerIntent:
        raw = self._ask_text(
            f"[{actor.name}] move to (x,y), e.g. 2,3 — current "
            f"{ctx.battlefield.position_of(actor.id)}:"
        )
        try:
            x_str, y_str = raw.split(",", 1)
            target = Square(int(x_str.strip()), int(y_str.strip()))
        except (ValueError, AttributeError):
            # Аудит 15 CL-UX001: невалидный ввод — re-prompt, не end turn.
            self._notify_user(
                f"Cannot parse coordinates from {raw!r}. Use format: x,y"
            )
            return self._next_intent(actor, ctx, encounter, depth + 1)
        if not ctx.battlefield.in_bounds(target):
            self._notify_user(
                f"{target} is out of bounds — pick coordinates within "
                f"{ctx.battlefield.width}x{ctx.battlefield.height}."
            )
            return self._next_intent(actor, ctx, encounter, depth + 1)
        start = ctx.battlefield.position_of(actor.id)
        # Тот же helper, что и TUI: A* с учётом стен и difficult terrain.
        # Чтобы CLI и TUI выбирали одну клетку и шли одинаковым путём,
        # — единый источник правды. is_alive пропускает трупы.
        def _alive(cid: CreatureId) -> bool:
            cr = encounter.participants.get(cid)
            return True if cr is None else cr.is_alive
        path = find_walkable_path(
            ctx.battlefield, start, target, is_alive=_alive
        )
        if path is None:
            self._notify_user(
                f"{target} is unreachable (стена / занято / отрезано)."
            )
            return self._next_intent(actor, ctx, encounter, depth + 1)
        if not path:
            self._notify_user("Already at the target square.")
            return self._next_intent(actor, ctx, encounter, depth + 1)
        return MoveIntent(path=path)

    def _build_object_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
        depth: int,
        *,
        kind: str,
    ) -> PlayerIntent:
        """Собрать InteractIntent или BreakIntent.

        ``kind=="interact"`` фильтрует любые объекты в reach (5 ft) и
        предлагает выбрать один; ``kind=="break"`` отбирает только те,
        у которых есть hp в state — остальные ломать нечем
        (window/door тоже сюда подходят, оба имеют hp).
        """
        bf = ctx.battlefield
        pos = bf.position_of(actor.id)
        candidates: list[tuple[ObjectId, str]] = []
        for sq in pos.chebyshev_disk(1):
            if not bf.in_bounds(sq):
                continue
            for obj in bf.objects_at(sq):
                if kind == "break" and "hp" not in obj.state:
                    continue
                label = f"{obj.id} ({obj.kind}) at ({sq.x},{sq.y})"
                candidates.append((ObjectId(str(obj.id)), label))
        if not candidates:
            verb = "interactable" if kind == "interact" else "breakable"
            self._notify_user(f"No {verb} objects in reach.")
            return self._next_intent(actor, ctx, encounter, depth + 1)
        labels = [label for _, label in candidates]
        picked = self._select_choice(
            f"{kind.title()} target:", labels
        )
        idx = labels.index(picked)
        obj_id, _ = candidates[idx]
        if kind == "interact":
            return InteractIntent(
                target_object_id=obj_id,
                interact_kind=InteractKind.OPEN,
            )
        return BreakIntent(target_object_id=obj_id)

    def _build_pickup_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
        depth: int,
    ) -> PlayerIntent:
        """Pickup из сундука в reach: 3 prompt'а (chest → item → qty).

        Если ``item_repository=None`` — пункт ещё работает, но названия
        items будут голыми id (Pickup_intent доходит до GameRunner и
        там резолвится через свой repo)."""
        bf = ctx.battlefield
        pos = bf.position_of(actor.id)
        # Сундуки в reach 5 ft (chebyshev 1).
        chests: list[tuple[ObjectId, str]] = []
        for sq in pos.chebyshev_disk(1):
            if not bf.in_bounds(sq):
                continue
            for obj in bf.objects_at(sq):
                if obj.kind is ObjectKind.CHEST and not obj.state.get("locked"):
                    chests.append(
                        (ObjectId(str(obj.id)), f"{obj.id} at ({sq.x},{sq.y})")
                    )
        if not chests:
            self._notify_user("No open chests in reach.")
            return self._next_intent(actor, ctx, encounter, depth + 1)

        # Шаг 1: выбираем chest.
        chest_labels = [label for _, label in chests]
        picked = self._select_choice("Pickup from:", chest_labels)
        chest_id, _ = chests[chest_labels.index(picked)]
        chest = bf.object_at(chest_id)

        # Шаг 2: выбираем item. Без repository — голые id; с ним —
        # name + qty в человеческой форме.
        raw_contents = chest.state.get("contents")
        item_labels: list[str] = []
        item_ids: list[ItemId] = []
        if self.item_repository is not None:
            for stack in parse_loot(raw_contents, self.item_repository):
                item_ids.append(stack.item.id)
                item_labels.append(
                    f"{stack.item.name} ×{stack.qty} ({stack.item.id})"
                )
        else:
            # Fallback: только сырой id, без resolved-имени.
            for entry in raw_contents or []:
                if isinstance(entry, dict):
                    item_ids.append(ItemId(str(entry["item_id"])))
                    item_labels.append(
                        f"{entry['item_id']} ×{entry.get('qty', 1)}"
                    )
                elif isinstance(entry, str):
                    item_ids.append(ItemId(entry))
                    item_labels.append(entry)
        if not item_labels:
            self._notify_user(f"{chest_id} is empty.")
            return self._next_intent(actor, ctx, encounter, depth + 1)

        picked_item = self._select_choice("Pickup what:", item_labels)
        item_id = item_ids[item_labels.index(picked_item)]

        # Шаг 3: qty (None = всё). Промт текст, если пусто/'all' → None.
        raw_qty = self._ask_text(
            f"Pickup how many of {item_id}? (empty / 'all' = all):"
        )
        qty: int | None
        if not raw_qty or raw_qty.strip().lower() == "all":
            qty = None
        else:
            try:
                qty = int(raw_qty.strip())
            except ValueError:
                self._notify_user(
                    f"Cannot parse qty {raw_qty!r}, picking up all."
                )
                qty = None

        return PickupIntent(
            target_object_id=chest_id, item_id=item_id, qty=qty,
        )


def _list_reachable_hostiles(
    actor: Creature,
    ctx: TurnContext,
    encounter: Encounter,
    actor_faction: Faction,
) -> list[CreatureId]:
    """Список ID живых врагов, по которым ``actor`` может атаковать
    сейчас (учёт LoS, cover, range — через can_perform_against)."""
    if actor.equipped_weapon is None:
        return []
    attack = AttackAction()
    result: list[CreatureId] = []
    for cid, cr in encounter.participants.items():
        if cid == actor.id or not cr.is_alive:
            continue
        if encounter.factions[cid] is actor_faction:
            continue
        if encounter.factions[cid] is Faction.NEUTRAL:
            continue
        try:
            params = weapon_attack_params(actor, cid)
        except ValueError:
            continue
        if isinstance(attack.can_perform_against(actor, params, ctx), Allowed):
            result.append(cid)
    return result


__all__ = ["ConsoleIntentProvider"]
