"""One-time migration: backfill trigger fields for existing evolved skills.

Scans data/skills/skills.json for evolved skills that mention specific card
or enemy names in their content but lack the corresponding trigger fields.
Auto-fills requires_cards and enemy_names based on content analysis.

Usage:
    python -m scripts.backfill_skill_triggers [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.knowledge.knowledge import GameKnowledge
from src.storage import paths

# Common card names that appear in English prose — skip auto-detect
_CARD_NAME_STOPLIST = frozenset({
    "strike", "defend", "block", "bash", "zap", "dualcast",
})


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    skills_path = paths.skills_file()
    if not skills_path.exists():
        print(f"Skills file not found: {skills_path}")
        return

    with open(skills_path, encoding="utf-8") as f:
        skills = json.load(f)

    kb = GameKnowledge.get_instance()

    # Build name sets
    card_names: dict[str, str] = {}  # lowercase -> display name
    for card in kb.cards._cards.values():
        if len(card.name) >= 5 and card.name.lower() not in _CARD_NAME_STOPLIST:
            card_names[card.name.lower()] = card.name

    import re

    enemy_names: dict[str, str] = {}  # lowercase -> display name
    for monster in kb.monsters._monsters.values():
        if len(monster.name) >= 4:
            enemy_names[monster.name.lower()] = monster.name
            # Also add space-separated form (PhrogParasite -> phrog parasite)
            spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", monster.name).lower()
            if spaced != monster.name.lower():
                enemy_names[spaced] = monster.name

    updated_count = 0

    for skill in skills:
        if skill.get("source") != "evolved":
            continue

        skill_name_lower = skill.get("name", "").lower()
        content_lower = skill.get("content", "").lower()
        trigger = skill.get("trigger", {})
        existing_cards = set(trigger.get("requires_cards", []))
        existing_enemies = set(trigger.get("enemy_names", []))

        changes = []

        # Auto-detect card names — ONLY if card name appears in skill name
        # Uses word boundary to avoid "Patter" matching "pattern"
        if not existing_cards:
            detected_cards = []
            for name_lower, display_name in card_names.items():
                pattern = r"\b" + re.escape(name_lower) + r"\b"
                if re.search(pattern, skill_name_lower):
                    detected_cards.append(display_name)
            if detected_cards:
                trigger["requires_cards"] = sorted(detected_cards)
                changes.append(f"requires_cards={detected_cards}")

        # Auto-detect enemy names — check both name and content
        if not existing_enemies:
            text = f"{skill_name_lower} {content_lower}"
            detected_enemies = []
            for name_lower, display_name in enemy_names.items():
                if name_lower in text:
                    detected_enemies.append(display_name)
            if detected_enemies:
                trigger["enemy_names"] = sorted(detected_enemies)
                changes.append(f"enemy_names={detected_enemies}")

        if changes:
            skill["trigger"] = trigger
            updated_count += 1
            print(f"  [{skill['skill_id'][:8]}] {skill['name']}: {', '.join(changes)}")

    print(f"\nTotal: {updated_count} skills updated out of {len(skills)}")

    if dry_run:
        print("(dry run — no changes written)")
    else:
        with open(skills_path, "w", encoding="utf-8") as f:
            json.dump(skills, f, indent=2, ensure_ascii=False)
        print(f"Written to {skills_path}")


if __name__ == "__main__":
    main()
