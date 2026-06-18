"""Generate STS2 relic and potion knowledge from local DLL + PCK localization."""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from scripts.generate_cards_from_dll import (
    DEFAULT_DLL,
    _parse_dynamic_vars,
    _parse_numeric_effects,
    _parse_powers,
    _render_description_template,
    class_to_id,
    class_to_name,
    decompile_dll,
)

logger = logging.getLogger(__name__)

DEFAULT_RELIC_OUTPUT = Path("data/knowledge/upstream/relics_dll.json")
DEFAULT_POTION_OUTPUT = Path("data/knowledge/upstream/potions_dll.json")
DEFAULT_RELIC_LOCALIZATION = Path("data/knowledge/localization/eng/relics.json")
DEFAULT_POTION_LOCALIZATION = Path("data/knowledge/localization/eng/potions.json")
FALLBACK_RELIC_LOCALIZATION = Path("data/knowledge/upstream/relics.json")
FALLBACK_POTION_LOCALIZATION = Path("data/knowledge/upstream/potions.json")

RELIC_NS_DIR = Path("MegaCrit.Sts2.Core.Models.Relics")
POTION_NS_DIR = Path("MegaCrit.Sts2.Core.Models.Potions")
RELIC_POOL_NS_DIR = Path("MegaCrit.Sts2.Core.Models.RelicPools")
POTION_POOL_NS_DIR = Path("MegaCrit.Sts2.Core.Models.PotionPools")


def _load_localization(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict):
        ids = sorted({key.rsplit(".", 1)[0] for key in data if "." in key})
        for item_id in ids:
            class_guess = "".join(part.title() for part in item_id.lower().split("_"))
            out[class_guess] = {
                "id": item_id,
                "name": data.get(f"{item_id}.title", ""),
                "description_raw": data.get(f"{item_id}.description", ""),
                "flavor": data.get(f"{item_id}.flavor", ""),
            }
    else:
        for entry in data:
            item_id = str(entry.get("id", ""))
            class_guess = "".join(part.title() for part in item_id.lower().split("_"))
            out[class_guess] = entry
    return out


def _merge_display(entry: dict[str, Any], localized: dict[str, Any]) -> dict[str, Any]:
    merged = dict(entry)
    for key in ("id", "name", "description_raw", "flavor", "image_url"):
        if localized.get(key) not in (None, ""):
            merged[key] = localized[key]
    if localized.get("description_raw"):
        merged["description"] = _render_description_template(
            localized["description_raw"],
            entry.get("vars"),
        )
    elif localized.get("description"):
        merged["description"] = localized["description"]
    return merged


def _parse_property(code: str, enum_name: str, property_name: str) -> str | None:
    match = re.search(rf"{property_name}\s*=>\s*{enum_name}\.(\w+)", code)
    return match.group(1) if match else None


def _parse_pool_title(path: Path, code: str, suffix: str) -> str:
    if path.stem == f"Shared{suffix}Pool":
        return "shared"
    if path.stem == f"Event{suffix}Pool":
        return "event"
    if path.stem == f"Deprecated{suffix}Pool":
        return "deprecated"
    if path.stem == f"Token{suffix}Pool":
        return "token"
    return path.stem.removesuffix(f"{suffix}Pool").lower()


def _parse_modeldb_pool(root: Path, pool_dir: Path, suffix: str, model_kind: str) -> dict[str, str]:
    pools: dict[str, str] = {}
    source_dir = root / pool_dir
    if not source_dir.exists():
        return pools
    for path in source_dir.glob(f"*{suffix}Pool.cs"):
        code = path.read_text(encoding="utf-8")
        pool = _parse_pool_title(path, code, suffix)
        for item in re.findall(rf"ModelDb\.{model_kind}<(\w+)>\(\)", code):
            pools[item] = pool
    return pools


def _parse_relic_source(path: Path, pool: str | None) -> dict[str, Any] | None:
    code = path.read_text(encoding="utf-8")
    class_match = re.search(r"public (?:sealed\s+)?class (\w+)\s*:\s*RelicModel", code)
    if not class_match:
        return None
    class_name = class_match.group(1)
    vars_by_name = _parse_dynamic_vars(code)
    entry: dict[str, Any] = {
        "id": class_to_id(class_name),
        "class_name": class_name,
        "name": class_to_name(class_name),
        "description": None,
        "description_raw": None,
        "flavor": "",
        "rarity": _parse_property(code, "RelicRarity", "Rarity"),
        "pool": pool,
        "vars": vars_by_name or None,
        "powers_applied": _parse_powers(code, vars_by_name),
        "image_url": None,
    }
    entry.update(_parse_numeric_effects(code, vars_by_name))
    return entry


def _parse_potion_source(path: Path, pool: str | None) -> dict[str, Any] | None:
    code = path.read_text(encoding="utf-8")
    class_match = re.search(r"public (?:sealed\s+)?class (\w+)\s*:\s*PotionModel", code)
    if not class_match:
        return None
    class_name = class_match.group(1)
    vars_by_name = _parse_dynamic_vars(code)
    entry: dict[str, Any] = {
        "id": class_to_id(class_name),
        "class_name": class_name,
        "name": class_to_name(class_name),
        "description": None,
        "description_raw": None,
        "rarity": _parse_property(code, "PotionRarity", "Rarity"),
        "usage": _parse_property(code, "PotionUsage", "Usage"),
        "target": _parse_property(code, "TargetType", "TargetType"),
        "pool": pool,
        "vars": vars_by_name or None,
        "powers_applied": _parse_powers(code, vars_by_name),
        "image_url": None,
    }
    entry.update(_parse_numeric_effects(code, vars_by_name))
    return entry


def generate_relics(
    root: Path,
    localization_json: Path | None = DEFAULT_RELIC_LOCALIZATION,
) -> list[dict[str, Any]]:
    if localization_json == DEFAULT_RELIC_LOCALIZATION and not localization_json.exists():
        localization_json = FALLBACK_RELIC_LOCALIZATION
    localized = _load_localization(localization_json)
    pools = _parse_modeldb_pool(root, RELIC_POOL_NS_DIR, "Relic", "Relic")
    relics: list[dict[str, Any]] = []
    for path in sorted((root / RELIC_NS_DIR).glob("*.cs")):
        entry = _parse_relic_source(path, pools.get(path.stem))
        if entry is None:
            continue
        relics.append(_merge_display(entry, localized.get(entry["class_name"], {})))
    return relics


def generate_potions(
    root: Path,
    localization_json: Path | None = DEFAULT_POTION_LOCALIZATION,
) -> list[dict[str, Any]]:
    if localization_json == DEFAULT_POTION_LOCALIZATION and not localization_json.exists():
        localization_json = FALLBACK_POTION_LOCALIZATION
    localized = _load_localization(localization_json)
    pools = _parse_modeldb_pool(root, POTION_POOL_NS_DIR, "Potion", "Potion")
    potions: list[dict[str, Any]] = []
    for path in sorted((root / POTION_NS_DIR).glob("*.cs")):
        entry = _parse_potion_source(path, pools.get(path.stem))
        if entry is None:
            continue
        potions.append(_merge_display(entry, localized.get(entry["class_name"], {})))
    return potions


def _newer(source: Path, target: Path) -> bool:
    try:
        return source.stat().st_mtime > target.stat().st_mtime
    except OSError:
        return True


def run(
    dll: Path = DEFAULT_DLL,
    relic_output: Path = DEFAULT_RELIC_OUTPUT,
    potion_output: Path = DEFAULT_POTION_OUTPUT,
    relic_localization: Path | None = DEFAULT_RELIC_LOCALIZATION,
    potion_localization: Path | None = DEFAULT_POTION_LOCALIZATION,
    force: bool = False,
) -> bool:
    if not dll.exists():
        logger.warning("STS2 DLL not found at %s — skipping item extraction", dll)
        return False
    if (
        not force
        and relic_output.exists()
        and potion_output.exists()
        and not _newer(dll, relic_output)
        and not _newer(dll, potion_output)
    ):
        logger.debug("relics_dll.json and potions_dll.json are up to date")
        return True

    with tempfile.TemporaryDirectory(prefix="sts2_ilspy_items_") as temp:
        root = Path(temp)
        decompile_dll(dll, root, force=True)
        relics = generate_relics(root, relic_localization)
        potions = generate_potions(root, potion_localization)
        relic_output.parent.mkdir(parents=True, exist_ok=True)
        relic_output.write_text(json.dumps(relics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        potion_output.parent.mkdir(parents=True, exist_ok=True)
        potion_output.write_text(json.dumps(potions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.info("Wrote %d relics to %s", len(relics), relic_output)
        logger.info("Wrote %d potions to %s", len(potions), potion_output)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll-path", type=Path, default=DEFAULT_DLL)
    parser.add_argument("--relic-output", type=Path, default=DEFAULT_RELIC_OUTPUT)
    parser.add_argument("--potion-output", type=Path, default=DEFAULT_POTION_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    ok = run(args.dll_path, args.relic_output, args.potion_output, force=args.force)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        logger.error("Item extraction failed: %s", exc)
        sys.exit(1)
