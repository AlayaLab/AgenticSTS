"""Generate STS2 card knowledge from the local game DLL.

This is the local replacement for the card half of the Spire Codex data flow:

1. decompile ``sts2.dll`` with ``ilspycmd``;
2. parse ``MegaCrit.Sts2.Core.Models.Cards`` and ``CardPools`` C# classes;
3. optionally merge localization/display fields from an existing cards.json.

The DLL contains authoritative mechanics: cost, type, rarity, target, dynamic
vars, upgrades, generated cards, powers, keywords, and card-pool membership.
Human-facing names/descriptions live in the Godot PCK localization resources,
so this script keeps those as an optional merge until we add a local PCK
extractor.

Usage:
    python -m scripts.generate_cards_from_dll
    python -m scripts.generate_cards_from_dll --force
    python -m scripts.generate_cards_from_dll --decompiled-dir extraction/decompiled
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DLL = Path(
    "C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2/"
    "data_sts2_windows_x86_64/sts2.dll"
)
DEFAULT_OUTPUT = Path("data/knowledge/upstream/cards_dll.json")
DEFAULT_LOCALIZATION = Path("data/knowledge/localization/eng/cards.json")
FALLBACK_LOCALIZATION = Path("data/knowledge/upstream/cards.json")

CARD_NS_DIR = Path("MegaCrit.Sts2.Core.Models.Cards")
POOL_NS_DIR = Path("MegaCrit.Sts2.Core.Models.CardPools")


def _run(cmd: list[str], timeout: int = 120) -> None:
    logger.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, timeout=timeout)


def _find_ilspy() -> str:
    configured = os.environ.get("ILSPY")
    if configured:
        return configured
    found = shutil.which("ilspycmd")
    if found:
        return found
    user_tool = Path.home() / ".dotnet" / "tools" / "ilspycmd.exe"
    if user_tool.exists():
        return str(user_tool)
    return "ilspycmd"


def decompile_dll(dll: Path, output_dir: Path, force: bool = False) -> Path:
    cards_dir = output_dir / CARD_NS_DIR
    if cards_dir.exists() and any(cards_dir.glob("*.cs")) and not force:
        return output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    _run([_find_ilspy(), str(dll), "-p", "-o", str(output_dir)], timeout=240)
    return output_dir


def _pascal_words(value: str) -> list[str]:
    return re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]?[a-z]+|\d+", value)


def class_to_id(class_name: str) -> str:
    return "_".join(word.upper() for word in _pascal_words(class_name))


def class_to_name(class_name: str) -> str:
    return " ".join(_pascal_words(class_name))


def _clean_number(value: str) -> int | float | None:
    value = value.strip().rstrip(")").rstrip("mMfF")
    try:
        parsed = float(value)
    except ValueError:
        return None
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _split_args(text: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            current.append(ch)
        elif ch in "([{":
            depth += 1
            current.append(ch)
        elif ch in ")]}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        args.append(tail)
    return args


_VAR_DEFAULT_NAMES = {
    "DamageVar": "Damage",
    "BlockVar": "Block",
    "CardsVar": "Cards",
    "ExtraDamageVar": "ExtraDamage",
    "CalculationBaseVar": "CalculationBase",
    "CalculationExtraVar": "CalculationExtra",
    "AmountVar": "Amount",
    "MagicNumberVar": "MagicNumber",
    "HealingVar": "Healing",
    "HpLossVar": "HpLoss",
    "EnergyVar": "Energy",
}


def _parse_dynamic_vars(code: str) -> dict[str, int | float]:
    vars_out: dict[str, int | float] = {}
    for match in re.finditer(r"new\s+(\w+Var)(?:<(?P<generic>[^>]+)>)?\(([^;\n{}]*)\)", code):
        var_type = match.group(1)
        generic = match.group("generic")
        args = _split_args(match.group(3))
        if not args:
            continue
        name = _VAR_DEFAULT_NAMES.get(var_type, var_type.removesuffix("Var"))
        if generic and var_type == "PowerVar":
            name = generic
        value_arg = args[0]
        if value_arg.startswith('"') and value_arg.endswith('"'):
            name = value_arg.strip('"')
            if len(args) < 2:
                continue
            value_arg = args[1]
        value = _clean_number(value_arg)
        if value is not None:
            vars_out[name] = value
    if (
        "CalculatedDamage" not in vars_out
        and "CalculationBase" in vars_out
        and "ExtraDamage" in vars_out
    ):
        vars_out["CalculatedDamage"] = vars_out["CalculationBase"] + vars_out["ExtraDamage"]
    return vars_out


def _parse_ctor(code: str) -> tuple[int | None, str | None, str | None, str | None]:
    match = re.search(
        r":\s*base\((?P<cost>[^,]+),\s*CardType\.(?P<type>\w+),\s*"
        r"CardRarity\.(?P<rarity>\w+),\s*TargetType\.(?P<target>\w+)\)",
        code,
        flags=re.S,
    )
    if not match:
        return None, None, None, None
    cost = _clean_number(match.group("cost"))
    return (
        cost if isinstance(cost, int) else None,
        match.group("type"),
        match.group("rarity"),
        match.group("target"),
    )


def _parse_upgrade(code: str, base_cost: int | None) -> dict[str, Any] | None:
    match = re.search(
        r"protected override void OnUpgrade\(\)\s*\{(?P<body>.*?)^\s*\}",
        code,
        flags=re.S | re.M,
    )
    if not match:
        return None
    body = match.group("body")
    upgrade: dict[str, Any] = {}
    cost_match = re.search(r"EnergyCost\.UpgradeBy\(([-\d.mMfF]+)\)", body)
    if cost_match and base_cost is not None:
        delta = _clean_number(cost_match.group(1))
        if isinstance(delta, int):
            upgrade["cost"] = base_cost + delta
    for dyn_match in re.finditer(
        r"DynamicVars(?:\.(?P<dot>\w+)|\[\s*\"(?P<bracket>[^\"]+)\"\s*\])"
        r"\.UpgradeValueBy\((?P<delta>[-\d.mMfF]+)\)",
        body,
    ):
        name = dyn_match.group("dot") or dyn_match.group("bracket")
        delta = _clean_number(dyn_match.group("delta"))
        if delta is not None:
            sign = "+" if delta > 0 else ""
            upgrade[name.lower()] = f"{sign}{delta:g}"
    added_keywords = sorted(set(re.findall(r"AddKeyword\(CardKeyword\.(\w+)\)", body)))
    if added_keywords:
        upgrade["keywords"] = added_keywords
    return upgrade or None


def _parse_keywords(code: str) -> list[str] | None:
    values = sorted(set(re.findall(r"CardKeyword\.(\w+)", code)))
    return values or None


def _parse_tags(code: str) -> list[str] | None:
    values = sorted(set(re.findall(r"CardTag\.(\w+)", code)))
    return values or None


def _parse_multiplayer_constraint(code: str) -> str:
    match = re.search(
        r"MultiplayerConstraint\s*=>\s*CardMultiplayerConstraint\.(\w+)",
        code,
    )
    return match.group(1) if match else "None"


def _parse_generated_cards(code: str) -> list[str] | None:
    names = set(re.findall(r"\b([A-Z]\w+)\.CreateInHand\(", code))
    names.update(re.findall(r"CreateInHand<([A-Z]\w+)>\(", code))
    names.update(re.findall(r"CreateIn(?:DrawPile|DiscardPile)<([A-Z]\w+)>\(", code))
    return sorted(class_to_id(name) for name in names) or None


def _resolve_amount(expr: str, vars_by_name: dict[str, int | float]) -> int | float | str | None:
    expr = expr.strip()
    literal = _clean_number(expr)
    if literal is not None:
        return literal
    bracket = re.search(r'DynamicVars\[\s*"([^"]+)"\s*\]', expr)
    if bracket:
        return vars_by_name.get(bracket.group(1))
    dot = re.search(r"DynamicVars\.(\w+)", expr)
    if dot:
        name = dot.group(1)
        return vars_by_name.get(name) or vars_by_name.get(f"{name}Power")
    if "ResolveEnergyXValue" in expr:
        return "X"
    if expr.startswith("-"):
        resolved = _resolve_amount(expr[1:], vars_by_name)
        if isinstance(resolved, (int, float)):
            return -resolved
    return None


def _parse_powers(code: str, vars_by_name: dict[str, int | float]) -> list[dict[str, Any]] | None:
    powers: list[dict[str, Any]] = []
    for match in re.finditer(r"PowerCmd\.Apply<(?P<power>\w+)>\((?P<args>.*?)\);", code, re.S):
        args = _split_args(match.group("args"))
        amount = _resolve_amount(args[1], vars_by_name) if len(args) > 1 else None
        powers.append({"power": match.group("power").removesuffix("Power"), "amount": amount})
    return powers or None


def _parse_numeric_effects(code: str, vars_by_name: dict[str, int | float]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "DamageCmd.Attack" in code and "Damage" in vars_by_name:
        out["damage"] = vars_by_name["Damage"]
    elif "DamageCmd.Attack" in code and "CalculationBase" in vars_by_name:
        out["damage"] = vars_by_name["CalculationBase"]
    if "CreatureCmd.GainBlock" in code and "Block" in vars_by_name:
        out["block"] = vars_by_name["Block"]
    hit_match = re.search(r"\.WithHitCount\(([^)]+)\)", code)
    if hit_match:
        out["hit_count"] = _resolve_amount(hit_match.group(1), vars_by_name)
    draw_match = re.search(r"CardCmd\.Draw\([^,]+,\s*([^)]+)\)", code)
    if draw_match:
        out["cards_draw"] = _resolve_amount(draw_match.group(1), vars_by_name)
    energy_match = re.search(r"GainEnergy\([^,]+,\s*([^)]+)\)", code)
    if energy_match:
        out["energy_gain"] = _resolve_amount(energy_match.group(1), vars_by_name)
    hp_match = re.search(r"(?:LoseHp|LoseHealth|Damage)\([^,]+,\s*([^)]+)\)", code)
    if hp_match and "Unblockable" in code:
        out["hp_loss"] = _resolve_amount(hp_match.group(1), vars_by_name)
    return out


def _parse_scaling(code: str, vars_by_name: dict[str, int | float]) -> dict[str, Any] | None:
    if "CardDrawnEntry" in code and "WithMultiplier" in code:
        return {
            "dimension": "cards_drawn_this_combat",
            "amount_per": vars_by_name.get("ExtraDamage"),
        }
    return None


def _apply_upgrade(
    vars_by_name: dict[str, int | float],
    cost: int | None,
    keywords: list[str] | None,
    upgrade: dict[str, Any] | None,
) -> tuple[dict[str, int | float], int | None, list[str] | None]:
    upgraded_vars = dict(vars_by_name)
    upgraded_cost = cost
    upgraded_keywords = set(keywords or [])
    if not upgrade:
        return upgraded_vars, upgraded_cost, sorted(upgraded_keywords) or None

    for key, delta in upgrade.items():
        key_lower = key.lower()
        if key_lower == "cost" and isinstance(delta, int):
            upgraded_cost = delta
            continue
        if key_lower == "keywords" and isinstance(delta, list):
            upgraded_keywords.update(str(item) for item in delta)
            continue
        matched = [
            name for name in upgraded_vars
            if name.lower() == key_lower or name.lower().startswith(key_lower)
        ]
        for name in matched:
            if isinstance(delta, str) and delta.startswith(("+", "-")):
                upgraded_vars[name] += int(delta)
            elif isinstance(delta, (int, float)):
                upgraded_vars[name] = delta
    return upgraded_vars, upgraded_cost, sorted(upgraded_keywords) or None


def _compose_rules_text(description: str | None, keywords: list[str] | None) -> str | None:
    if description is None:
        return None
    text = description.strip()
    keyword_set = set(keywords or [])
    prefixes = [kw for kw in ("Sly", "Innate", "Ethereal") if kw in keyword_set and kw not in text]
    suffixes = [kw for kw in ("Exhaust", "Retain") if kw in keyword_set and kw not in text]
    if prefixes:
        text = ". ".join(prefixes) + ". " + text
    if suffixes:
        end = "" if text.endswith(".") else "."
        text = text + end + " " + ". ".join(suffixes) + "."
    return text


def parse_card_source(path: Path) -> dict[str, Any] | None:
    code = path.read_text(encoding="utf-8")
    class_match = re.search(r"public (?:sealed\s+)?class (\w+)\s*:\s*CardModel", code)
    if not class_match:
        return None
    class_name = class_match.group(1)
    cost, card_type, rarity, target = _parse_ctor(code)
    vars_by_name = _parse_dynamic_vars(code)
    entry: dict[str, Any] = {
        "id": class_to_id(class_name),
        "class_name": class_name,
        "name": class_to_name(class_name),
        "description": None,
        "description_raw": None,
        "rules_text": None,
        "cost": cost,
        "is_x_cost": "HasEnergyCostX => true" in code,
        "is_x_star_cost": "HasStarCostX => true" in code,
        "star_cost": None,
        "type": card_type,
        "rarity": rarity,
        "target": target,
        "color": None,
        "damage": None,
        "block": None,
        "hit_count": None,
        "powers_applied": _parse_powers(code, vars_by_name),
        "cards_draw": None,
        "energy_gain": None,
        "hp_loss": None,
        "keywords": _parse_keywords(code),
        "tags": _parse_tags(code),
        "multiplayer_constraint": _parse_multiplayer_constraint(code),
        "spawns_cards": _parse_generated_cards(code),
        "vars": vars_by_name or None,
        "scaling": _parse_scaling(code, vars_by_name),
        "upgrade": _parse_upgrade(code, cost),
        "upgraded_cost": None,
        "upgraded_vars": None,
        "upgraded_keywords": None,
        "upgraded_description": None,
        "upgraded_rules_text": None,
        "beta_image_url": None,
    }
    entry.update(_parse_numeric_effects(code, vars_by_name))
    return entry


def _parse_pool_title(code: str, fallback: str) -> str:
    title = re.search(r'Title\s*=>\s*"([^"]+)"', code)
    if title:
        return title.group(1)
    return fallback.removesuffix("CardPool").lower()


def parse_card_pools(root: Path) -> dict[str, str]:
    pools_dir = root / POOL_NS_DIR
    colors: dict[str, str] = {}
    if not pools_dir.exists():
        return colors
    for path in pools_dir.glob("*CardPool.cs"):
        code = path.read_text(encoding="utf-8")
        pool = _parse_pool_title(code, path.stem)
        for card in re.findall(r"ModelDb\.Card<(\w+)>\(\)", code):
            colors[card] = pool
    return colors


def load_localization(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    by_class: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict):
        ids = sorted({key.rsplit(".", 1)[0] for key in data if "." in key})
        for card_id in ids:
            class_guess = "".join(part.title() for part in card_id.lower().split("_"))
            by_class[class_guess] = {
                "id": card_id,
                "name": data.get(f"{card_id}.title", ""),
                "description_raw": data.get(f"{card_id}.description", ""),
            }
    else:
        for entry in data:
            card_id = str(entry.get("id", ""))
            class_guess = "".join(part.title() for part in card_id.lower().split("_"))
            by_class[class_guess] = entry
    return by_class


def _render_description_template(template: str, vars_by_name: dict[str, Any] | None) -> str:
    if not template or not vars_by_name:
        return template
    placeholder = "\x00VALUE\x00"
    template = template.replace("{}", placeholder)

    def replace_plural(match: re.Match[str]) -> str:
        name, singular, plural = match.group(1), match.group(2), match.group(3)
        value = vars_by_name.get(name)
        selected = singular if value == 1 else plural
        return selected.replace(placeholder, str(value))

    rendered = re.sub(r"\{(\w+):plural:([^|{}]+)\|([^{}]+)\}", replace_plural, template)

    def replace_value(match: re.Match[str]) -> str:
        name = match.group(1)
        value = vars_by_name.get(name)
        return str(value) if value is not None else match.group(0)

    rendered = re.sub(r"\{(\w+)(?::[^{}]*)?\}", replace_value, rendered)
    return rendered.replace(placeholder, "")


def merge_display_fields(entry: dict[str, Any], localized: dict[str, Any]) -> dict[str, Any]:
    merged = dict(entry)
    for key in ("id", "name", "description_raw", "color", "beta_image_url"):
        if localized.get(key) not in (None, ""):
            merged[key] = localized[key]
    if localized.get("description_raw"):
        merged["description"] = _render_description_template(
            localized["description_raw"],
            entry.get("vars"),
        )
    elif localized.get("description"):
        merged["description"] = localized["description"]
    merged["rules_text"] = _compose_rules_text(merged.get("description"), merged.get("keywords"))

    vars_by_name = entry.get("vars") or {}
    upgraded_vars, upgraded_cost, upgraded_keywords = _apply_upgrade(
        vars_by_name,
        entry.get("cost"),
        entry.get("keywords"),
        entry.get("upgrade"),
    )
    if entry.get("upgrade"):
        merged["upgraded_cost"] = upgraded_cost
        merged["upgraded_vars"] = upgraded_vars or None
        merged["upgraded_keywords"] = upgraded_keywords
        raw = merged.get("description_raw")
        if raw:
            merged["upgraded_description"] = _render_description_template(raw, upgraded_vars)
        else:
            merged["upgraded_description"] = merged.get("description")
        merged["upgraded_rules_text"] = _compose_rules_text(
            merged.get("upgraded_description"),
            upgraded_keywords,
        )
    return merged


def generate_cards(root: Path, localization_json: Path | None = DEFAULT_LOCALIZATION) -> list[dict[str, Any]]:
    localized = load_localization(localization_json)
    colors = parse_card_pools(root)
    cards_dir = root / CARD_NS_DIR
    cards: list[dict[str, Any]] = []
    for path in sorted(cards_dir.glob("*.cs")):
        entry = parse_card_source(path)
        if entry is None:
            continue
        entry["color"] = colors.get(entry["class_name"])
        entry = merge_display_fields(entry, localized.get(entry["class_name"], {}))
        cards.append(entry)
    return cards


def needs_update(dll: Path, output: Path, localization_json: Path | None = DEFAULT_LOCALIZATION) -> bool:
    if not output.exists():
        return True
    try:
        if dll.stat().st_mtime > output.stat().st_mtime:
            return True
        return bool(
            localization_json
            and localization_json.exists()
            and localization_json.stat().st_mtime > output.stat().st_mtime
        )
    except OSError:
        return True


def run(
    dll: Path = DEFAULT_DLL,
    output: Path = DEFAULT_OUTPUT,
    localization_json: Path | None = DEFAULT_LOCALIZATION,
    force: bool = False,
) -> bool:
    """Generate and cache card knowledge. Returns True on success or if already fresh."""
    if not dll.exists():
        logger.warning("STS2 DLL not found at %s — skipping card extraction", dll)
        return False
    if localization_json == DEFAULT_LOCALIZATION and not localization_json.exists():
        localization_json = FALLBACK_LOCALIZATION

    if not force and not needs_update(dll, output, localization_json):
        logger.debug("cards_dll.json is up to date")
        return True

    with tempfile.TemporaryDirectory(prefix="sts2_ilspy_cards_") as temp:
        root = Path(temp)
        decompile_dll(dll, root, force=True)
        cards = generate_cards(root, localization_json=localization_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(cards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.info("Wrote %d cards to %s", len(cards), output)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll-path", type=Path, default=DEFAULT_DLL)
    parser.add_argument("--decompiled-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--localization-json", type=Path, default=DEFAULT_LOCALIZATION)
    parser.add_argument("--no-localization", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-decompiled", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s: %(message)s")

    if args.decompiled_dir is None:
        ok = run(
            dll=args.dll_path,
            output=args.output,
            localization_json=None if args.no_localization else args.localization_json,
            force=args.force,
        )
        raise SystemExit(0 if ok else 1)
    else:
        root = decompile_dll(args.dll_path, args.decompiled_dir, force=args.force)
        localization = None if args.no_localization else args.localization_json
        cards = generate_cards(root, localization_json=localization)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(cards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.info("Wrote %d cards to %s", len(cards), args.output)

    if args.keep_decompiled:
        kept = args.output.parent / "decompiled_cards_source"
        if kept.exists():
            shutil.rmtree(kept)
        shutil.copytree(root, kept)
        logger.info("Kept decompiled source at %s", kept)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        logger.error("Card extraction failed: %s", exc)
        sys.exit(1)
