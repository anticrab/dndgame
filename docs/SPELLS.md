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
| `targeting: TargetingSpec` | `kind` SELF/SINGLE (P1), AREA (P2), MULTI (P2b) |
| `range_ft` | дальность |
| `description` | текст для справки (зерно базы знаний — этап P3) |
| `dice`, `damage_type` | урон (ATTACK/AUTO/SAVE) |
| `save_ability`, `save_for_half` | спасбросок (SAVE): какая хар-ка, половина/ноль при успехе |
| `concentration` | требует концентрации (BUFF) |
| `heal_dice` | лечение (HEAL) |
| `buffs: tuple[BuffSpec, ...]` | модификаторы баффа (BUFF); каждый `BuffSpec` — `target` + ровно одно из `numeric_bonus`/`dice_bonus` |

Валидация по `effect` — в `Spell.__post_init__` (ATTACK/AUTO требуют dice+тип;
SAVE — ещё save_ability; HEAL — heal_dice; BUFF — ≥1 `BuffSpec`).

## Типы воздействия и хендлеры (`application/engine/spells/handlers.py`)

| `SpellEffect` | Хендлер | Логика |
|---------------|---------|--------|
| ATTACK | `AttackSpellHandler` | spell attack roll (d20+бонус) vs КД → урон; крит удваивает кости |
| SAVE | `SaveSpellHandler` | цель кидает спасбросок vs Сл.; провал — полный урон, успех — половина/ноль |
| AUTO | `AutoSpellHandler` | авто-попадание без броска (Magic Missile) |
| HEAL | `HealSpellHandler` | `target.heal(heal_dice + mod)` |
| BUFF | `BuffSpellHandler` | модификатор КД через `ModifierApplier`; концентрация |
| CONTROL | `ControlSpellHandler` | наложение состояния (Sleep/Hold Person), T2 — см. ниже |

Хендлеры публикуют свои события (`DamageDealt`/`HealingApplied`) через
`ctx.event_bus`. `CastSpellAction` публикует `SpellCast` до делегирования.

## Заклинательные характеристики (`Creature`, P1)

- `spellcasting_ability: Ability | None` — INT/WIS/CHA; None = не-кастер;
- `spell_slots: dict[int,int]` — level → осталось; заговоры (level 0) безлимитны;
- `known_spells: tuple[SpellId, ...]` — список известных.

Деривации (PHB-2024 стр. 233): spell attack = `prof + mod`, save DC = `8 + prof + mod`.
Ячейки задаются классовой таблицей (`classes.yaml`): Волшебник L1 — две ячейки
1-го круга, L3 — четыре 1-го и две 2-го (этап T1). У монстров-кастеров без класса
ячейки берутся из шаблона напрямую.

Спасброски целей против заклинаний (SAVE-эффект) идут через единую
`roll_saving_throw` (`engine/saving_throw.py`) с учётом профициентных
спасбросков цели — см. `docs/PROGRESSION.md` §7b.

## Концентрация

Одно concentration-заклинание на кастера (`Creature.concentration: SpellId`).
Старт нового concentration-заклинания снимает прежний эффект (BuffSpellHandler
удаляет модификатор по `source_id = spell:{spell}:{caster}`).

## Длительность (`Spell.duration`, этап X0)

Заклинание несёт `duration: Duration` (данными в `spells.yaml`,
`duration: { unit, amount }`; отсутствие → `INSTANT`). Для **конечной** длительности
хендлеры кладут дедлайн снятия по игровым часам в событие
(`ConditionApplied.expires_at_round` / `BuffApplied.expires_at_round`), и
`OngoingEffectTracker` снимает эффект на границе раунда. Это **дополняет** триггеры
(урон / повторный спасбросок / срыв концентрации), не заменяет их: `INSTANT` и
безлимитная концентрация по часам не снимаются. Концентрация-потолки:
Bless / Hold Person — 1 мин (10 раундов), Shield of Faith — 10 мин (100 раундов).
Подробно — `docs/TIME.md`.

## UI

- **TUI**: заклинания актора попадают в `ActionBarWidget` на hotkey'и `1..9`
  (`spell_ability`); полоса видна только у кастера. Урон-заклинания целятся во
  врагов, heal/buff — в союзников и себя (`BattleScreen._list_spell_targets`).
- **Меню способностей** (`Tab`, этап T1): заклинания показываются в общем списке
  способностей наравне с умениями — удобно, когда заклинаний больше девяти
  (см. `docs/ABILITIES.md` «Меню способностей»).
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

## Мультитаргет (этап P2b)

`TargetingSpec` с `kind=multi` — выбор нескольких целей как **мультимножество**:

| Поле | Назначение |
|------|-----------|
| `max_targets` | сколько всего «попаданий» (выборов) можно сделать |
| `allow_repeat_target` | можно ли класть несколько попаданий в одну цель |

Цели передаются в `CastSpellParams.target_ids` / `CastSpellIntent.target_ids` —
кортеж **с возможными дублями** (порядок = выборы). Эффект-хендлеры уже итерируют
кортеж целей, поэтому дубль = ещё одно применение эффекта. Так одной механикой
покрываются оба классических случая:

- **Bless** — `allow_repeat_target: false`, до 3 *разных* союзников; каждый
  получает +1d4 к броскам атаки и спасброскам (концентрация).
- **Magic Missile** — `allow_repeat_target: true`, 3 дротика по `1d4+1`;
  распределяются между целями (можно несколько в одну) — дубли в `target_ids`
  дают несколько бросков урона по одной цели.

Валидация `target_ids` — в `CastSpellAction.can_perform_against` (непусто,
`len ≤ max_targets`, дубли только при `allow_repeat_target`, дальность, liveness).

**Обобщённый бафф.** Вместо узкого `ac_bonus` — `Spell.buffs: tuple[BuffSpec,…]`.
`BuffSpec(target, numeric_bonus | dice_bonus)` накладывается `BuffSpellHandler`'ом
как `Modifier` через `ModifierApplier`. Bless'нутый союзник реально получает +1d4:
weapon-атаки подхватывают `ATTACK_ROLL`-модификаторы в `AttackAction`, а
спелл-атаки/спасброски — в `AttackSpellHandler`/`SaveSpellHandler` (собирают
`ATTACK_ROLL`/`SAVING_THROW` и прокидывают `extra_dice`).

Пример (YAML):
```yaml
- id: bless
  effect: buff
  targeting: { kind: multi, max_targets: 3, allow_repeat_target: false }
  range_ft: 30
  concentration: true
  buffs:
    - { target: attack_roll, dice_bonus: "1d4" }
    - { target: saving_throw, dice_bonus: "1d4" }
```

## Контроль состояний (этап T2)

`effect: control` накладывает состояние «до момента X». Поля `Spell`:
`condition` (что накладываем), ровно один гейт — `hp_pool_dice` (Sleep: пул
хитов без спасброска) **или** `save_ability` (резист-спасбросок); опционально
`condition_ends_on_damage` (Sleep — пробуждение от урона) и
`condition_repeat_save` (Hold Person — повторный спасбросок в конце хода).

`ControlSpellHandler` накладывает состояние через `ConditionService.
apply_with_implies` (каскад implies) и публикует `ConditionApplied` со всей
метой снятия. Длительность держит `OngoingEffectTracker`
(`engine/effects/ongoing_effect_tracker.py`) — application-служба на шине:

| Событие | Снятие |
|---------|--------|
| `DamageDealt` по цели (`ends_on_damage`) | пробуждение Sleep |
| `TurnEnded` цели (`repeat_save_ability`) | успешный повторный спасбросок |
| `ConcentrationBroken` кастера | снятие удержания |

Снятие убирает **ровно** наложенный набор состояний и публикует
`ConditionRemoved`. Инкапаситированный (Paralyzed/Unconscious → Incapacitated)
актёр не действует — guard в `GameRunner`/`SimpleMonsterAI`. Контент T2:
**Sleep** (L1, сфера r5, пул 5d8), **Hold Person** (L2, WIS-спасбросок,
концентрация). Заодно исправлены круги: Fireball/Lightning Bolt — 3-й.

Упрощение: ограничение «только гуманоид» для Hold Person отложено (нет типа
существа); стэкинг разных эффектов на одно состояние — тоже (см. ROADMAP T3).

## Отложено

- **P3:** справка/inspect по заклинанию-способности → база знаний
  (`description` уже заполняется).
- Upcasting (каст на слот выше), реакция-каст (Shield как реакция), ритуалы,
  материальные компоненты, классовые таблицы ячеек (→ R), блокировка зоны
  стенами/LoS (в P2 зона по чистой геометрии).
