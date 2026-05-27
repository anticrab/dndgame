# Аудит игры — находки и диспозиция (2026-05-27)

Многоагентное ревью текущего состояния: архитектура/корректность, соответствие
правилам PHB-2024, слой интерфейсов. Все находки ниже **проверены вручную** по
коду. Документ — источник истины по тому, что чиним сейчас и что отложено.

## Чиним сейчас (REV-1..REV-7, inline TDD)

| # | Severity | Суть | Где |
|---|---|---|---|
| 1 | CRIT | Концентрация не прерывается уроном (CON-save не бросается) | engine + creature/encounter |
| 2 | MAJOR | UI не рефрешит HP/состояние при DeathSaveRolled/Stabilized/Died | tui/bridge/event_renderer |
| 3 | MAJOR | level-up «Сейчас!» не показывает +HP (`_call` глушит main-thread RuntimeError) | tui/bridge/event_renderer |
| 4 | MAJOR | Неверный intent после Esc из TARGET (`_pending_ability` не сброшен) | tui/screens/battle |
| 5 | MAJOR | Sneak Attack срабатывает при disadvantage (если союзник рядом) | actions/attack |
| 6 | MAJOR | Спам `LevelUpReady` выше макс. уровня класса | progression/xp_award |
| 7 | MAJOR | `begin_dying` минует ConditionService → нет implied Prone/Incapacitated | creature/encounter |

## Отложено — занесено в планы развития

### Подсистема правил (к этапу прогрессии/мага и далее)
- **Профициентные спасброски классов** (d20 + mod **+ prof**). Нужны данные
  `saving_throw_proficiencies` в `ClassProgression`/classes.yaml + поле в Creature +
  учёт во всех спасбросках (`SaveSpellHandler`, death-saves и т.д.).
  → **этап «Волшебник + прогрессия L1–L3»** (там трогаем классы/спасброски).
- **Авто-крит в упор по Unconscious/Paralyzed от заклинаний** (не только `is_at_zero_hp`).
  Сейчас источников Sleep/Hold Person нет → активируется вместе с такими заклинаниями.
  → этап мага (когда появятся контролящие заклинания).

### Боевые модификаторы состояний (отдельный этап «Условия в бою»)
- **Cross-creature преимущество**: атаки *по* Prone (≤5 фт), Stunned, Paralyzed,
  Unconscious — с преимуществом; Prone на расстоянии — с помехой.
- **Dodge** даёт преимущество на DEX-спасброски (сейчас только «помеха атакующим»).
- **Exhaustion −2 к d20** за уровень (модель есть, эффекта нет; источников пока нет).
- **Stunned/Paralyzed**: авто-провал STR/DEX-спасбросков (сейчас как помеха — `TODO(post-MVP)` в `builtin.py`).

### Прочее (по месту, когда будем рядом)
- **ranged-в-упор → disadvantage** (TODO в `attack.py`) → вместе с боевыми модификаторами.
- **CreatureDied при massive-damage по уже лежачему PC** не публикуется
  (`was_lethal=False`, т.к. был 0 HP) → мелкий событийный пробел; чинить при
  следующей правке dying.
- **`ability_menu_screen`**: в режиме «нажмите клавишу» не-alnum клавиши не
  `stop()`-аются (косметика). → при следующей правке меню.
- **dead-body-block**: мёртвые NPC остаются занятой клеткой, жадный AI не обходит
  → к умному pathfinding-AI (см. [[project_demo_slice]]).
- Мелочи: мёртвый `TurnContext.start_new_round`; dead `except NoMatches` в
  end-screen; `KeyError` в `build_keymap` при незарегистрированном ability_id
  (fail-fast — оставляем) — чистка по случаю.

### Намеренные упрощения (НЕ баги)
Диагональ 5 фт; Improved Critical всем Воинам L3 (упрощение подкласса, docs/PROGRESSION §8);
XP-кривые только L1–5; концентрация DC cap 30 (конвенция).
