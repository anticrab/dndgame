# ITEMS — используемые предметы (этап U)

Зелья и свитки в проекте — обвязка над **единым каталогом заклинаний**. Сам
эффект (лечение, бафф, fireball-AoE) описан **один раз** в `data/content/
spells.yaml`; предмет ссылается на него по `effect_id`. Никаких параллельных
«item-эффектов» — растущая часть домена закрыта open/closed: новый эффект
добавляется хендлером в `SpellEffectRegistry`, а не правкой контейнера.

См. также: `docs/SPELLS.md` (хендлеры эффектов), `docs/INVENTORY.md`
(стаки/слоты/вес), `docs/MODIFIERS.md` (баффы → ModifierBag), `docs/ROADMAP.md`
(почему U был приоритет-1).

## 1. Картина: предмет → эффект-пакет → ядро резолва

```
items.yaml ──► Item.use: ItemUseSpec ──► spells.yaml(effect_id)
                                            │
UseItemAction ─────► resolve_and_apply_spell ─► SpellEffectRegistry(handler)
                              ▲                        │
                              │                        ▼
                          SpellPower            ctx.modifier_applier /
                       (Сл/атака/мод)            ctx.event_bus.publish
```

* `Item.use` (`ItemUseSpec`) — **обвязка доставки**: что за эффект, какая
  экономика тратится, расходник ли это, является ли свитком.
* `SpellPower` — **источник чисел**: Сл спасброска, бонус атаки, прибавка к
  HEAL. Развязывает «силу» эффекта от источника:
  * `from_caster(caster)` — заклинание волшебника;
  * `scroll(spell_level)` — фикс по таблице свитков PHB-2024;
  * `potion()` — нулевой мод (зелье лечит ровно по кости).
* `resolve_and_apply_spell` — **чистое slotless-ядро** (резолв целей + вызов
  хендлера). Вынесено из `CastSpellAction`, поэтому одинаково исполняет каст
  волшебника и эффект свитка/зелья.
* `UseItemAction` — действие игрока: проверки (наличие в инвентаре, поддержка
  эффекта, цель/range, экономика), затем вызов ядра + публикация `ItemUsed` +
  списание расходника.

## 2. `ItemUseSpec` — обвязка доставки

`src/dnd/domain/values/item_use.py`. Frozen VO, лежит в **domain** (без
зависимостей от application: `economy` хранится строкой, конвертацию в
`ActionEconomyCost` делает `UseItemAction`).

| Поле | Тип | Назначение |
|------|-----|-----------|
| `effect_id` | `SpellId` | id записи эффект-пакета в `spells.yaml` |
| `economy` | `"action"` / `"bonus_action"` | сколько тратит действие |
| `consumed` | `bool` | списать ли единицу из инвентаря (по умолчанию True) |
| `is_scroll` | `bool` | `True` → `SpellPower.scroll(level)`; `False` → `potion()` |

## 3. `SpellPower` — «сила» эффекта (PHB-2024 таблица свитков)

`src/dnd/domain/values/spell_power.py`. Хендлеры эффектов читают `power.save_dc`,
`power.attack_bonus`, `power.ability_mod` — поэтому **один** хендлер обслуживает
кастера, свиток и зелье без переключателей.

Фикс-таблица свитка по уровню заклинания (PHB-2024):

| Уровень | Сл | Атака |
|---------|-----|-------|
| 0–2 | 13 | +5 |
| 3–4 | 15 | +7 |
| 5–6 | 17 | +9 |
| 7–8 | 18 | +10 |
| 9   | 19 | +11 |

Для `from_caster` у не-кастера (нет `spellcasting_ability`) — нули.

## 4. Хендлеры эффектов — что доступно (U)

Поддержаны полностью в этапе U:

* **HEAL** — `2d4+2`, `1d8`, `2d8+потолок`, … (heal_dice из spell-записи).
  Для зелья `ability_mod=0` — лечит ровно по кости; для каста волшебника —
  по `from_caster` (с прибавкой мода).
* **BUFF** — модификаторы цели (КД, проверки, атака, спасброски, ...).
  **Концентрационный** бафф (Shield of Faith) использует `source_id =
  concentration:{caster}` (одна группа, снимается срывом концентрации);
  **не-концентрационный** (зелье силы) — `source_id = buff:{spell}:{owner}`,
  независим от концентрации (фикс U3-1).
* **ATTACK / SAVE / AUTO / CONTROL** — для свитков. `Сл`/`атака` берутся из
  `SpellPower.scroll(level)`; **слот не тратится** (`consume_spell_slot` зовёт
  только `CastSpellAction`, ядро ничего не списывает).

Отложено в этап X:

* **LIGHT** (факел) — освещённость требует модели vision/LoS (нельзя описать
  булевым флагом), потому едет вместе с этапом исследования. См.
  `project_light_vision_deferred`.

## 5. Контент: items.yaml + spells.yaml

### Зелье лечения (HEAL)

```yaml
# spells.yaml
- id: potion_healing
  level: 0
  effect: heal
  targeting: { kind: single }
  heal_dice: "2d4+2"

# items.yaml
- id: healing_potion
  kind: consumable
  stackable: true
  use:
    effect_id: potion_healing
    economy: bonus_action
```

### Зелье силы (BUFF, не-концентрация)

```yaml
- id: potion_strength_buff
  effect: buff
  targeting: { kind: self }
  duration: { unit: until_encounter_end }
  buffs:
    - { target: ability_check, numeric_bonus: 2 }
```

### Свиток (CAST)

`is_scroll: true` → `SpellPower.scroll(level)` (фикс Сл по таблице).

```yaml
- id: scroll_of_fireball
  kind: consumable
  use:
    effect_id: fireball  # уже есть в каталоге, тот же что и у мага
    economy: action
    is_scroll: true
```

## 6. Стартовый инвентарь шаблона

`MonsterTemplate.starting_inventory: tuple[str, ...]` — список item-id; по
одной единице каждого. Загружается в `build_creature_from_template` при
наличии `item_repository` (опциональный kwarg). Демо-сценарий (`demo_skirmish`)
выдаёт ветерану зелье и свиток через этот механизм.

## 7. Как добавить новый используемый предмет

1. Если нужного эффект-пакета **нет** в `spells.yaml` — добавить там запись
   (любой существующий хендлер: HEAL/BUFF/SAVE/...). Никакого кода не пишется.
2. В `items.yaml` — `Item` с блоком `use: { effect_id, economy, is_scroll }`.
3. Тест на загрузку + использование (по образцу
   `tests/integration/content/test_usable_items_content.py`).

## 8. Отложено в следующих этапах

* **Ограничения использования** (свиток-по-классу/уровню) — этап W
  (`project_item_use_restrictions_deferred`): сейчас любой может прочитать
  любой свиток. По канону PHB-2024 уровень свитка ограничивает уровень
  заклинания и (опционально) класс.
* **LIGHT** — этап X (vision/LoS).
* **Drop/Equip** для используемых предметов — отдельно от U (уже есть
  `PickupAction`; полноценные drop/equip — этап O-8/9).
* **Очистка `until_encounter_end`-баффов на `EncounterEnded`** — этап X
  (`GameSession`): сейчас `Encounter` короткоживущий, утечка не
  воспроизводится. С появлением сессий поверх боёв нужно подписать на
  `EncounterEnded` чистку `modifier_applier.remove_by_source(...)` для
  таких баффов. Источник истины — `BuffSpec.duration`.
* **Узкие BUFF-таргеты по характеристикам** (отдельно «Сила», «Ловкость»,
  ...) — этап W: сейчас `potion_of_strength` использует `ability_check`
  (категория «любая проверка характеристик»), что чуть шире классики PHB.
  Точечный таргет — расширение `ModifierTargetKind` (за рамками U).

## 9. Что включено в этап U

* `SpellPower` VO + scroll-таблица + `from_caster`/`scroll`/`potion`.
* Вынос `resolve_and_apply_spell` из `CastSpellAction` (slotless-ядро).
* `ItemUseSpec` + `Item.use` + YAML-парсинг.
* Событие `ItemUsed` + рендер в `EventPrinter` (🧪 зелье / 📜 свиток).
* `UseItemAction` + `UseItemIntent` + диспатч в `GameRunner._do_use_item`.
* Контент: `potion_healing`/`potion_strength_buff`/`scroll_of_cure_wounds`/
  `scroll_of_fireball` + `MonsterTemplate.starting_inventory` + демо-инвентарь.
* Фикс `BuffSpellHandler.source_id` (не-конц. бафф независим от концентрации).
* E2E-смок: PC выпивает зелье и читает свиток на скопление гоблинов.
