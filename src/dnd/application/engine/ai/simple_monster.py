"""SimpleMonsterAI — минималистичная политика хода монстра.

Stateless: одна функция ``take_monster_turn(actor, ctx, encounter)``.
Алгоритм (на MVP):

1. Найти ближайшее живое существо враждебной фракции (PARTY если actor
   из MONSTERS, MONSTERS если actor из PARTY).
2. Если в reach equipped_weapon → атака; иначе попытаться сократить
   дистанцию через MoveAction (прямая chebyshev-пошаговая линия) и
   атаковать, если дошли.
3. Если у actor нет equipped_weapon или нет видимых врагов — пропустить
   ход (Dodge как самозащита).

Не моделирует:

* грамотный выбор цели (минимум HP, дальняя угроза);
* отступление и kiting;
* Help/Dash/Disengage;
* spell casting и features.

Цель — иметь работающий смок-сценарий «бой до конца». Полная AI —
позднее, через сменную ReactionPolicy/TurnPolicy.
"""

from __future__ import annotations

from collections.abc import Callable

from dnd.application.dto.action import Allowed, NoParams
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.move import MoveAction, MoveParams
from dnd.application.engine.actions.stances import DodgeAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square

IsHostile = Callable[[CreatureId], bool]


def take_monster_turn(
    actor: Creature, ctx: TurnContext, *, is_hostile: IsHostile
) -> None:
    """Сделать ход за монстра.

    ``is_hostile(other_id) -> bool`` — предикат «другое existo враг».
    Composition root собирает его поверх Encounter.factions; AI не
    зависит от Faction-enum и от структуры Encounter напрямую.
    Аудит 14 VS-AI001 — заменил бесполезный ``hostile_factions`` на
    рабочий callable.

    Side effects: вызывает Action.execute, мутирует Battlefield,
    публикует события.
    """
    if not actor.is_alive or actor.is_at_zero_hp:
        return  # ничего не делаем

    target = _find_nearest_hostile(actor, ctx, is_hostile)
    if target is None:
        _try_dodge(actor, ctx)
        return

    weapon = actor.equipped_weapon
    if weapon is None:
        _try_dodge(actor, ctx)
        return

    attack = AttackAction()
    # 1) Пробуем атаковать с текущей позиции.
    params = weapon_attack_params(actor, target.id)
    if isinstance(attack.can_perform_against(actor, params, ctx), Allowed):
        attack.execute(actor, params, ctx)
        return

    # 2) Не дотягиваемся — попробуем подойти на расстояние reach.
    path = _path_towards(actor, target, ctx, target_distance_ft=weapon.range_ft)
    if path:
        MoveAction().execute(actor, MoveParams(path=tuple(path)), ctx)
        # 3) После движения — повторная попытка атаки.
        params = weapon_attack_params(actor, target.id)
        if isinstance(attack.can_perform_against(actor, params, ctx), Allowed):
            attack.execute(actor, params, ctx)
        return

    # Если ничего из вышеперечисленного не сработало — Dodge.
    _try_dodge(actor, ctx)


def _try_dodge(actor: Creature, ctx: TurnContext) -> None:
    dodge = DodgeAction()
    if isinstance(dodge.can_perform(actor, ctx), Allowed):
        dodge.execute(actor, NoParams(), ctx)


def _find_nearest_hostile(
    actor: Creature, ctx: TurnContext, is_hostile: IsHostile
) -> Creature | None:
    """Ближайший живой враг (chebyshev-distance) в зоне видимости LoS.

    Фильтрует кандидатов через ``is_hostile`` — composition root
    знает Encounter.factions и собирает предикат заранее.
    """
    bf = ctx.battlefield
    if not bf.has_creature(actor.id):
        return None
    actor_pos = bf.position_of(actor.id)

    candidates: list[tuple[int, Creature]] = []
    for cid, cr in ctx.participants.items():
        if cid == actor.id or not cr.is_alive or cr.is_at_zero_hp:
            continue
        if not bf.has_creature(cid):
            continue
        if not is_hostile(cid):
            continue
        cr_pos = bf.position_of(cid)
        if not bf.line_of_sight(actor_pos, cr_pos):
            continue
        dist = actor_pos.distance_to(cr_pos)
        candidates.append((dist, cr))

    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def _path_towards(
    actor: Creature,
    target: Creature,
    ctx: TurnContext,
    *,
    target_distance_ft: int,
) -> list[Square]:
    """Простейший «шаг к цели по диагонали»: каждый шаг — клетка,
    сближающая по chebyshev.

    Возвращает путь (без стартовой клетки), такой что:
    * каждый шаг — соседняя клетка;
    * каждая клетка in_bounds и passable;
    * остаётся в пределах movement_remaining_ft (с учётом difficult);
    * останавливаемся, когда дошли в reach (chebyshev <= target_distance_ft/5).

    Препятствия (другие existo на клетке): на MVP игнорируем — если
    клетка occupied, MoveAction.move_creature всё равно положит туда
    несколько (Q1).
    """
    bf = ctx.battlefield
    start = bf.position_of(actor.id)
    target_pos = bf.position_of(target.id)
    target_squares = max(1, target_distance_ft // 5)

    path: list[Square] = []
    current = start
    remaining_ft = ctx.movement_remaining_ft

    while current.distance_to(target_pos) > target_squares:
        dx = _sign(target_pos.x - current.x)
        dy = _sign(target_pos.y - current.y)
        if dx == 0 and dy == 0:
            break
        step = Square(current.x + dx, current.y + dy)
        if not bf.in_bounds(step):
            break
        terrain = bf.terrain_at(step)
        if not terrain.passable:
            break
        cost = 10 if terrain.difficult else 5
        if cost > remaining_ft:
            break
        path.append(step)
        remaining_ft -= cost
        current = step

    return path


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def is_hostile_from_factions(
    actor_id: CreatureId, factions: dict[CreatureId, Faction]
) -> IsHostile:
    """Утилита: predicate «враждебен ли" по карте фракций.

    Все participants, чья фракция не совпадает с фракцией actor'а и
    не NEUTRAL, считаются врагами. NEUTRAL и same-faction —
    дружественны/нейтральны.

    Composition root / тесты собирают этот предикат и передают в
    ``take_monster_turn(..., is_hostile=...)``.
    """
    actor_faction = factions.get(actor_id)

    def predicate(other_id: CreatureId) -> bool:
        if other_id == actor_id:
            return False
        other_faction = factions.get(other_id)
        if other_faction is None or other_faction is Faction.NEUTRAL:
            return False
        return other_faction is not actor_faction

    return predicate


__all__ = ["IsHostile", "is_hostile_from_factions", "take_monster_turn"]
