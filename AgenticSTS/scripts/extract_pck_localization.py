"""Extract STS2 localization JSON from the local Godot PCK with GDRETools.

The output is intentionally raw game localization, not Spire Codex shaped data.
Knowledge generators merge these title/description templates with mechanics
parsed from ``sts2.dll``.

Usage:
    python -m scripts.extract_pck_localization
    python -m scripts.extract_pck_localization --force
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PCK = Path("C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.pck")
DEFAULT_OUTPUT = Path("data/knowledge")
DEFAULT_LOCALE = "eng"

LOCALIZATION_FILES = (
    "cards.json",
    "relics.json",
    "potions.json",
    "card_keywords.json",
    "afflictions.json",
    "enchantments.json",
    "powers.json",
    "intents.json",
    "events.json",
    "monsters.json",
)


def find_gdre_tools() -> str:
    configured = os.environ.get("GDRE_TOOLS")
    if configured:
        return configured
    found = shutil.which("gdre_tools") or shutil.which("gdre_tools.exe")
    if found:
        return found
    local_root = Path(os.environ.get("LOCALAPPDATA", "")) / "CodexTools" / "GDRETools"
    candidates = sorted(local_root.glob("*/gdre_tools.exe"), reverse=True)
    if candidates:
        return str(candidates[0])
    return "gdre_tools"


def needs_update(pck: Path, output_dir: Path, locale: str = DEFAULT_LOCALE) -> bool:
    try:
        pck_mtime = pck.stat().st_mtime
    except OSError:
        return True
    for name in LOCALIZATION_FILES:
        target = output_dir / locale / name
        if not target.exists():
            return True
        try:
            if pck_mtime > target.stat().st_mtime:
                return True
        except OSError:
            return True
    return False


def run(
    pck: Path = DEFAULT_PCK,
    output_dir: Path = DEFAULT_OUTPUT,
    locale: str = DEFAULT_LOCALE,
    force: bool = False,
) -> bool:
    if not pck.exists():
        logger.warning("STS2 PCK not found at %s — skipping localization extraction", pck)
        return False
    if not force and not needs_update(pck, output_dir, locale):
        logger.debug("PCK localization cache is up to date")
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        find_gdre_tools(),
        "--headless",
        f"--extract={pck}",
        f"--output={output_dir}",
        "--no-header",
    ]
    for name in LOCALIZATION_FILES:
        cmd.append(f"--include=res://localization/{locale}/{name}")

    logger.info("Extracting STS2 localization from PCK")
    subprocess.run(cmd, check=True, timeout=180)
    logger.info("Wrote localization files to %s", output_dir / locale)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pck-path", type=Path, default=DEFAULT_PCK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--locale", default=DEFAULT_LOCALE)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    ok = run(args.pck_path, args.output_dir, args.locale, args.force)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        logger.error("PCK localization extraction failed: %s", exc)
        sys.exit(1)
