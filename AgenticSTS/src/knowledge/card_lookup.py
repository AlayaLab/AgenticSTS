"""Card knowledge lookup — metadata + behaviors from decompiled source."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from src.knowledge.parser import parse_md_table

logger = logging.getLogger(__name__)


_ENERGY_TOK = "\x00E\x00"
_STAR_TOK = "\x00S\x00"
_HP_TOK = "\x00H\x00"


def _strip_bbcode(text: str) -> str:
    """Remove BBCode tags from game text, counting consecutive icon runs."""
    text = re.sub(r"\[img\][^\[]*energy_icon[^\[]*\[/img\]", _ENERGY_TOK, text)
    text = re.sub(r"\[img\][^\[]*star_icon[^\[]*\[/img\]", _STAR_TOK, text)
    text = re.sub(r"\[img\][^\[]*(?:hp|health)_icon[^\[]*\[/img\]", _HP_TOK, text)
    text = re.sub(r"\[img\][^\[]*\[/img\]", "", text)
    text = re.sub(r"\[/?[a-zA-Z_]+\]", "", text)
    for tok, singular, plural in (
        (_ENERGY_TOK, "Energy", "Energy"),
        (_STAR_TOK, "Star", "Stars"),
        (_HP_TOK, "HP", "HP"),
    ):
        def _merge(m: re.Match, _tok: str = tok, _s: str = singular, _p: str = plural) -> str:
            n = len(m.group(0)) // len(_tok)
            return f"{n} {_p}" if n > 1 else _s
        text = re.sub(f"(?:{re.escape(tok)})+", _merge, text)
    return text.strip()


def _humanize_identifier(value: str) -> str:
    cleaned = value.replace("_", " ").strip()
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)
    if cleaned.lower().endswith("power"):
        cleaned = cleaned[:-5]
    cleaned = re.sub(r"\bpower\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else value


def _format_upgrade_delta(name: str, value: str) -> str:
    label = _humanize_identifier(name)
    delta = value.strip()
    if delta.startswith(("+", "-")):
        return f"{label} {delta}"
    return f"{label} -> {delta}"


@dataclass(frozen=True, slots=True)
class CardKnowledge:
    """Combined card metadata + behavior."""
    name: str
    cost: str = ""
    type: str = ""
    rarity: str = ""
    target: str = ""
    on_play: str = ""
    on_upgrade: str = ""
    vars: str = ""
    # New fields from upstream JSON:
    powers_applied: tuple[tuple[str, int], ...] = ()  # (power_name, amount) pairs
    spawns_cards: tuple[str, ...] = ()
    upgrade_deltas: tuple[tuple[str, str], ...] = ()  # (var_name, delta_str) pairs
    base_hit_count: int | None = None
    # Full upstream card data for upgrade previews
    description: str = ""           # Resolved description (BBCode), e.g. "Gain 5 [gold]Block[/gold]."
    description_raw: str = ""       # Template description, e.g. "Gain {Block:diff()} Block."
    rules_text: str = ""            # Description plus card keywords as game rules text.
    upgraded_description: str = ""
    upgraded_rules_text: str = ""
    upgraded_cost: int | None = None
    base_vars: tuple[tuple[str, int | float], ...] = ()  # (var_name, value) pairs from upstream vars
    upgrade_raw: tuple[tuple[str, str | int | bool], ...] = ()  # Raw upgrade dict as tuple pairs
    base_cost: int | None = None    # Numeric base cost from upstream JSON


class CardLookup:
    """O(1) card lookup by name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._cards: dict[str, CardKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        meta_path = data_dir / "cards.md"
        behav_path = data_dir / "card-behaviors.md"

        meta_by_name: dict[str, dict[str, str]] = {}
        if meta_path.exists():
            for row in parse_md_table(meta_path):
                meta_by_name[row["Name"].lower()] = row

        behav_by_name: dict[str, dict[str, str]] = {}
        if behav_path.exists():
            for row in parse_md_table(behav_path):
                behav_by_name[row["Name"].lower()] = row

        all_names = set(meta_by_name.keys()) | set(behav_by_name.keys())
        for name_lower in all_names:
            m = meta_by_name.get(name_lower, {})
            b = behav_by_name.get(name_lower, {})
            display_name = m.get("Name") or b.get("Name", name_lower)
            self._cards[name_lower] = CardKnowledge(
                name=display_name,
                cost=m.get("Cost", ""),
                type=m.get("Type", ""),
                rarity=m.get("Rarity", ""),
                target=m.get("Target", ""),
                on_play=b.get("OnPlay", ""),
                on_upgrade=b.get("OnUpgrade", ""),
                vars=b.get("Vars", ""),
            )

        # Enrich with upstream JSON
        json_path = data_dir / "upstream" / "cards_dll.json"
        if not json_path.exists():
            json_path = data_dir / "upstream" / "cards.json"
        if json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    upstream = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load upstream cards: %s", exc)
                return
            enriched = 0
            for entry in upstream:
                uname = entry.get("name", "")
                key = uname.lower().rstrip("+")
                existing = self._cards.get(key)
                if existing is None:
                    # Try without spaces (cards.md uses "deadlypoison" not "deadly poison")
                    key = key.replace(" ", "")
                    existing = self._cards.get(key)
                pa = tuple(
                    (p.get("power", ""), p.get("amount", 0))
                    for p in (entry.get("powers_applied") or [])
                )
                sc = tuple(entry.get("spawns_cards") or [])
                ud = tuple(
                    (k, str(v))
                    for k, v in (entry.get("upgrade") or {}).items()
                )
                hc = entry.get("hit_count")
                desc = entry.get("description", "")
                desc_raw = entry.get("description_raw", "")
                rules_text = entry.get("rules_text", "")
                upgraded_desc = entry.get("upgraded_description", "")
                upgraded_rules = entry.get("upgraded_rules_text", "")
                upgraded_cost = entry.get("upgraded_cost")
                if not isinstance(upgraded_cost, int):
                    upgraded_cost = None
                raw_vars = entry.get("vars") or {}
                bv = tuple((k, v) for k, v in raw_vars.items() if isinstance(v, (int, float)))
                raw_upg = entry.get("upgrade") or {}
                ur = tuple((k, v) for k, v in raw_upg.items())
                bc = entry.get("cost")
                if not isinstance(bc, int):
                    bc = None
                if existing is None:
                    existing = CardKnowledge(
                        name=uname,
                        cost=str(entry.get("cost", "")),
                        type=entry.get("type", ""),
                        rarity=entry.get("rarity", ""),
                        target=entry.get("target", ""),
                    )
                self._cards[key] = CardKnowledge(
                    name=existing.name,
                    cost=existing.cost,
                    type=existing.type,
                    rarity=existing.rarity,
                    target=existing.target,
                    on_play=existing.on_play,
                    on_upgrade=existing.on_upgrade,
                    vars=existing.vars,
                    powers_applied=pa,
                    spawns_cards=sc,
                    upgrade_deltas=ud,
                    base_hit_count=hc,
                    description=desc,
                    description_raw=desc_raw,
                    rules_text=rules_text,
                    upgraded_description=upgraded_desc,
                    upgraded_rules_text=upgraded_rules,
                    upgraded_cost=upgraded_cost,
                    base_vars=bv,
                    upgrade_raw=ur,
                    base_cost=bc,
                )
                enriched += 1
            logger.info("Enriched %d cards with upstream JSON data", enriched)

    def get(self, card_name: str) -> CardKnowledge | None:
        """Lookup by card name (case-insensitive, strips '+' suffix)."""
        key = card_name.rstrip("+").lower()
        result = self._cards.get(key)
        if result is None:
            result = self._cards.get(key.replace(" ", ""))
        return result

    def get_mechanic_summary(self, card_name: str) -> str | None:
        """Get a compact mechanic summary for prompt injection.

        Returns None if card not found or has no behavior data.
        """
        card = self.get(card_name)
        if not card or not card.on_play:
            return None
        parts = [f"{card.name}:"]
        if card.vars:
            parts.append(f"[{card.vars}]")
        parts.append(card.on_play)
        is_upgraded = card_name.rstrip().endswith("+")
        if is_upgraded and card.on_upgrade:
            parts.append(f"Upgraded: {card.on_upgrade}")
        return " ".join(parts)

    def get_enrichment_summary(self, card_name: str) -> str | None:
        """Return structured effect info for card reward/shop prompts."""
        card = self.get(card_name)
        if card is None:
            return None
        parts = []
        if card.powers_applied:
            effects = ", ".join(
                f"{amount} {_humanize_identifier(power)}"
                for power, amount in card.powers_applied
            )
            parts.append(f"Applies: {effects}")
        if card.spawns_cards:
            parts.append(
                f"Creates: {', '.join(_humanize_identifier(spawn) for spawn in card.spawns_cards)}"
            )
        if card.upgrade_deltas:
            deltas = ", ".join(
                _format_upgrade_delta(name, delta)
                for name, delta in card.upgrade_deltas
            )
            parts.append(f"Upgrade: {deltas}")
        return " | ".join(parts) if parts else None

    def get_upgrade_preview(self, card_name: str) -> tuple[int | None, str, list[str]] | None:
        """Compute what a card looks like after upgrading.

        Returns (new_cost_or_None, upgraded_description, special_flags) or None
        if the card has no upgrade data.  *new_cost* is only set when the
        upgrade explicitly changes cost; otherwise None (cost unchanged).
        """
        card = self.get(card_name)
        if card is None or not card.upgrade_raw:
            return None

        if card.upgraded_rules_text or card.upgraded_description:
            return (
                card.upgraded_cost if card.upgraded_cost != card.base_cost else None,
                _strip_bbcode(card.upgraded_rules_text or card.upgraded_description),
                [],
            )

        upgrade_dict: dict[str, str | int | bool] = dict(card.upgrade_raw)
        base_vars: dict[str, int | float] = dict(card.base_vars)

        # Compute upgraded vars
        upgraded_vars: dict[str, int | float] = dict(base_vars)
        special_flags: list[str] = []
        new_cost: int | None = None

        for key, delta in upgrade_dict.items():
            key_lower = key.lower()
            # Boolean flags
            if isinstance(delta, bool) and delta:
                flag_name = key.replace("add_", "").replace("_", " ").title()
                special_flags.append(flag_name)
                continue
            # Cost change (absolute value)
            if key_lower == "cost":
                new_cost = int(delta) if not isinstance(delta, bool) else None
                continue
            # Numeric delta: find matching var(s).  Upstream upgrade keys are often
            # short forms of the actual var name (e.g. "poison" → "PoisonPower",
            # "damage" → "Damage").  Apply to ALL vars whose lowercase name starts
            # with the key — e.g. "poison" updates both "Poison" and "PoisonPower".
            matched_vars: list[str] = []
            for var_name in upgraded_vars:
                vn_lower = var_name.lower()
                if vn_lower == key_lower or vn_lower.startswith(key_lower):
                    matched_vars.append(var_name)
            for matched_var in matched_vars:
                if isinstance(delta, str) and delta.startswith(("+", "-")):
                    upgraded_vars[matched_var] = upgraded_vars[matched_var] + int(delta)
                elif isinstance(delta, (int, float)):
                    upgraded_vars[matched_var] = delta

        # Generate upgraded description from description_raw template
        desc = self._substitute_template(card.description_raw, upgraded_vars)
        if not desc:
            # Fallback: use base description as-is
            desc = _strip_bbcode(card.description) if card.description else ""

        # Prepend special flags
        if special_flags:
            prefix = ". ".join(special_flags) + ". "
            desc = prefix + desc

        return (new_cost, desc, special_flags)

    @staticmethod
    def _substitute_template(desc_raw: str, upgraded_vars: dict[str, int | float]) -> str:
        """Substitute {VarName:diff()} patterns in description_raw with values."""
        if not desc_raw:
            return ""

        def _replace_diff(m: re.Match) -> str:
            var_name = m.group(1)
            val = upgraded_vars.get(var_name)
            return str(int(val)) if val is not None else m.group(0)

        def _replace_plural(m: re.Match) -> str:
            var_name = m.group(1)
            singular = m.group(2)
            plural_form = m.group(3)
            val = upgraded_vars.get(var_name)
            if val is not None and int(val) == 1:
                return singular
            # Substitute nested {VarName:diff()} in the plural form
            return re.sub(r"\{(\w+):diff\(\)\}", _replace_diff, plural_form)

        # Handle plural patterns first: {Var:plural:singular|plural_form}
        # The plural form may contain nested {Var:diff()} — use alternation for balanced braces
        result = re.sub(
            r"\{(\w+):plural:(\w+)\|((?:[^{}]|\{[^{}]*\})*)\}",
            _replace_plural,
            desc_raw,
        )
        # Then simple {VarName:diff()} patterns
        result = re.sub(r"\{(\w+):diff\(\)\}", _replace_diff, result)

        return _strip_bbcode(result)

    @property
    def count(self) -> int:
        return len(self._cards)
