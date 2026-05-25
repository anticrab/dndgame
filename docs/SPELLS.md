# Заклинания (этап P1 — фундамент)

Подсистема заклинаний построена на двух принципах:

1. **Data-driven заклинания.** Заклинание — это данные (`Spell`), а не код.
   Каталог — `data/content/spells.yaml`, грузится `YamlSpellRepository`.
2. **Расширяемая обработка через реестр эффект-хендлеров** (open/closed). Тип
   воздействия (`SpellEffect`) обрабатывает свой `SpellEffectHandler`,
   зарегистрированный в `SpellEffectRegistry`. `CastSpellAction` — тонкий:
   резолвит цель/слот/экономику и делегирует хендлеру.

Это даёт две оси роста без боли:
- **новое заклинание существующего типа** = строки в YAML, **ноль кода**;
- **новый тип воздействия** = новый класс-хендлер + регистрация, **без касания**
  `CastSpellAction` и существующих хендлеров (никаких центральных `switch`).

## Модель данных — `Spell` (`domain/values/spell.py`)

| Поле | Назначение |
|------|-----------|
| `id`, `name`, `level`, `school` | идентификация; `level=0` — заговор |
| `effect: SpellEffect` | ATTACK / SAVE / AUTO / HEAL / BUFF — выбирает хендлер |
| `targeting: TargetingSpec` | `kind` SELF/SINGLE (P1) + задел MULTI/AREA (P2) |
| `range_ft` | дальность |
| `description` | текст для справки (зерно базы знаний — этап P3) |
| `dice`, `damage_type` | урон (ATTACK/AUTO/SAVE) |
| `save_ability`, `save_for_half` | спасбросок (SAVE): какая хар-ка, половина/ноль при успехе |
| `concentration` | требует концентрации (BUFF) |
| `heal_dice` | лечение (HEAL) |
| `ac_bonus` | бафф КД (BUFF, напр. Shield of Faith +2) |

Валидация по `effect` — в `Spell.__post_init__` (ATTACK/AUTO требуют dice+тип;
SAVE — ещё save_ability; HEAL — heal_dice; BUFF — ac_bonus>0).

## Типы воздействия и хендлеры (`application/engine/spells/handlers.py`)

| `SpellEffect` | Хендлер | Логика |
|---------------|---------|--------|
| ATTACK | `AttackSpellHandler` | spell attack roll (d20+бонус) vs КД → урон; крит удваивает кости |
| SAVE | `SaveSpellHandler` | цель кидает спасбросок vs Сл.; провал — полный урон, успех — половина/ноль |
| AUTO | `AutoSpellHandler` | авто-попадание без броска (Magic Missile) |
| HEAL | `HealSpellHandler` | `target.heal(heal_dice + mod)` |
| BUFF | `BuffSpellHandler` | модификатор КД через `ModifierApplier`; концентрация |

Хендлеры публикуют свои события (`DamageDealt`/`HealingApplied`) через
`ctx.event_bus`. `CastSpellAction` публикует `SpellCast` до делегирования.

## Заклинательные характеристики (`Creature`, P1)

- `spellcasting_ability: Ability | None` — INT/WIS/CHA; None = не-кастер;
- `spell_slots: dict[int,int]` — level → осталось; заговоры (level 0) безлимитны;
- `known_spells: tuple[SpellId, ...]` — список известных.

Деривации (PHB-2024 стр. 233): spell attack = `prof + mod`, save DC = `8 + prof + mod`.
Модель ячеек **упрощённая** (без классовой таблицы — она появится на этапе R).

## Концентрация

Одно concentration-заклинание на кастера (`Creature.concentration: SpellId`).
Старт нового concentration-заклинания снимает прежний эффект (BuffSpellHandler
удаляет модификатор по `source_id = spell:{spell}:{caster}`).

## UI

- **TUI**: заклинания актора попадают в `ActionBarWidget` на hotkey'и `1..9`
  (`spell_ability`); полоса видна только у кастера. Урон-заклинания целятся во
  врагов, heal/buff — в союзников и себя (`BattleScreen._list_spell_targets`).
- **Лог** (CLI+TUI): `✨ aelar casts Fire Bolt at goblin`, `✚ hero heals 7 (HP 9/12)`.

## Как добавить заклинание

**Существующего типа** — только YAML:
```yaml
- id: ray_of_frost
  name: "Ray of Frost"
  level: 0
  school: evocation
  effect: attack
  targeting: { kind: single }
  range_ft: 60
  dice: "1d8"
  damage_type: cold
  description: "Луч холода; дальнобойная атака заклинанием."
```
Затем добавить `id` в `known_spells` нужного шаблона (`monsters.yaml`).

**Нового типа воздействия** (напр. «телепорт», «призыв») — новый класс,
реализующий `SpellEffectHandler.apply(caster, targets, spell, ctx)`, и его
регистрация в `default_spell_effect_registry` (или в контент-паке). Ни
`CastSpellAction`, ни существующие хендлеры не меняются.

## Контент P1 (5 заклинаний)

Fire Bolt (attack), Sacred Flame (save), Magic Missile (auto), Cure Wounds
(heal), Shield of Faith (buff+concentration) — по одному на каждый тип
воздействия, чтобы движок был проверен на всех механиках. Кастер-PC —
`mage_apprentice`, сценарий `mage_skirmish`.

## Зоны поражения (AoE, этап P2)

Зона конфигурируется тремя независимыми осями в `TargetingSpec` (`kind=area`):

| Поле | Значения | Назначение |
|------|----------|-----------|
| `origin` | `from_caster` / `at_point` | от клетки кастера (в направлении) или вокруг выбранной точки |
| `shape` | `circle` / `cone` / `line` | форма (расширяемо через реестр резолверов) |
| `radius_ft` | для `circle` | радиус |
| `length_ft` | для `cone`/`line` | длина |

- **at_point** (снаряд → взрыв): игрок целит клетку в пределах `range_ft`, зона
  строится вокруг неё. Пример — Fireball (круг r=10фт).
- **from_caster** (эманация): зона строится от клетки кастера в выбранном
  **направлении** (8 сторон, вкл. диагонали). Примеры — Burning Hands (конус),
  Lightning Bolt (линия). Можно запускать и по диагонали.

Зона бьёт **всех** живых существ в задетых клетках — **включая союзников и
кастера** (friendly fire). Урон/спасброски идут через те же эффект-хендлеры
(они принимают кортеж целей).

**Геометрия** — чистые функции `domain/values/geometry.py`
(`circle_squares`/`line_squares`/`cone_squares`); футы→клетки = `ft//5`.
**Резолвинг формы** — `AreaShapeRegistry` (open/closed): новая форма зоны =
новый `AreaShapeResolver` + регистрация в `default_area_shape_registry`, без
правки `CastSpellAction`.

Пример AoE-заклинания (YAML):
```yaml
- id: fireball
  level: 1
  effect: save
  targeting: { kind: area, origin: at_point, shape: circle, radius_ft: 10 }
  range_ft: 150
  dice: "2d6"
  damage_type: fire
  save_ability: DEX
  save_for_half: true
```

## Отложено

- **P2b:** мультитаргет — выбор N отдельных целей (Bless, распределение
  дротиков Magic Missile). Поле `TargetingSpec.max_targets` заложено.
- **P3:** справка/inspect по заклинанию-способности → база знаний
  (`description` уже заполняется).
- Upcasting (каст на слот выше), реакция-каст (Shield как реакция), ритуалы,
  материальные компоненты, классовые таблицы ячеек (→ R), блокировка зоны
  стенами/LoS (в P2 зона по чистой геометрии).
