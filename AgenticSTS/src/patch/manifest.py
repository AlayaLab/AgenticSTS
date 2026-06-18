"""Patch Manifest: structured description of one game version upgrade."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.patch.slug import slug


class RemovedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    replacement_note: str | None = None


class ReworkedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    category: str | None = None
    severity: Literal["major", "minor"]
    change: str | None = None


class RarityChangedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    from_: str = Field(alias="from")
    to: str


class NewCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    text: str | None = None


class ReworkedRelic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    severity: Literal["major", "minor"] = "major"
    change: str | None = None


class NewRelic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    source: str | None = None


class ReworkedEnemy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    severity: Literal["major", "minor"]
    # Other enemies that share the same encounter (e.g. boss + its minions)
    # and whose stored data should be invalidated together. Follows the
    # parent's severity: treated as major iff severity == "major".
    related_enemies: list[str] = []


class AscensionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ascension: int
    from_: str = Field(alias="from")
    to: str


class WritingClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str
    clarification: str


class NewSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    scope: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_version: str
    previous_version: str
    patch_date: str
    source: str = ""
    summary: str = ""

    removed_cards: list[RemovedCard] = []
    reworked_cards: list[ReworkedCard] = []
    rarity_changed_cards: list[RarityChangedCard] = []
    new_cards: list[NewCard] = []
    reworked_relics: list[ReworkedRelic] = []
    new_relics: list[NewRelic] = []
    reworked_enemies: list[ReworkedEnemy] = []
    ascension_changes: list[AscensionChange] = []
    shop_changes: list[str] = []
    writing_clarifications: list[WritingClarification] = []
    new_systems: list[NewSystem] = []

    @field_validator("patch_date", mode="before")
    @classmethod
    def _coerce_date_to_str(cls, v):
        """Coerce YAML-parsed datetime.date/datetime to str for patch_date field."""
        if v is None:
            return v
        if not isinstance(v, str):
            return str(v)
        return v

    def changed_entities(self) -> set[str]:
        """Slugged set of entities whose data should be purged."""
        out: set[str] = set()
        for c in self.removed_cards:
            out.add(slug(c.name))
        for c in self.reworked_cards:
            if c.severity == "major":
                out.add(slug(c.name))
        for r in self.reworked_relics:
            if r.severity == "major":
                out.add(slug(r.name))
        for e in self.reworked_enemies:
            if e.severity == "major":
                out.add(slug(e.name))
                for rel in e.related_enemies:
                    out.add(slug(rel))
        return out

    def prompt_review_targets(self) -> set[str]:
        """Broader set: entities + mechanics that trigger prompt rewrites."""
        out = self.changed_entities()
        # Include minor severity entries for wording updates
        for c in self.reworked_cards:
            if c.severity == "minor":
                out.add(slug(c.name))
        for r in self.reworked_relics:
            if r.severity == "minor":
                out.add(slug(r.name))
        for e in self.reworked_enemies:
            if e.severity == "minor":
                out.add(slug(e.name))
                for rel in e.related_enemies:
                    out.add(slug(rel))
        # New entities need prompt hints added
        for c in self.new_cards:
            out.add(slug(c.name))
        for r in self.new_relics:
            out.add(slug(r.name))
        # Clarifications reference specific entities
        for w in self.writing_clarifications:
            out.add(slug(w.entity))
        # Mechanics described in free text
        for a in self.ascension_changes:
            out.add(f"ascension_{a.ascension}")
        return out

    def dump_yaml(self, path: Path) -> None:
        data = self.model_dump(by_alias=True, exclude_none=False)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def load_manifest(path: Path) -> Manifest:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Manifest.model_validate(data)
