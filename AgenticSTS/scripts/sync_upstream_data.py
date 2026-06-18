"""
Sync upstream game data JSON files from CharTyr/STS2-Agent.

Downloads 16 JSON files from mcp_server/data/eng/ into data/knowledge/upstream/.
Uses the GitHub CLI (gh) for authentication — run `gh auth login` first if needed.

Usage:
    python -m scripts.sync_upstream_data
    python -m scripts.sync_upstream_data --dry-run
"""

import argparse
import json
import os
import subprocess
import sys

REPO = "CharTyr/STS2-Agent"
REMOTE_DIR = "mcp_server/data/eng"
LOCAL_DIR = "data/knowledge/upstream"

# The 16 files we track. Update SHAs when upgrading to a new upstream version.
# SHAs pinned to v0.5.3 tree (2026-03-30).
FILES = [
    {"name": "cards.json",        "sha": "05377a86aa661170fbbdb762ee5bda5dbdbcfc15"},
    {"name": "relics.json",       "sha": "91c967a86cc27f5e65ca254fa629619abbc2a15a"},
    {"name": "monsters.json",     "sha": "04d9957f844b6f46eaeb37a09121f55828fcbac1"},
    {"name": "potions.json",      "sha": "1646a242707af6a48135c1eaac75cb0838799dae"},
    {"name": "events.json",       "sha": "ce36d2247c1526eb8fc6658645870bd627cf02c2"},
    {"name": "encounters.json",   "sha": "06e5dc11d8db9267035bc85c77f53b042b6a30dc"},
    {"name": "powers.json",       "sha": "d9f03222056ac6c24a106b420351847c8d2c77b2"},
    {"name": "enchantments.json", "sha": "629985afefa5935ddd976714b4f8f73292b781a7"},
    {"name": "acts.json",         "sha": "344d9ee2aba866adfe15226e7f4c623c291c791e"},
    {"name": "keywords.json",     "sha": "6857e8dc2a381089086e69068b3d77ca931c00d7"},
    {"name": "characters.json",   "sha": "f748892a9469ea35b029fcabc07009999ceecaa4"},
    {"name": "epochs.json",       "sha": "3e53bb58fac3a441f3fe3d3f4cd7a3749bd0915e"},
    {"name": "intents.json",      "sha": "68a0ba755903b5c3844d9a0c79f7c0d0d9ea2e3f"},
    {"name": "afflictions.json",  "sha": "d575c9e564eb9e1f3c88b536916a5bdcc15abad2"},
    {"name": "modifiers.json",    "sha": "42f0097947cf2fbff64b0d3382a19e54b1611b16"},
    {"name": "ascensions.json",   "sha": "c6d24e8ca1d32b335a74fbeff4ae8f987fdfaa72"},
]


def _gh_blob(sha: str) -> bytes:
    """Download a git blob by SHA via gh CLI, return raw bytes."""
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/git/blobs/{sha}", "--jq", ".content"],
        capture_output=True,
        check=True,
    )
    b64 = result.stdout.strip()
    import base64
    return base64.b64decode(b64)


def _get_latest_shas() -> dict[str, dict]:
    """Fetch current SHAs from upstream HEAD tree for all tracked files."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{REPO}/git/trees/HEAD?recursive=1",
            "--jq",
            f'.tree[] | select(.path | startswith("{REMOTE_DIR}/")) | {{path: .path, sha: .sha, size: .size}}',
        ],
        capture_output=True,
        check=True,
    )
    tree: dict[str, dict] = {}
    for line in result.stdout.decode().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        filename = entry["path"].removeprefix(f"{REMOTE_DIR}/")
        tree[filename] = entry
    return tree


def sync(dry_run: bool = False, force: bool = False) -> None:
    """Download all tracked files, skipping those whose SHA already matches."""
    os.makedirs(LOCAL_DIR, exist_ok=True)

    print(f"Fetching upstream tree from {REPO}/{REMOTE_DIR} ...")
    try:
        latest = _get_latest_shas()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: gh API call failed: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)

    skipped = updated = failed = 0

    for entry in FILES:
        name = entry["name"]
        pinned_sha = entry["sha"]
        local_path = os.path.join(LOCAL_DIR, name)

        upstream = latest.get(name)
        current_sha = upstream["sha"] if upstream else pinned_sha

        # Check if local file already matches
        if not force and os.path.exists(local_path):
            # Quick size check first
            expected_size = upstream["size"] if upstream else None
            local_size = os.path.getsize(local_path)
            if expected_size is not None and local_size == expected_size:
                print(f"  skip  {name:<30} (size matches, assuming up to date)")
                skipped += 1
                continue

        if dry_run:
            print(f"  would download  {name}")
            updated += 1
            continue

        print(f"  download  {name} (sha={current_sha[:12]}...)", end=" ", flush=True)
        try:
            data = _gh_blob(current_sha)
            # Validate JSON before writing
            json.loads(data)
            with open(local_path, "wb") as fh:
                fh.write(data)
            print(f"OK ({len(data):,} bytes)")
            updated += 1
        except subprocess.CalledProcessError as e:
            print(f"FAILED: {e.stderr.decode()}")
            failed += 1
        except json.JSONDecodeError as e:
            print(f"INVALID JSON: {e}")
            failed += 1

    print(
        f"\nDone: {updated} downloaded, {skipped} skipped, {failed} failed "
        f"({len(FILES)} total files)"
    )
    if failed:
        sys.exit(1)


def upgrade() -> None:
    """Print new SHA table from upstream HEAD (for updating this script)."""
    print(f"Fetching latest SHAs from {REPO} HEAD ...")
    latest = _get_latest_shas()
    tracked_names = {e["name"] for e in FILES}
    print("\n# Paste into FILES list to pin to latest upstream:")
    for name in sorted(tracked_names):
        if name in latest:
            entry = latest[name]
            print(f'    {{"name": "{name:<25}", "sha": "{entry["sha"]}"}},')
        else:
            print(f'    # WARNING: {name} not found in upstream tree')


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync upstream game data JSON from CharTyr/STS2-Agent"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    parser.add_argument("--force", action="store_true", help="Re-download even if local file exists")
    parser.add_argument("--upgrade", action="store_true", help="Print latest SHAs from upstream HEAD")
    args = parser.parse_args()

    if args.upgrade:
        upgrade()
    else:
        sync(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
