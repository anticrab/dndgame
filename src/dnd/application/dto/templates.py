"""Шаблоны контента — DTO для загрузки existo, оружий, сценариев из
внешних источников (YAML, SQLite, JSON).

Это **read-only схема**, не игровые сущности. Конкретные ``Creature`` /
``Battlefield`` / ``Encounter`` строятся из шаблонов через builder'ы.

См. ``docs/ENGINE.md`` §2.6 («Карта в YAML сценария») и ARCHITECTURE.md.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.damage import DamageType
from dnd.domain.values.faction import Faction


class WeaponTemplate(BaseModel):
    """Запись об оружии в каталоге контента.

    Соответствует :class:`WeaponProfile` 1-в-1, плюс ``id`` для лукапа.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    kind: AttackKind
    damage_expr: str
    damage_type: DamageType
    range_ft: int = Field(default=5, ge=5)
    long_range_ft: int = Field(default=0, ge=0)
    ability: str = "STR"  # ключ Ability enum (STR/DEX/...)
    finesse: bool = False


class AbilityScoresTemplate(BaseModel):
    """Six abilities as one record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    str_: int = Field(alias="str", ge=1, le=30)
    dex: int = Field(ge=1, le=30)
    con: int = Field(ge=1, le=30)
    int_: int = Field(alias="int", ge=1, le=30)
    wis: int = Field(ge=1, le=30)
    cha: int = Field(ge=1, le=30)


class MonsterTemplate(BaseModel):
    """Запись о существе в каталоге.

    ``id`` — стабильный идентификатор шаблона (например, ``"goblin"``).
    Конкретный экземпляр в encounter получает свой ``CreatureId``
    (например, ``"goblin#1"``) через :func:`build_creature_from_template`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    abilities: AbilityScoresTemplate
    max_hp: int = Field(ge=1)
    armor_class: int = Field(ge=1)
    speed_ft: int = Field(default=30, ge=0)
    proficiency_bonus: int = Field(default=2, ge=2, le=6)
    weapon_id: str | None = None
    default_faction: Faction = Faction.MONSTERS
    resistances: tuple[str, ...] = ()
    vulnerabilities: tuple[str, ...] = ()
    immunities: tuple[str, ...] = ()

    # Заклинания (этап P1). None/пусто — не-кастер (backward-compat).
    spellcasting_ability: str | None = None  # "INT" / "WIS" / "CHA"
    known_spells: tuple[str, ...] = ()
    spell_slots: dict[int, int] = Field(default_factory=dict)  # level → count

    # Прогрессия (этап R1). cr — для награды XP (XP=cr*100); character_class/
    # level — для PC (level-up через LevelUpService). None/0 — обычный монстр.
    cr: float = Field(default=0.0, ge=0)
    character_class: str | None = None  # "fighter" / "rogue"
    level: int = Field(default=1, ge=1)
    # Накопленный XP на старте (для PC-«ветеранов»: демо-сцена ставит воина
    # у порога уровня, чтобы level-up случился в бою). 0 — обычный старт.
    xp: int = Field(default=0, ge=0)
    # T4: выбор данными шаблона (интерактив отложен). Боевой стиль (Воин L1) и
    # подкласс (L3); None → автовыбор дефолта в LevelUpService.
    fighting_style: str | None = None
    subclass: str | None = None


class SpawnTemplate(BaseModel):
    """Кто и где появляется в сценарии."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str  # MonsterTemplate.id или CharacterTemplate.id
    instance_id: str  # CreatureId данного боя ("goblin#1")
    at: tuple[int, int]  # (x, y)
    faction: Faction


class MapTemplate(BaseModel):
    """Прямоугольная карта: легенда + grid (символы построчно)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: int = Field(ge=1)
    height: int = Field(ge=1)
    # Легенда: символ → terrain id (floor / wall / difficult / pit / ...).
    legend: dict[str, str]
    # Сетка: tuple строк длиной width, всего height строк.
    grid: tuple[str, ...]


class ScenarioTemplate(BaseModel):
    """Сценарий: имя + карта + spawns. Достаточно для запуска боя.

    Полный сценарий с диалогами, локациями, exploration и т.п. —
    отдельная сущность (пост-MVP).

    Карта задаётся **одним из двух способов** (XOR):

    * ``map: MapTemplate`` — inline grid+legend (legacy MVP-формат).
    * ``map_id: str`` — ссылка на ``MapDocument`` из ``MapRepository``
      (K8: data/content/maps/{id}.yaml). В этом случае Battlefield
      строится через Tile API + objects.

    Один из двух обязательно должен быть задан (model_validator).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    map: MapTemplate | None = None
    map_id: str | None = None
    spawns: tuple[SpawnTemplate, ...]

    @model_validator(mode="after")
    def _check_map_xor(self) -> ScenarioTemplate:
        if (self.map is None) == (self.map_id is None):
            raise ValueError("ScenarioTemplate requires exactly one of `map` or `map_id`")
        return self


__all__ = [
    "AbilityScoresTemplate",
    "MapTemplate",
    "MonsterTemplate",
    "ScenarioTemplate",
    "SpawnTemplate",
    "WeaponTemplate",
]
