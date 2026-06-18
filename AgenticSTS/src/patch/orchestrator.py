"""High-level apply_patch flow: load manifest, snapshot, purge, rewrite, bump version."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path

from src.patch.manifest import Manifest, load_manifest
from src.patch.purge import (
    PurgeReport,
    purge_card_memories,
    purge_evolution_dir,
    purge_jsonl_card_builds,
    purge_jsonl_episodes,
    purge_jsonl_event_memories,
    purge_silent_card_notes,
    purge_skills,
    purge_guides,
)
from src.patch.review import apply_rewrites, print_review_batch
from src.patch.rewrite import LLMBackend, rewrite_file, scan_prompt_files
from src.patch.slug import slug
from src.patch.snapshot import snapshot_data
from src.patch.version import load_version_state


@dataclass
class ApplyPatchOptions:
    manifest_path: Path
    data_root: Path
    prompts_root: Path
    version_file: Path
    snapshot_root: Path
    seeds_root: Path = Path("src/skills/seeds")
    dry_run: bool = False
    backend: LLMBackend | None = None
    skip_llm: bool = False
    auto_apply: bool = False  # skip interactive confirmation before writing rewrites


@dataclass
class ApplyPatchReport:
    manifest: Manifest
    purge_reports: list[PurgeReport] = field(default_factory=list)
    rewrite_files_touched: int = 0
    snapshot_path: Path | None = None
    total_deleted: int = 0
    version_bumped: bool = False


def _compute_major_enemies(m: Manifest) -> set[str]:
    out: set[str] = set()
    for e in m.reworked_enemies:
        if e.severity != "major":
            continue
        out.add(slug(e.name))
        # Episodes for encounter-mates (same boss room) must be purged too —
        # their fight context was shaped by the now-reworked enemy.
        for rel in e.related_enemies:
            out.add(slug(rel))
    return out


def apply_patch(options: ApplyPatchOptions) -> ApplyPatchReport:
    manifest = load_manifest(options.manifest_path)
    report = ApplyPatchReport(manifest=manifest)

    changed = manifest.changed_entities()
    major_enemies = _compute_major_enemies(manifest)

    # Snapshot first (only in live mode)
    if not options.dry_run:
        label = f"{load_version_state(options.version_file).current.game_version}-pre-{manifest.game_version}"
        report.snapshot_path = snapshot_data(options.data_root, options.snapshot_root, label=label)

    # Phase 1: deterministic purge
    report.purge_reports.extend([
        purge_card_memories(options.data_root / "memory/v2/card_memories.json", changed, dry_run=options.dry_run),
        purge_jsonl_card_builds(options.data_root / "memory/v2/card_builds.jsonl", changed=changed, dry_run=options.dry_run),
        purge_jsonl_episodes(options.data_root / "memory/v2/combat_episodes.jsonl",
                              changed_major_enemies=major_enemies, changed_cards=changed, dry_run=options.dry_run),
        purge_jsonl_event_memories(options.data_root / "memory/v2/event_memories.jsonl",
                                    changed=changed, dry_run=options.dry_run),
        purge_skills(options.data_root / "skills/skills.json", changed=changed, dry_run=options.dry_run),
        purge_silent_card_notes(options.seeds_root / "silent_card_notes.json",
                                 changed=changed, dry_run=options.dry_run),
        purge_evolution_dir(options.data_root / "evolution", changed=changed, dry_run=options.dry_run),
        purge_guides(options.data_root / "memory/v2/guides.json", changed=changed, dry_run=options.dry_run),
    ])
    report.total_deleted = sum(r.deleted for r in report.purge_reports)

    # Phase 2: LLM rewrite (unless skipped)
    if not options.skip_llm and options.backend is not None and options.prompts_root.exists():
        targets = manifest.prompt_review_targets()
        requests = scan_prompt_files(options.prompts_root, targets=targets)
        manifest_context = _build_manifest_context(manifest)
        results = [rewrite_file(req, manifest_context=manifest_context, backend=options.backend)
                   for req in requests]
        if not options.dry_run:
            print_review_batch(results)
            # Interactive approval unless auto_apply or no changes
            changed_count = sum(1 for r in results if r.changed)
            if changed_count > 0 and not options.auto_apply:
                try:
                    response = input(f"\nApply all {changed_count} file rewrites? [y/N]: ").strip().lower()
                except EOFError:
                    response = ""
                if response != "y":
                    print("Rewrites skipped by user.")
                    results = []  # empty list → apply_rewrites does nothing
        report.rewrite_files_touched = apply_rewrites(results, dry_run=options.dry_run)

    # Phase 3: bump version
    if not options.dry_run:
        state = load_version_state(options.version_file)
        state.bump(
            new_game_version=manifest.game_version,
            new_mod_version=state.current.mod_version,
            verified_date=_dt.date.today().isoformat(),
            snapshot_path=str(report.snapshot_path) if report.snapshot_path else "",
        )
        state.save(options.version_file)
        report.version_bumped = True

    return report


def _build_manifest_context(m: Manifest) -> str:
    """Compact description of changes for LLM context."""
    lines: list[str] = [f"Game updated from {m.previous_version} to {m.game_version}.", ""]
    for c in m.removed_cards:
        lines.append(f"- REMOVED card '{c.name}' ({c.character or '?'}).")
    for c in m.reworked_cards:
        lines.append(f"- REWORKED card '{c.name}' ({c.severity}): {c.change or ''}")
    for r in m.reworked_relics:
        lines.append(f"- REWORKED relic '{r.name}' ({r.severity}): {r.change or ''}")
    for r in m.new_relics:
        lines.append(f"- NEW relic '{r.name}' (source: {r.source or '?'}).")
    for c in m.new_cards:
        lines.append(f"- NEW card '{c.name}' ({c.character or '?'}): {c.text or ''}")
    for e in m.reworked_enemies:
        lines.append(f"- REWORKED enemy '{e.name}' ({e.severity}).")
    for a in m.ascension_changes:
        lines.append(f"- Ascension {a.ascension}: '{a.from_}' → '{a.to}'.")
    for w in m.writing_clarifications:
        lines.append(f"- CLARIFICATION for '{w.entity}': {w.clarification}")
    for s in m.shop_changes:
        lines.append(f"- Shop: {s}")
    return "\n".join(lines)
