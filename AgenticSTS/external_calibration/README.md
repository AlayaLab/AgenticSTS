# External Calibration Snapshots

This directory contains cached snapshots of the four external sources that the
AgenticSTS paper cites as calibration anchors. The snapshots exist so future
readers can reproduce — or at minimum verify the existence and approximate
magnitude of — the numbers the paper attributes to live, drift-prone web
sources.

**These snapshots are for reproducibility supplements only — they do NOT
replace the primary-source citation in `paper/.../refs.bib`.** Readers who
need to verify a specific number should:
1. Consult the cached `snapshot.md` first for the captured-on-2026-05-28 values.
2. Then consult the live URL in `metadata.yaml` for the current values.
3. Treat any drift as expected (these are live community / leaderboard sources).

## Source-by-source summary

| Source dir | Paper role | Status | Verified vs paper? |
|---|---|---|---|
| `agi-eval-spire-2026/` | "0 wins across 5 frontier configs at $A_0$; max defeat floor 33" | fetched | **MATCH** — paper numbers confirmed against the Chinese CSDN article body |
| `megacrit-newsletter-may2026/` | "16% human $A_0$ win rate across 240M community runs" | failed | **UNVERIFIED** — Steam newsletter body is JS-rendered; WebFetch returned only page chrome. Paper claim plausible but not independently confirmed in this snapshot |
| `spirecodex-2026/` | "576 cards / 293 relics / 115 monsters / 87 encounters / 66 events" | partial | **PARTIAL MATCH** — live site 403; GitHub README confirms "66 events" exactly but shows 403 cards (vs paper 576) and 111 monsters (vs paper 115). See snapshot for likely explanations (counting methodology, README staleness lag) |
| `sts2fun-community-stats-2026/` | Human-reference row in Figure 1c | fetched | **N/A** — paper does not cite specific sts2.fun numbers; captured headline values (239,445 runs, 30.1% overall win rate, 2,081 active players) document the source's existence and order of magnitude |

## Capture date

All snapshots captured **2026-05-28** via the `WebFetch` tool. The paper was
submitted to EMNLP 2026 ARR on **2026-05-25**, so all captures are 3 days
post-submission. The paper's own access dates (per `refs.bib` `note` fields) are
2026-05-13 (AGI-Eval), 2026-05-23 (Mega Crit, Spire Codex), and 2026-05-25
(sts2.fun) — all within the same ~2-week window.

## Headline discrepancy to flag

The Spire Codex GitHub README on 2026-05-28 shows:

| Entity | README | Paper | Match? |
|--------|------:|------:|:------:|
| Cards | 403 | 576 | mismatch |
| Monsters | 111 | 115 | mismatch (+4) |
| Events | 66 | 66 | match |
| Relics | (no number) | 293 | unverified |
| Encounters | (no number) | 87 | unverified |

Most likely the paper's 576 cards counted base+upgrade variants separately
(576/403 ≈ 1.43, consistent with most cards having an upgraded form). The
live API at `spire-codex.com/api/cards` would resolve this, but was unreachable
to WebFetch (403). **This is a documentation gap, not necessarily a paper
error.** A future maintainer with browser access to the live site should
record the authoritative counts.

## File structure

```
external_calibration/
├── README.md                                  (this file)
├── agi-eval-spire-2026/
│   ├── snapshot.md                            (Chinese CSDN article excerpt + paper-cited numbers)
│   └── metadata.yaml                          (source URL, capture date, paper claim, license)
├── megacrit-newsletter-may2026/
│   ├── snapshot.md                            (FAILED fetch — documents what paper cites + verification gap)
│   └── metadata.yaml
├── spirecodex-2026/
│   ├── snapshot.md                            (GitHub README captured; live site 403; CRITICAL discrepancy noted)
│   └── metadata.yaml
└── sts2fun-community-stats-2026/
    ├── snapshot.md                            (Live homepage stats; paper-N/A but documented for context)
    └── metadata.yaml
```

## License caveats per source

- **AGI-Eval (CSDN blog)** — community-attribution. Fragments-only extraction.
- **Mega Crit newsletter (Steam)** — developer content; attribution required even
  if a future snapshot succeeds in capturing the body text.
- **Spire Codex** — source code under PolyForm Noncommercial 1.0.0 (non-commercial
  redistribution permitted with attribution); game data is Mega Crit IP served
  under community fair-use.
- **sts2.fun** — no explicit license; attribution conservative path. Headline
  numbers extracted; full page not mirrored.

## Verification protocol for future readers

If a reader needs to confirm a specific number cited in the paper:

1. Open `external_calibration/<source>/snapshot.md` — see what was captured
   on 2026-05-28 and how it compares to the paper's text.
2. If the snapshot matches the paper: confidence high.
3. If the snapshot is "failed" or "partial": follow the URL in `metadata.yaml`
   to the live source. The numbers may have drifted but the methodology /
   existence of the source can still be confirmed.
4. For Spire Codex specifically: the live API endpoints (e.g., `/api/cards`)
   accept programmatic queries with proper HTTP headers. A real browser session
   or a properly-headered HTTP client should bypass the Cloudflare 403 that
   blocked WebFetch.

## What this directory deliberately does NOT include

- Full mirror copies of any source page (only the numbers the paper cites + minimal context).
- Archived snapshots from web.archive.org (was not reachable from the sandbox at capture time).
- Any number that could not be independently corroborated from a fetched page.
- Numbers fabricated to fit the paper's claims.
