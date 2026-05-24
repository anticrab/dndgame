# Inventory & Loot

> Этап O. Domain + application + интеграция с TUI/CLI: `Item`,
> `Inventory`, `PickupAction`, лут из сундуков.

## Концепция

Инвентарь — список **штабелируемых предметов** (`ItemStack`).
Каждый предмет описывается frozen value-object'ом `Item` (id, name,
kind, weight, optional flag `stackable`). Сами стаки лежат в
**mutable** `Inventory`-сущности на `Creature.inventory` и подчиняются
slot- / weight-лимитам.

Каталог items (`Item`-описания) живёт в YAML — `data/content/items.yaml`,
загружается через :class:`YamlItemRepository`. Сундуки в картах
ссылаются на items по id (`{item_id: gold_piece, qty: 25}`), полные
описания добавляет загрузчик. Это позволяет редактировать карты, не
дублируя weight/name каждого предмета.

## Сущности

```
Item (frozen)                       ItemStack (mutable qty)
├── id: ItemId                      ├── item: Item
├── name: str                       └── qty: int (1 для non-stackable)
├── kind: ItemKind
├── weight_lb: float
├── stackable: bool
└── description: str

Inventory (mutable)                 Creature.inventory: Inventory
├── stacks: list[ItemStack]
├── slot_limit: int | None          ItemRepository (Port)
├── weight_limit_lb: float | None   ├── list_ids() -> tuple[ItemId, ...]
├── add(item, qty) -> overflow      ├── load(id) -> Item
├── remove_one(id) -> Item | None   └── contains(id) -> bool
├── find_by_id, contains
├── total_weight_lb
└── slot_count
```

`ItemKind` (5 категорий): `WEAPON / ARMOR / CONSUMABLE / QUEST / MISC`.

## Slot- и weight-логика

* **stackable** items (валюта, зелья, факелы) занимают **один слот**,
  даже при больших qty. Пополнение через `inv.add(item, qty)` находит
  существующий стак и инкрементит qty.
* **non-stackable** items (оружие, броня) — отдельный слот на каждую
  единицу.
* `slot_limit` блокирует **новые** слоты, но не пополнение
  существующего стака — даже при забитом рюкзаке можно докинуть монет
  в уже-открытый кошель.
* `weight_limit_lb` ограничивает суммарный вес; `add(...)` возвращает
  **overflow** — сколько не влезло (UI показывает «overflow 6 потерян»).
* `remove_one(id)` — атомарная единица: декрементит qty для stackable
  (qty=0 удаляет слот целиком), убирает один стак для non-stackable.

## Loot из сундуков

`Chest.state["contents"]` хранит сырой YAML — либо canonical-формат:

```yaml
contents:
  - item_id: gold_piece
    qty: 25
  - item_id: healing_potion
    qty: 1
```

… либо **legacy** список строк (`["gold", "gold", "longsword"]` — старые
warehouse.yaml). `parse_loot(raw, item_repo)` принимает оба формата и
возвращает `tuple[ItemStack, ...]`. На сохранении (`dump_loot_entries`)
пишется только canonical. Битый item_id в карте → `KeyError` при
загрузке (fail-fast).

## Pickup-сценарий

```
Player → press 'l' (TUI) / выбрать "Pickup" (CLI)
      → InventoryScreen / questionary меню
      → выбрать chest и item
      → PickupIntent(chest_id, item_id, qty=None)
      → GameRunner._do_pickup → PickupAction.execute
        ├── parse_loot(chest.state['contents'], item_repo)
        ├── inv.add(stack.item, qty)
        ├── update chest.state['contents'] через dump_loot_entries
        └── publish ItemPickedUp event
```

Pickup — **free object interaction** (1/ход, как Interact). Reach
5 ft. Forbidden: NO_ECONOMY_LEFT / OUT_OF_RANGE / locked chest /
wrong kind / no such item_id / inventory full (success=False, ход
не съедается).

## Composition

| Layer | Класс | Где собирается |
|-------|-------|----------------|
| domain | `Item`, `ItemStack`, `Inventory`, `Creature.inventory` | runtime |
| application | `PickupAction`, `PickupIntent`, events | через `GameRunner(item_repository=...)` |
| application/ports | `ItemRepository` (Protocol) | — |
| infrastructure | `YamlItemRepository(items_file)` | `dnd play` → `data/content/items.yaml` |
| TUI | `InventoryScreen`, hotkey 'l' | `TuiApp(item_repository=...)` |
| CLI | пункт меню «Pickup» | `ConsoleIntentProvider(item_repository=...)` |

`ItemRepository=None` допустимо — `PickupAction` тогда не вызывается
(intent отклоняется с понятной причиной), а UI работает с голыми id.

## Что ещё в плане

* **O-7 Лут трупов** (отложен до этапа Q): убитое существо остаётся
  лежать на карте `%`, его `Creature.inventory` доступен через
  Interact/Loot. Сейчас inventory остаётся в памяти, но UI к нему
  ещё не подключён — экран лута пока только для chest'ов.
* **Drop / Equip / Unequip** intents (O-extra): сейчас pickup
  односторонний. Drop требует поля «куда» (в клетку под актором →
  создавать на лету chest'ы / pile'ы), equip — переписать слой
  `Creature.equipped_weapon` так, чтобы он ссылался на `Item.id`
  из inventory вместо отдельной `WeaponProfile`.
* **Encumbrance penalties**: PHB-2024 `Carrying Capacity =
  STR × 15 lb`; при превышении — Speed -10 ft и disadvantage на
  STR/DEX/CON checks. Сейчас weight_limit_lb опционален без
  механического эффекта.

См. также:
* `docs/ROADMAP.md` §8 — этап O в общей картине;
* `docs/ACTIONS.md` — Pickup рядом с Interact (FREE economy);
* `docs/superpowers/specs/...` — детальный спек, когда сделаем
  brainstorming для O-7/R/Q.
