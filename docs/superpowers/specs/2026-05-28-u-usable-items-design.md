# U — используемые предметы: дизайн (единый слой эффектов)

> Заменяет устаревший `2026-05-27-u-usable-items-design.md` (тот предлагал
> отдельный `ItemEffectRegistry` с дублями). Здесь — **единый слой эффектов**:
> предмет ссылается на эффект-пакет по id и производит его slotless через то же
> ядро, что и заклинание. Прямое следствие требования `project_unified_effects`.
> Блокеры сняты: слой времени/длительностей готов (этап X0).

«Оживляет» готовый инвентарь (этап O): зелья лечат, свитки кастуют, есть
зелья-баффы. Принципы: эффект — данные/реестр (не switch); domain не зависит от
application; никакого дублирования логики заклинаний и предметов.

## 1. Решения (зафиксированы с пользователем)

- **Объём:** HEAL (зелье), CAST (свиток), BUFF (зелье-бафф). **LIGHT отложен в X**
  (свет — не заклинание; без системы видимости бесполезен, см.
  `project_light_vision_deferred`).
- **Единый slotless-каст:** предмет ссылается на эффект-пакет в `spells.yaml`
  (`use.effect_id`) и производит его через вынесенное ядро резолва **без траты
  слота**. Свиток файрбола = тот же `fireball`, что кастует волшебник.
- **Свиток — без ограничений** (любой персонаж). Ограничения по классу/уровню/
  способности — отложено до создания персонажа W (`project_item_use_restrictions_deferred`).
- **Сл/атака свитка — фикс по уровню заклинания** (таблица PHB-2024), не зависят
  от читателя. Заговор–2 ур → DC13/+5; 3 ур → DC15/+7 (полная таблица — данные).
- **Зелье лечения** лечит ровно `2d4+2`, **без** модификатора пьющего.
- **Экономика — данными предмета:** зелье → бонусное действие (PHB: выпить зелье =
  Bonus Action), свиток → действие.
- **UX:** использование с экрана инвентаря (`l`); таргет (если нужен) —
  существующими режимами TUI.

## 2. Ядро резолва эффекта (рефактор слоя заклинаний)

Из `CastSpellAction.execute` выносится чистая функция (модуль
`application/engine/spells/resolve.py`):

```python
def resolve_and_apply_spell(
    caster: Creature,
    spell: Spell,
    params: SpellTargeting,   # target_id / target_ids / target_point / direction
    ctx: TurnContext,
    *,
    power: SpellPower,
    effect_registry: SpellEffectRegistry,
    area_registry: AreaShapeRegistry,
) -> None: ...
```

Содержит текущие `_resolve_targets(...)` + `effect_registry.get(spell.effect).apply(...)`.
**Без** `consume_spell_slot` и **без** `ctx.spend` — экономика/слот остаются в
вызывающих действиях.

### 2.1 `SpellPower` — источник Сл/атаки/мода

Новый frozen VO (`domain/values/spell_power.py`):

```python
@dataclass(frozen=True, slots=True)
class SpellPower:
    save_dc: int       # для SAVE / CONTROL
    attack_bonus: int  # для ATTACK
    ability_mod: int   # прибавка к HEAL ("+ мод заклинательной хар-ки")
```

- **Из кастера** (`SpellPower.from_caster(creature)`): `spell_save_dc()` /
  `spell_attack_bonus()` / `abilities.modifier(spellcasting_ability)` (0, если не
  кастер). Используется в `CastSpellAction`.
- **Свиток** (`SpellPower.scroll(level)`): фикс по таблице PHB, `ability_mod=0`.
- **Зелье HEAL**: `SpellPower(0, 0, ability_mod=0)` — лечит ровно по кости.

Таблица свитка (данные, `domain/values/spell_power.py` или рядом):

| Уровень заклинания | Сл | Атака |
|--------------------|----|-------|
| заговор–2 | 13 | +5 |
| 3–4 | 15 | +7 |
| 5–6 | 17 | +9 |
| 7–8 | 18 | +10 |
| 9 | 19 | +11 |

(в U используются уровни 0–3; таблица заведена целиком.)

### 2.2 Правка протокола хендлеров

`SpellEffectHandler.apply(caster, targets, spell, ctx, power)` — добавляется
`power: SpellPower`. Хендлеры читают `power.save_dc` / `power.attack_bonus` /
`power.ability_mod` вместо прямых `caster.spell_*()`:

- `SaveSpellHandler` / `ControlSpellHandler`: `dc = power.save_dc`.
- `AttackSpellHandler`: `atk_bonus = power.attack_bonus`.
- `HealSpellHandler`: `amount = heal_roll.total + power.ability_mod`.
- `AutoSpellHandler` / `BuffSpellHandler`: `power` не используют (сигнатура ради
  единообразия).

Затрагивает 6 хендлеров и их тесты; регрессия CastSpell зелёная (в спелл-пути
`power = SpellPower.from_caster(caster)`).

> Альтернатива — носить `power` транзиентом на `TurnContext` (меньше правок
> сигнатур, но скрытое мутабельное состояние). Выбран явный параметр — честнее и
> тестируемее.

## 3. Данные (domain)

### 3.1 `domain/values/item_use.py`

```python
@dataclass(frozen=True, slots=True)
class ItemUseSpec:
    effect_id: SpellId                          # ссылка в spells.yaml
    economy: ActionEconomyCost = ActionEconomyCost.ACTION
    consumed: bool = True
    is_scroll: bool = False  # True → power фикс по уровню; иначе ability_mod=0
```

`is_scroll` различает источник `SpellPower`: свиток (фикс по уровню) vs зелье
(нулевой мод). Без концентрации у зелий — задаётся записью эффекта (`concentration:
false`).

### 3.2 `Item.use`

`use: ItemUseSpec | None = None` на `Item` (`domain/values/item.py`). У обычных
предметов None (backward-compat). Парсинг `use` в `YamlItemRepository`.

### 3.3 Эффект-пакеты в `spells.yaml`

- Реальные заклинания (`fireball`, `cure_wounds`) — переиспользуются как есть.
- Зельные эффекты — новые записи уровня 0, **не входящие ни в чью книгу** (кастуются
  только через предмет): `potion_healing` (HEAL, `heal_dice: 2d4+2`, таргетинг
  `SINGLE`, дальность 5 фт — себя или соседа), `potion_strength_buff` (BUFF,
  `SELF`, не-концентрация, длительность `until_encounter_end`).
- Один каталог — без второго репозитория; «одна логика».

## 4. Исполнение (application)

### 4.1 `UseItemAction` (`actions/use_item.py`)

`__init__(spell_repository, effect_registry?, area_registry?)`. **ItemRepository
не нужен**: используемый предмет уже лежит в `actor.inventory`, грузим оттуда
через `inventory.find_by_id(item_id)` (см. реализацию: post-review, спека
изначально предполагала `item_repository` — оказалось избыточно).

```python
class UseItemParams(ActionParams):
    item_id: ItemId
    target_id: CreatureId | None = None
    target_ids: tuple[CreatureId, ...] = ()
    target_point: Square | None = None
    direction: Direction | None = None
```

- `economy_cost` — номинально ACTION для UI; **реальная** экономика берётся из
  `item.use.economy` в `can_perform_against`/`execute`.
- `can_perform_against`: предмет в `actor.inventory` (`contains`); `use is not None`;
  эффект-пакет известен репозиторию и его эффект поддержан реестром;
  `ctx.can_spend(use.economy)`; валидность цели — теми же проверками, что у
  `CastSpellAction` (range/liveness/targeting по `spell.targeting`).
- `execute`: `ctx.spend(use.economy)`; `power` = `SpellPower.scroll(spell.level)`
  если `use.is_scroll`, иначе `SpellPower(0,0,0)`; `resolve_and_apply_spell(... power
  ...)` (slotless — слот не тратится); при `use.consumed` →
  `actor.inventory.remove_one(item_id)`; публикует `ItemUsed`.

### 4.2 Событие `ItemUsed`

`application/dto/engine_event.py`: `ItemUsed(actor_id, item_id, item_name,
effect: str, target_id: CreatureId | None, consumed: bool)`. Рендер в
`EventPrinter` (рус.: «выпивает зелье…», «читает свиток…»).

### 4.3 Фикс `BuffSpellHandler` (source_id)

Сейчас `source_id = concentration_source(caster.id)` **всегда** — для
не-концентрационного баффа (зелье) это неверно (новый concentration-спелл снял бы
бафф зелья). Правка: source = `concentration_source(caster)` **только** при
`spell.concentration`, иначе уникальный `f"buff:{spell.id}:{owner.id}"`.
Истечение по времени (X0) у не-концентрационного баффа — по `spell.duration`.

### 4.4 Интент + диспатч + TUI

- `UseItemIntent(_IntentBase)`: `kind="use_item"`, `item_id`, target-поля (как
  `CastSpellIntent`). В `PlayerIntent` union + `__all__`.
- `GameRunner._do_use_item`: грузит предмет, строит `UseItemParams`,
  `can_perform_against` → `execute`/`_log_rejected`. Runner получает
  `item_repository`/`spell_repository` (composition).
- TUI: на `InventoryScreen` у расходника с `use` — действие «Использовать»; если
  нужен таргет → существующие режимы (`SINGLE`/`AREA`/`MULTI`), затем
  `UseItemIntent`.

## 5. Контент (`items.yaml`)

- `healing_potion` (есть) → `use: {effect_id: potion_healing, economy: bonus_action,
  consumed: true}`.
- `potion_of_strength` (новый) → `use: {effect_id: potion_strength_buff, economy:
  bonus_action}`; запись эффекта BUFF в `spells.yaml`.
- `scroll_of_cure_wounds` (новый) → `use: {effect_id: cure_wounds, economy: action,
  is_scroll: true}`.
- `scroll_of_fireball` (новый) → `use: {effect_id: fireball, economy: action,
  is_scroll: true}`.

Демо-PC/сцена получает зелье и свиток в инвентарь — чтобы использование видно в
игре.

## 6. Расширяемость и инварианты

- Новый используемый предмет = строка в `items.yaml` (+ запись эффекта в
  `spells.yaml`, если эффекта ещё нет) — **без кода**.
- Эффект применяется единым ядром; новый тип воздействия = хендлер в
  `SpellEffectRegistry` (open/closed), работает и для заклинаний, и для предметов.
- domain не импортирует application; `ItemUseSpec`/`SpellPower` — данные в domain.
- Расходник списывается РОВНО при успешном применении; при отказе экономика не
  тратится.
- Backward-compat: `Item.use=None`; `power` в спелл-пути = из кастера (поведение
  CastSpell неизменно).
- Свиток/зелье не тратят слот заклинаний пользователя (slotless).

## 7. Декомпозиция (план)

- **U1 — ядро + `SpellPower` + рефактор хендлеров.** `SpellPower` VO + таблица
  свитка; `resolve_and_apply_spell`; протокол хендлеров `+power`; `CastSpellAction`
  зовёт ядро с `from_caster`. Регрессия CastSpell/handlers зелёная.
- **U2 — `Item.use` + `UseItemAction` + `ItemUsed` + интент.** `ItemUseSpec`,
  парсинг, действие (экономика из данных, slotless, списание), событие, интент,
  `GameRunner._do_use_item`, проводка composition.
- **U3 — HEAL + BUFF.** `potion_healing`/`potion_strength_buff` в `spells.yaml`;
  фикс `BuffSpellHandler.source_id`; тесты «зелье лечит на 2d4+2», «зелье-бафф
  висит и истекает по X0».
- **U4 — CAST (свиток).** `SpellPower.scroll(level)`; свитки cure_wounds/fireball;
  тест «свиток кастует без слота, фикс-DC по уровню».
- **U5 — TUI + контент + демо.** Использование с `InventoryScreen`; демо-инвентарь;
  `EventPrinter`.
- **U6 — доки + смок.** `docs/ITEMS.md` (или раздел в INVENTORY.md) + ROADMAP;
  e2e-смок «выпил зелье / прочитал свиток».

## 8. Отложено

- **LIGHT** (факел → свет/видимость) — этап X (`project_light_vision_deferred`).
- **Ограничения свитка** (класс/уровень/способность) — W
  (`project_item_use_restrictions_deferred`).
- **Drop/Equip/Unequip-интенты** — вне U (отмечены в O/Q).
- **Upcasting свитка** (свиток выше базового уровня) — пост-U.
