"""CLI entry point for applying a game patch manifest.

Usage:
    python -m scripts.apply_patch --manifest data/patches/<game_version>.yaml [OPTIONS]

Options:
    --manifest PATH              Path to data/patches/<game_version>.yaml [required]
    --data-root PATH             Root of persistent data directory [default: data]
    --prompts-root PATH          Root of prompt source files [default: src/brain/prompts]
    --version-file PATH          Path to version_compatibility.json [default: data/version_compatibility.json]
    --snapshot-root PATH         Root for data snapshots [default: data.snapshots]
    --dry-run                    Report impact without writing changes
    --skip-llm                   Skip LLM prompt rewrite phase
    --smoke-test                 Run regression harness after apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, ".")

from src.patch.orchestrator import ApplyPatchOptions, apply_patch
from src.storage import paths


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="apply_patch",
        description="Apply a game patch manifest: snapshot, purge, rewrite prompts, bump version.",
    )
    p.add_argument("--manifest", type=Path, required=True,
                   help="Path to data/patches/<game_version>.yaml")
    p.add_argument("--data-root", type=Path, default=paths.data_root(),
                   help="Root of persistent data directory (default: resolved dynamic data root)")
    p.add_argument("--prompts-root", type=Path, default=Path("src/brain/prompts"),
                   help="Root of prompt source files to scan")
    p.add_argument("--version-file", type=Path, default=Path("data/version_compatibility.json"))
    p.add_argument("--snapshot-root", type=Path, default=Path("data.snapshots"))
    p.add_argument("--seeds-root", type=Path, default=Path("src/skills/seeds"),
                   help="Root of skill seed JSON files")
    p.add_argument("--dry-run", action="store_true", help="Report impact without writing changes")
    p.add_argument("--skip-llm", action="store_true", help="Skip LLM prompt rewrite phase")
    p.add_argument("--auto-apply", action="store_true",
                   help="Skip interactive confirmation before applying prompt rewrites")
    p.add_argument("--smoke-test", action="store_true",
                   help="Run regression harness after apply")
    return p


class _AnalysisTierAdapter:
    """Adapter mapping our LLMBackend protocol to V2Backend.call on the analysis tier."""

    def __init__(self):
        from src.brain.v2_backend import V2Backend
        import config as _cfg  # local import to avoid hard dep at module load
        self._backend = V2Backend()
        self._cfg = _cfg

    def complete(self, *, system: str, user: str) -> str:
        msg = self._backend.call(
            system=system,
            messages=[{"role": "user", "content": user}],
            provider=self._cfg.LLM_ANALYSIS_PROVIDER,
            model=self._cfg.LLM_ANALYSIS_MODEL,
            effort=self._cfg.LLM_THINK_EFFORT_ANALYSIS,
            think=True,
        )
        # Extract text from anthropic.Message: content is list of blocks; grab text blocks.
        text_parts: list[str] = []
        for block in getattr(msg, "content", []) or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(getattr(block, "text", ""))
        return "".join(text_parts)


def _build_backend():
    """Obtain real LLM backend from project analysis tier. Lazy-imported."""
    try:
        return _AnalysisTierAdapter()
    except Exception as exc:
        print(f"Warning: could not construct analysis backend ({exc}); prompts will not be rewritten.",
              file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 2

    backend = None if args.skip_llm or args.dry_run else _build_backend()

    options = ApplyPatchOptions(
        manifest_path=args.manifest,
        data_root=args.data_root,
        prompts_root=args.prompts_root,
        version_file=args.version_file,
        snapshot_root=args.snapshot_root,
        seeds_root=args.seeds_root,
        dry_run=args.dry_run,
        backend=backend,
        skip_llm=args.skip_llm or backend is None,
        auto_apply=args.auto_apply,
    )

    report = apply_patch(options)

    print(f"\n=== apply_patch report ({'DRY RUN' if args.dry_run else 'APPLIED'}) ===")
    print(f"Manifest: {args.manifest} ({report.manifest.game_version})")
    for r in report.purge_reports:
        print(f"  {r.store}: deleted={r.deleted} kept={r.kept}")
    print(f"Prompts rewritten: {report.rewrite_files_touched}")
    if report.snapshot_path:
        print(f"Snapshot: {report.snapshot_path}")
    if report.version_bumped:
        print(f"Version bumped to {report.manifest.game_version}")

    if args.smoke_test:
        print("\n--smoke-test: running regression harness...")
        import pytest as _pytest
        rc = _pytest.main(["tests/regression/", "-v"])
        return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
