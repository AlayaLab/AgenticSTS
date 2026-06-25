# Release exclusions

This document lists files and directories that exist in the current working
tree but **must not** be included when the new public release repository is
seeded. The exclusions exist for two reasons:

1. **License incompatibility** — some files are derived from upstream
   sources whose license is incompatible with the project's Apache-2.0
   distribution.
2. **Stale or sensitive content** — some directories are dev-side staging
   areas with machine identifiers, internal hostnames, or pre-restructure
   metadata that contradict the released paper.

## How to apply the exclusion list

Two equivalent paths exist:

### Option α — `git archive` with `--worktree-attributes`

Tag the excluded paths with `export-ignore` in a top-level `.gitattributes`:

```
data/knowledge/upstream/      export-ignore
data/knowledge/*_dll.json     export-ignore
paper/data_package_2026-05-20/  export-ignore
```

Then seed the public repo with:

```bash
git archive --worktree-attributes --format=tar HEAD | \
  tar -x -C /path/to/new-release-repo
cd /path/to/new-release-repo
git init
git add .
git commit -m "Initial release seed"
```

### Option β — manual exclusion at copy time

Use `rsync` or a custom snapshot script that explicitly excludes the paths
listed below.

```bash
rsync -av --exclude='data/knowledge/upstream/' \
          --exclude='data/knowledge/*_dll.json' \
          --exclude='paper/data_package_2026-05-20/' \
          ./ /path/to/new-release-repo/
```

The orchestrator decides which mechanism to use at release time.

---

## License-incompatible content (CRITICAL — Apache-2.0 cannot redistribute)

### `data/knowledge/upstream/` (24 JSON files)

These are verbatim copies from
[`CharTyr/STS2-Agent`](https://github.com/CharTyr/STS2-Agent), which the
panel 4 review confirmed is **AGPL-3.0-only**. AGPL is one-way-compatible
into AGPL projects, not into Apache-2.0 projects. Redistributing these
files under our LICENSE would either violate AGPL (if we ignored it) or
force the entire project to AGPL (if we honored it).

**Mitigation**: the orchestrator script `scripts/sync_upstream_data.py`
regenerates `data/knowledge/upstream/` from the upstream repo on demand.
Public-release users run this script themselves; the **outputs live on
their machine under their own license obligations to the upstream AGPL**,
not redistributed by the AgenticSTS project. This is identical to the
pattern many ML projects use for redistributable derivatives of
restrictive datasets.

The script itself (`sync_upstream_data.py`) IS in the release — only its
generated output is excluded.

### `data/knowledge/*_dll.json` (4 files)

These were extracted via `ilspycmd` decompilation of Mega Crit's
proprietary `sts2.dll`. Decompiled extracts of proprietary software
cannot be redistributed without the original vendor's permission, which
Mega Crit has not granted for this project's release.

**Mitigation**: the orchestrator script
`scripts/extract_mechanics_from_dll.py` re-runs the extraction. Same
pattern as the upstream sync — users regenerate locally from their own
legal copy of `sts2.dll`. Public-release users **must own** Slay the
Spire 2 to use this regeneration script; the extract is downstream of
their own license to the game.

### `data/knowledge/*.md` decompiled game-mechanic indexes (8 files)

`cards.md`, `card-behaviors.md`, `characters.md`, `events.md`, `monsters.md`,
`monster-behaviors.md`, `potions.md`, `potion-behaviors.md` are Markdown index
tables auto-generated from the decompiled `sts2.dll` (their headers read
"Auto-generated from extraction/decompiled"); they contain Mega Crit's internal
command names and numeric values. Like the `*_dll.json` extracts, decompiled
content of proprietary software cannot be redistributed without the vendor's
permission.

**Mitigation**: users regenerate locally from their own legal copy of the game —
decompile `sts2.dll` into `extraction/decompiled/`, run
`scripts/generate-sts2-knowledge.ps1` (writes `docs/game-knowledge/*.md`), then
copy the results into `data/knowledge/` where the runtime parser reads them. The
generator script IS in the release; only its decompiled output is excluded.

The hand-authored `character_strategies.md` (compiled from public web research)
and the directory's `README.md` are NOT decompiled and **do** ship.

### Affected `NOTICE` line

The `NOTICE` file already documents that "This project does NOT include
or redistribute the Slay the Spire 2 game." That disclaimer is what the
above exclusions implement in practice.

---

## Stale / sensitive content (HIGH — should not ship)

### `paper/data_package_2026-05-20/` (iter5 staging area)

Stale pre-restructure metadata + leaked identifiers:

- `paper/data_package_2026-05-20/README.md` carries the iter5 paper title,
  "362 runs", and "$A_0$-$A_{20}$" ladder claims — **all superseded** by
  the final EMNLP submission (`AgenticSTS`, 298 trajectories, $A_0$-$A_{10}$
  ladder).
- 289 records across 14 JSONL files inside this directory leak
  `machine_id: <personal-machine-hostname>` (a personal machine hostname).
- 18 records embed commercial-relay hostnames `<commercial-relay-host>` and
  `<commercial-relay-host>` (gameplay-time API proxies that should not be exposed in a
  public dataset).

The actual 298-trajectory release lives in the sibling repo
`AgenticSTS-Data` (via `STS2_DATA_REPO`), which is the authoritative source
of paper-grade data. This staging directory was an intermediate work area
that was not cleaned up before submission.

**Mitigation**: exclude the entire directory from the release seed.

---

## Files in scope but flagged for sanitation (kept, with edits — not exclusions)

The following live in the public release tree but had identifiable
content scrubbed in place during the remediation pass; they are NOT
exclusions, just listed here for the audit record:

| Path | Issue | Fix |
|---|---|---|
| `paper/.../figures/v2/_crop_pdf.py:6` | `<local-path>` SRC line inside ARR bundle | parameterized to argv-driven default |
| 6 docs under `docs/superpowers/specs/` | a personal author byline | replaced with `AgenticSTS Contributors` |
| `docs/2026-04-28-mod-english-output-with-chinese-ui.md:9` | `<local-path>` path | replaced with relative path |
| `docs/stream-ui-integration.md:7` | same | same |
| 5 dev scripts under `scripts/*` | hardcoded `...` paths | env-resolved or relative |

See `docs/release/remediation_log.md` for the exact diffs once the
remediation pass completes.

---

## Items reviewed and kept (no action needed)

- **`.env.example`**: empty placeholder template; safe.
- **`.gitignore`**: correctly excludes `.env`, `.venv`, `logs`, `node_modules`,
  etc.
- **The paper itself is NOT in this repo.** The arXiv preprint (LaTeX source +
  PDF) is released separately on arXiv, not shipped in this code repository, so
  there is no paper-bundle / LaTeX-style-file content (e.g. `acl.sty`) to vet
  here. The repo links to the paper rather than embedding it.

---

## Future-work hooks

When the matched accumulating-context experiment runs (workstream B), its
output trajectories will land in the sibling data repo and become part of
the canonical 298+ archive. The current dev workflow can be extended to
new sibling-repo data without needing to revisit this exclusion list.

The `docs/release/release_exclusions.md` file itself ships in the public
release — it documents the boundary between what's distributable and what
the user must regenerate locally, which is useful context for the
researcher-reusable bar.
