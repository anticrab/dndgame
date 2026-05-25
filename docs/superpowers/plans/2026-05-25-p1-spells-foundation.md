# Этап P1: Заклинания — фундамент — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development или executing-plans. Шаги — checkbox TDD.

**Goal:** Data-driven заклинания: `Spell` (YAML) + `CastSpellAction` (switch по effect) + ячейки + 5 заклинаний (single/self/auto) + ActionBar + события.

**Architecture:** `Spell`-value (с заделом под AoE/мультитаргет/описание) грузится `YamlSpellRepository`; `Creature` получает spellcasting-поля; один `CastSpellAction` исполняет по `spell.effect` (ATTACK/SAVE/AUTO/HEAL/BUFF); заклинания превращаются в `Ability` и попадают в `ActionBarWidget`.

**Tech Stack:** Python 3.12, pydantic v2 frozen, Textual, hexagonal, pytest, mypy strict, ruff.

**Конвенции:** коммиты `Maxim Lokotkov` / `anticrab@users.noreply.github.com`; доки/комментарии на русском; после каждого таска `python3 -m pytest -q && mypy src/ && ruff check`; git push/reset --hard/rebase запрещены.

Спек: docs/superpowers/specs/2026-05-25-p1-spells-foundation-design.md (детали полей/механик — там).

---

## Образцы для переиспользования
- `application/engine/actions/attack.py` — spell-attack roll, крит, DamageDealt.
- `application/engine/actions/stabilize.py` — структура Action (can_perform_against/execute, ACTION economy).
- `application/ports/item_repository.py` + `infrastructure/content/yaml_item_repository.py` — образец Port+YAML.
- `application/abilities/defaults.py` + `ability.py` — Ability + intent_factory.
- `interfaces/tui/widgets/action_bar_widget.py` — ActionBarWidget (был скрыт в M).
- `application/dto/rolls.py` — RollPurpose (ATTACK/SAVE/DAMAGE), RollContext.
- `Creature.take_damage`/`heal`, `abilities.modifier(Ability.X)`, `proficiency_bonus`.

---

## P1-1: `Spell` value + enums + валидация
**Files:** Create `src/dnd/domain/values/spell.py`; Test `tests/unit/domain/test_spell.py`.

Реализовать `SpellEffect`, `TargetKind`, `TargetingSpec`, `Spell` (см. spec §4.1).
`__post_init__`: level>=0; ATTACK/AUTO требуют `dice`+`damage_type`; SAVE требует
`dice`+`damage_type`+`save_ability`; HEAL требует `heal_dice`; BUFF требует
`ac_bonus>0` (на P1; condition-баффы — позже).

- [ ] Тест: создание валидного Spell каждого effect; ValueError при пропуске
  обязательного поля (ATTACK без dice; SAVE без save_ability; HEAL без heal_dice).
- [ ] Реализация. Запуск → зелено. Sweep + commit `feat(domain): P1-1 Spell value + targeting/effect enums`.

## P1-2: SpellRepository + YAML + 5 заклинаний
**Files:** Create `src/dnd/application/ports/spell_repository.py`,
`src/dnd/infrastructure/content/yaml_spell_repository.py`,
`data/content/spells.yaml`; Test `tests/integration/content/test_yaml_spell_repository.py`.

Port (`@runtime_checkable` Protocol): `list_ids()`, `load(id)`, `contains(id)`.
YAML-адаптер по образцу `YamlItemRepository` (дубли-guard, нет файла → пусто).
`spells.yaml` — 5 заклинаний:
- `fire_bolt`: level0, ATTACK, SINGLE, range120, dice "1d10", fire.
- `sacred_flame`: level0, SAVE, SINGLE, range60, dice "1d8", radiant, save DEX, save_for_half=False (полный или ноль).
- `magic_missile`: level1, AUTO, SINGLE, range120, dice "3d4+3", force.
- `cure_wounds`: level1, HEAL, SINGLE(touch range5), heal_dice "1d8".
- `shield_of_faith`: level1, BUFF, SINGLE, range60, ac_bonus 2, concentration true.

- [ ] Тест: load каждого; contains; дубль id → ошибка; пустой путь → 0.
- [ ] Реализация. Зелено. Sweep + commit `feat(content): P1-2 SpellRepository + spells.yaml (5)`.

## P1-3: Creature spellcasting-поля + деривации
**Files:** Modify `src/dnd/domain/entities/creature.py`; Test
`tests/unit/domain/test_creature_spellcasting.py`.

Поля (после `known`-секции, default не-кастер):
`spellcasting_ability: Ability | None = None`;
`spell_slots: dict[int,int] = field(default_factory=dict)`;
`known_spells: tuple[SpellId,...] = ()`. (Импорт `Ability` уже есть.)
Методы: `spell_attack_bonus()`, `spell_save_dc()` (raise ValueError если
`spellcasting_ability is None`); `has_spell_slot(level)` (level0→True);
`consume_spell_slot(level)` (level0→no-op; нет слота→ValueError).

- [ ] Тест: attack = prof+mod; DC = 8+prof+mod; не-кастер → ValueError;
  слоты трата/исчерпание; cantrip безлимит.
- [ ] Реализация. Зелено. Sweep + commit `feat(domain): P1-3 Creature spellcasting + деривации`.

## P1-4: CastSpellAction — ATTACK (Fire Bolt)
**Files:** Create `src/dnd/application/engine/actions/cast_spell.py`,
`src/dnd/application/dto/engine_event.py` (+ `SpellCast`);
Test `tests/integration/engine/test_cast_spell.py`.

`CastSpellParams(spell_id, target_id|None)`. Action хранит ссылку на
`SpellRepository` (в конструкторе, как PickupAction с item_repository).
`can_perform_against`: actor кастер; spell в known; level>0 → слот; ACTION
economy; цель: SELF→actor, SINGLE→ существо в range (distance_to_feet).
`execute` ATTACK-ветка: spend slot+ACTION; `SpellCast` event; spell-attack roll
(prof+mod) vs AC → hit → `take_damage(DiceExpr.parse(spell.dice), damage_type)`;
крит удваивает кости (как attack.py). DamageDealt publish.
`SpellCast(caster_id, spell_id, slot_level, target_id: CreatureId|None)`.

- [ ] Тест: Fire Bolt hit (урон применён, SpellCast+DamageDealt), miss (нет урона),
  cantrip без слота не тратит слот; вне range → Forbidden; не-кастер → Forbidden.
- [ ] Реализация. Зелено. Sweep + commit `feat(engine): P1-4 CastSpellAction ATTACK + SpellCast`.

## P1-5: + SAVE (Sacred Flame)
**Files:** Modify `cast_spell.py`; Test дополнить.
SAVE-ветка: бросок урона; цель кидает спасбросок `save_ability` (d20+mod) vs
`caster.spell_save_dc()`; success → 0 урона (sacred_flame save_for_half=False),
иначе полный. (Для save_for_half=True — половина; заложить обе ветки.)

- [ ] Тест: save провален → полный урон; save успешен → 0 (sacred flame);
  отдельный кейс save_for_half=True → половина.
- [ ] Реализация. Зелено. Sweep + commit `feat(engine): P1-5 CastSpellAction SAVE`.

## P1-6: + AUTO (Magic Missile)
**Files:** Modify `cast_spell.py`; Test дополнить.
AUTO-ветка: `take_damage(dice)` без броска атаки. Тратит слот level1.

- [ ] Тест: Magic Missile авто-урон (3d4+3 фикс через ScriptedRNG), слот потрачен,
  нет слота → Forbidden.
- [ ] Реализация. Зелено. Sweep + commit `feat(engine): P1-6 CastSpellAction AUTO`.

## P1-7: + HEAL (Cure Wounds)
**Files:** Modify `cast_spell.py`; Test дополнить.
HEAL-ветка: `target.heal(roll(heal_dice) + mod(spellcasting_ability))`. Не выше max.
Touch (range5). Может поднять из dying (Q heal-логика — без изменений).

- [ ] Тест: Cure Wounds лечит раненого; не выше max; поднимает PC из dying
  (death_saves → None, Unconscious снят).
- [ ] Реализация. Зелено. Sweep + commit `feat(engine): P1-7 CastSpellAction HEAL`.

## P1-8: + BUFF/concentration (Shield of Faith)
**Files:** Modify `cast_spell.py`, возможно `creature.py` (helper concentration);
Test дополнить.
BUFF-ветка: применить `ac_bonus` к цели. Способ: временный модификатор AC.
Проверить, как `ModifierApplier` собирает AC (attack.py использует
`ModifierTargetKind.ARMOR_CLASS`) — добавить источник модификатора на цель, или
(проще для P1) хранить активный бафф в состоянии и учитывать в AC-расчёте.
**Решение реализатора по факту:** выбрать минимальный путь, не ломающий
attack.py AC-сбор; задокументировать в SPELLS.md. concentration: при касте
concentration-заклинания — `_start_concentration`: если у кастера уже есть
`concentration` — снять прежний бафф, поставить новый `spell_id`.

- [ ] Тест: Shield of Faith +2 AC цели (атака, которая попала бы, мажет);
  concentration выставлен; каст второго concentration-заклинания снимает первый
  (AC возвращается).
- [ ] Реализация. Зелено. Sweep + commit `feat(engine): P1-8 CastSpellAction BUFF + concentration`.

## P1-9: CastSpellIntent + GameRunner
**Files:** Modify `src/dnd/application/dto/player_intent.py`,
`src/dnd/application/engine/game_runner.py`; Test
`tests/integration/engine/test_cast_spell_intent.py`.
`CastSpellIntent(spell_id, target_id: CreatureId|None)` в union + `__all__`.
`GameRunner.__init__(spell_repository: SpellRepository | None = None)`;
`_do_cast` (как `_do_pickup`: нет repo → log rejected). Маршрут в `_apply_intent`.

- [ ] Тест: CastSpellIntent через GameRunner кастует Fire Bolt (урон применён);
  без spell_repository → rejected.
- [ ] Реализация. Зелено. Sweep + commit `feat(engine): P1-9 CastSpellIntent + GameRunner wiring`.

## P1-10: spell_ability + возврат ActionBarWidget
**Files:** Modify `src/dnd/application/abilities/defaults.py` (или новый
`spell_abilities.py`), `src/dnd/interfaces/tui/screens/battle.py`,
`src/dnd/interfaces/tui/app.py`/`cli/app.py` (проброс SpellRepository); Test
`tests/integration/tui/test_spell_action_bar.py`.
`spell_ability(spell, hotkey)` → `Ability` (requires_target = SINGLE;
intent_factory → CastSpellIntent). BattleScreen: строит abilities из
`actor.known_spells` (через SpellRepository), биндит `1..9`, **показывает
ActionBarWidget** (вернуть из M-скрытия) с `[1] Fire Bolt …`.

- [ ] Тест (pilot): у PC с known_spells полоса содержит `[1] Fire Bolt`; нажатие
  `1` уводит в TARGET mode (или кастует SELF сразу).
- [ ] Реализация. Зелено. Sweep + commit `feat(tui): P1-10 spell action-bar + ActionBarWidget возврат`.

## P1-11: SpellCast рендер в EventPrinter
**Files:** Modify `src/dnd/interfaces/cli/event_printer.py`; Test
`tests/integration/cli/test_event_printer_spell.py`.
Handler `_on_spell_cast`: `✨ {caster} casts {spell_name}` (+ `at {target}` если
есть target). Имя заклинания — нужен SpellRepository ИЛИ кладём `spell_name` в
событие. **Решение:** добавить `spell_name: str` в `SpellCast` (EventPrinter без
доступа к repo) — проще и без новой зависимости.

- [ ] Тест: SpellCast рендерится с именем и целью.
- [ ] Реализация (включая `spell_name` в SpellCast + проставление в CastSpellAction).
  Зелено. Sweep + commit `feat(events): P1-11 SpellCast рендер`.

## P1-12: сценарий выдаёт PC заклинания
**Files:** Modify `src/dnd/application/engine/scenario_builder.py` (+ источник
данных: monster/character template или хардкод для PARTY-кастера); Test
`tests/integration/engine/test_scenario_spells.py`.
Минимально: PARTY-существо с подходящим шаблоном получает
`spellcasting_ability`, `known_spells` (5), `spell_slots` (напр. {1: 2}). Способ
задания — по факту (поле в monster YAML или маппинг по template_id). Реализатор
выбирает наименее инвазивный путь; задокументировать.

- [ ] Тест: построенный из сценария PC-кастер имеет known_spells и слоты.
- [ ] Реализация. Зелено. Sweep + commit `feat(content): P1-12 PC-кастер в сценарии`.

## P1-13: docs SPELLS.md + ROADMAP
**Files:** Create `docs/SPELLS.md`; Modify `docs/ROADMAP.md`.
SPELLS.md (рус.): модель `Spell`, effect-типы, деривации attack/DC, ячейки,
концентрация, как добавить заклинание (YAML), что отложено (AoE/мультитаргет→P2,
справка→P3). ROADMAP: пометить P1.

- [ ] Sweep + commit `docs: P1-13 SPELLS.md + ROADMAP`.

---

## Финальный аудит
Независимый аудит P1 (general-purpose subagent), как после Q: инварианты §6,
корректность правил (spell attack/DC, save half/full, концентрация-replace,
слоты), отсутствие регрессий, маскирующие тесты (проверять реальный флоу через
can_perform_against, не только execute — см. урок Q C-1). Применить CRITICAL/MAJOR.

## Self-Review
- Spec §2 скоуп → таски P1-1..P1-13 покрывают все пункты «Включено».
- Каждый effect-branch (§4.4) → отдельный таск P1-4..P1-8 с тестом.
- Заделы под P2/P3 (targeting/description) — в P1-1 (поля), реализация single/self.
- Типы согласованы: `SpellEffect`/`TargetKind`/`Spell` поля — едины между тасками.
- Открытые «решения реализатора» (BUFF AC-механика P1-8; способ выдачи
  заклинаний P1-12) помечены явно с указанием файла-источника для сверки —
  не плейсхолдеры, а точки, где надо посмотреть реальный код.
