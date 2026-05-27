# U — используемые предметы: дизайн

> ⚠️ **УСТАРЕЛО ПО ПОДХОДУ (пересмотрено в брейнсторме).** Отдельный
> `ItemEffectRegistry` заменён на **единый слой эффектов** (заклинания и предметы —
> одна логика, свиток ссылается на эффект-пакет; см. memory
> `project_unified_effects`). Баффы — на полном `GameClock`/`GameSession` (этап X0
> вытащен вперёд). LIGHT — в задел X (`project_light_vision_deferred`). Этот файл
> сохранён как история; актуальный U-спек будет переписан ПОСЛЕ X0 и ядра эффектов.

> «Оживляет» готовый инвентарь (этап O): зелья лечат, свитки кастуют, есть баффы
> и свет. Зеркалит систему заклинаний (реестр эффектов — доказанная
> расширяемость). Принципы: эффект — данные/реестр (не switch); domain не зависит
> от application; гасим техдолг честно.

## 1. Решения (зафиксированы с пользователем)

- **Объём:** все 4 эффекта — HEAL (зелье), CAST (свиток), BUFF (зелье-бафф),
  LIGHT (факел).
- **Экономика — данными предмета** (`economy` в `items.yaml`): зелье — бонусное
  действие (PHB-2024: выпить зелье = Bonus Action), свиток — действие. Дефолт —
  ACTION.
- **Свиток — без ограничений** (любой персонаж, любой свиток). Ограничения по
  классу/уровню/способности — **отложено до уровней/создания персонажа (W)**, см.
  memory `project_item_use_restrictions_deferred`.
- **Свиток (CAST) — вариант A:** вынести из `CastSpellAction` чистое ядро
  резолва заклинания (таргетинг + AoE + эффект, БЕЗ слота/экономики); и
  `CastSpellAction`, и `CastItemHandler` зовут его. Максимум переиспользования.
- Режим исполнения — спрошу перед планом.

## 2. Данные (domain)

### 2.1 `domain/values/item_use.py`

```python
class ItemUseEffect(StrEnum):
    HEAL = "heal"     # восстановить HP (NdM[+K])
    CAST = "cast"     # сотворить заклинание (свиток), без траты слота
    BUFF = "buff"     # модификаторы на пользователя (зелье силы и т.п.)
    LIGHT = "light"   # источник света (факел)

class ItemUseTarget(StrEnum):
    SELF = "self"     # на себя (зелье силы, факел)
    CREATURE = "creature"  # на существо в пределах 5 фт (зелье лечения союзнику)
    SPELL = "spell"   # таргетинг определяется заклинанием (свиток)

@dataclass(frozen=True, slots=True)
class ItemUseSpec:
    effect: ItemUseEffect
    economy: str = "action"        # сериализованный ActionEconomyCost
    consumed: bool = True          # расходуется ли (факел — False)
    target: ItemUseTarget = ItemUseTarget.SELF
    # HEAL
    heal_dice: str | None = None   # "2d4+2"
    # CAST
    spell_id: SpellId | None = None
    # BUFF (переиспользуем BuffSpec из spell.py)
    buffs: tuple[BuffSpec, ...] = ()
    # LIGHT
    light_radius_ft: int | None = None
```

Валидация в `__post_init__`: эффект требует свои поля (HEAL→`heal_dice`,
CAST→`spell_id`, BUFF→`buffs` непустой, LIGHT→`light_radius_ft`); `economy` ∈
{"action","bonus_action"}.

### 2.2 `Item.use`

Опциональное поле `use: ItemUseSpec | None = None` на `Item`
(`domain/values/item.py`). У большинства предметов None; у расходников/факела —
заполнено. Backward-compat: дефолт None, существующие предметы не меняются.

## 3. Исполнение (application)

### 3.1 `ItemEffectRegistry` (зеркало `SpellEffectRegistry`)

`application/engine/items/effect_registry.py`: `register(effect, handler)` /
`get(effect)` / `__contains__`. `ItemUseHandler` (Protocol):

```python
def apply(self, user: Creature, target: Creature, item: Item, ctx: TurnContext) -> bool: ...
```

`target` = существо-получатель (для SELF/SPELL = сам `user`; реальный таргетинг
свитка — внутри `CastItemHandler` по параметрам). Возвращает успех (для лога).

### 3.2 Хендлеры

- **HealItemHandler** (U1): бросок `heal_dice` → `target.heal(amount)`; публикует
  `HealingApplied(healer_id=user.id, target_id, amount, hp_after, hp_max)` —
  событие переиспользуется как есть (healer = пьющий/применяющий).
- **BuffItemHandler** (U1): применяет `buffs` через `ctx.modifier_applier.add(...)`
  с `source_id=f"item:{item.id}:{user.id}"` (БЕЗ концентрации). Своих событий не
  шлёт — факт использования логирует `ItemUsed` от `UseItemAction`. **Упрощение:**
  без истечения по времени — держится до конца сцены (чистится при EncounterEnded
  как прочие модификаторы; точная длительность — X0). Помечено в доках.
- **LightItemHandler** (U1): ставит на `user` флаг источника света (поле
  `light_radius_ft: int | None` на Creature, дефолт None). Факт — через `ItemUsed`.
  На видимость/LoS пока не влияет — **упрощение**, полноценная освещённость — X.

> Событие `ItemUsed` всегда публикует `UseItemAction` (единая точка лога);
> хендлеры шлют лишь свои доменные события (HEAL → `HealingApplied`).
- **CastItemHandler** (U2): резолвит заклинание `spell_id` и применяет через
  вынесенное ядро `resolve_and_apply_spell(...)` БЕЗ траты слота; цели — из
  `UseItemParams` (target_id/target_ids/target_point/direction). DC/атака — по
  `spell_save_dc()`/атаке пользователя (без ограничений).

### 3.3 `UseItemAction`

`application/engine/actions/use_item.py`. `__init__(item_repository,
effect_registry)`. Параметры:

```python
class UseItemParams(ActionParams):
    item_id: ItemId
    target_id: CreatureId | None = None        # CREATURE / одиночный спелл-таргет
    target_ids: tuple[CreatureId, ...] = ()     # свиток MULTI
    target_point: Square | None = None          # свиток AoE
    direction: Direction | None = None
```

- `economy_cost` (property) — номинально ACTION (для UI-бара); **реальная**
  экономика берётся из `item.use.economy` в `can_perform_against`/`execute`
  (так же движок и гейтит — через can_perform_against + execute).
- `can_perform_against`: предмет есть в `actor.inventory` (`contains`); у него
  `use is not None`; `ctx.can_spend(real_economy)`; цель валидна (CREATURE → в
  `participants` и ≤5 фт; SELF → actor; SPELL → проверки делегируются ядру
  резолва в execute, как у CastSpell).
- `execute`: `ctx.spend(real_economy)`; `target = actor` или из params;
  `ok = registry.get(use.effect).apply(actor, target, item, ctx)`; если
  `use.consumed` → `actor.inventory.remove_one(item_id)`; публикует
  `ItemUsed(actor_id, item_id, item_name, effect, target_id, consumed)`;
  `ActionOutcome(consumed=real_economy, ...)`.

### 3.4 Событие `ItemUsed`

`application/dto/engine_event.py`: `ItemUsed(EngineEvent)` — `actor_id`,
`item_id`, `item_name`, `effect: str`, `target_id: CreatureId | None`,
`consumed: bool`. Рендер в `EventPrinter` (рус. текст: «выпивает зелье…»,
«читает свиток…»).

### 3.5 Интент + диспатч + TUI

- `UseItemIntent(_IntentBase)`: `kind="use_item"`, `item_id`, target-поля (как
  CastSpellIntent). Добавить в `PlayerIntent` union + `__all__`.
- `GameRunner._do_use_item`: грузит предмет, строит `UseItemParams`,
  `can_perform_against` → `execute`/`_log_rejected`. Runner получает
  `item_repository`/`effect_registry` (через composition).
- TUI: пункт «использовать предмет» из инвентаря (ActionBar/инвентарный экран) —
  выбор предмета → (если нужен таргет) выбор цели существующими режимами
  (CREATURE → TargetMode; свиток → как CastSpell-таргетинг). Минимально:
  показать использование зелья/свитка из боя.

## 4. Рефакторинг для U2 (вариант A)

Из `CastSpellAction.execute` вынести чистую функцию (модуль
`application/engine/spells/resolve.py` или метод-helper):

```python
def resolve_and_apply_spell(
    caster: Creature, spell: Spell, params: SpellTargeting, ctx: TurnContext,
    *, effect_registry: SpellEffectRegistry, area_registry: AreaShapeRegistry,
) -> bool: ...
```

— содержит резолв целей (single/multi/AoE) + `effect_registry.get(spell.effect)
.apply(...)`. **Без** `consume_spell_slot` и **без** `ctx.spend`. `CastSpellAction
.execute` после валидации/слота/экономики зовёт ядро; `CastItemHandler` зовёт
ядро напрямую (слот не тратится, экономику уже потратил `UseItemAction`).
Регрессия: все тесты CastSpell должны остаться зелёными.

## 5. Контент (`items.yaml`)

- `healing_potion` (есть) → добавить `use: {effect: heal, economy: bonus_action,
  heal_dice: "2d4+2", target: creature}`.
- `potion_of_strength` (новый, BUFF): `use: {effect: buff, economy: bonus_action,
  buffs: [...] , target: self}`.
- `torch` (есть) → `use: {effect: light, economy: action, consumed: false,
  light_radius_ft: 20, target: self}`.
- `scroll_of_cure_wounds` / `scroll_of_fireball` (новые, CAST): `use: {effect:
  cast, economy: action, spell_id: <id>, target: spell}`.

Демо-PC/сцена получает зелье и свиток в инвентарь — чтобы использование видно в
игре.

## 6. Расширяемость

- Новый эффект предмета = член `ItemUseEffect` + хендлер в `ItemEffectRegistry`
  (open/closed, без правки `UseItemAction`).
- Новый предмет = строка в `items.yaml` (данные), без кода.
- Свиток переиспользует ВСЮ механику заклинаний через общее ядро резолва.

## 7. Инварианты

1. domain не импортирует application; `ItemUseSpec`/`ItemUseEffect` — данные в
   domain.
2. Эффект применяется через реестр; `UseItemAction` агностичен к конкретному
   эффекту.
3. Расходник списывается из инвентаря РОВНО при успешном применении (`consumed`);
   при отказе экономика не тратится.
4. Backward-compat: `Item.use=None`, `Creature.light_radius_ft=None` по умолчанию.
5. Свиток не тратит слот заклинаний пользователя.

## 8. Декомпозиция (план)

**U1 — фундамент + HEAL/BUFF/LIGHT:**
- U1-1 `ItemUseEffect`/`ItemUseTarget`/`ItemUseSpec` + валидация + тест.
- U1-2 `Item.use` + парсинг `use` в `YamlItemRepository`.
- U1-3 `ItemEffectRegistry` + протокол + defaults.
- U1-4 `ItemUsed`-событие + `UseItemAction` (экономика из данных, списание).
- U1-5 `HealItemHandler` + тест (зелье лечит).
- U1-6 `BuffItemHandler` (+ `Creature` без изменений; модификаторы) + тест.
- U1-7 `LightItemHandler` (+ `Creature.light_radius_ft`) + тест.
- U1-8 `UseItemIntent` + `GameRunner._do_use_item` + composition-проводка.
- U1-9 TUI: использование предмета из боя (минимально) + `EventPrinter`.
- U1-10 контент (зелья/факел) + демо-инвентарь + доки `ITEMS.md`/ROADMAP.

**U2 — CAST (свиток):**
- U2-1 вынести `resolve_and_apply_spell` из `CastSpellAction` (рефакторинг,
  регрессия зелёная).
- U2-2 `CastItemHandler` (свиток кастует без слота) + тест.
- U2-3 контент свитков + демо + e2e «выпил зелье / прочитал свиток».
- U2-4 доки + аудит-смок.

## 9. Отложено (W/X/далее)

- Ограничения использования свитка (класс/уровень/способность) — при уровнях/
  создании персонажа W (memory `project_item_use_restrictions_deferred`).
- Длительности баффов по времени — X0 (`GameClock`); сейчас бафф до конца сцены.
- Полноценная освещённость/видимость от света — X (исследование мира); сейчас
  LIGHT = флаг без влияния на LoS.
- Drop/Equip/Unequip-интенты (отмечены в O/Q) — вне U.
