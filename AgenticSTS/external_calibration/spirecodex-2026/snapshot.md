# Spire Codex — partial snapshot (live site 403, GitHub README captured)

**Source URL (paper-cited):** https://spire-codex.com/
**Source URL (GitHub canonical):** https://github.com/ptrlrd/spire-codex
**Captured:** 2026-05-28 via WebFetch
**Status:** PARTIAL — live site returns HTTP 403 to WebFetch (Cloudflare / WAF); GitHub README on `main` and `staging` branches was fully retrieved, but its inventory counts diverge from the paper's claims (see "CRITICAL discrepancy" below).

---

## Paper claim that this source supports

The paper (`sections_v2/testbed.tex`) cites Spire Codex for the STS2 content-inventory anchor:

> "576 cards / 293 relics / 115 monsters / 87 encounters / 66 events (Spire Codex May 2026)"

This is used to characterize STS2's "closed-rule space" as a long-horizon-but-discrete environment.

## What was retrieved

### Live site `https://spire-codex.com/` — INACCESSIBLE
All paths attempted returned HTTP 403:
- `/` (root)
- `/api/cards`
- `/cards`
- `/database`
- `/about`
- `/sitemap.xml`

Cloudflare / WAF appears to be blocking the WebFetch user agent. The live API would have been the authoritative source for the numerical counts cited by the paper.

### GitHub canonical repo — RETRIEVED

**Repository:** `ptrlrd/spire-codex` (TypeScript + Python; 202 GitHub stars; 1,035 commits on staging)
**README most recent update:** 2026-05-22 (commit `e1d9e2a`: "Docs: refresh README + API reference + ansible README")
**License (source code):** PolyForm Noncommercial 1.0.0
**License (game data):** © Mega Crit Games — served as community reference under fair-use

#### README-quoted inventory counts (both `main` and `staging` branches; identical text)

| Entity | README count | Paper-cited count | Match? |
|--------|-------------:|------------------:|:------:|
| Cards | 403 | 576 | **MISMATCH** |
| Relics | "comprehensive pool data" (no number) | 293 | unverified |
| Monsters | 111 (99 rendered + 12 aliases / static) | 115 | **MISMATCH (close: +4)** |
| Encounters | "full act-based compositions" (no number) | 87 | unverified |
| Events | 66 | 66 | **MATCH** |
| Powers | 260 | (not cited) | n/a |
| Achievements | 33 | (not cited) | n/a |
| Languages | 14 | (not cited) | n/a |

The "events: 66" line matches the paper exactly. The other paper-cited numbers are NOT reproduced verbatim by the README.

### Architecture (for context)

- Backend: FastAPI (Python), GZip compression, 60 req/min rate limit
- Frontend: Next.js 16, TypeScript, Tailwind CSS
- Data extraction: GDRE Tools (Godot PCK) + ILSpy (.NET DLL decompile) + 22 Python regex parsers
- Game version: built from `sts2.dll` (Godot 4.x + .NET 8 / 9)
- API: 25+ endpoints (e.g., `/api/cards`, `/api/relics`, etc.)

## CRITICAL discrepancy

The README (committed 2026-05-22, one day before the paper's "accessed 2026-05-23" date) reports **403 cards / 111 monsters / 66 events**, but the paper claims **576 cards / 293 relics / 115 monsters / 87 encounters / 66 events**.

**Possible explanations (cannot be resolved without live-API access):**

1. **README staleness lag.** The README in `ptrlrd/spire-codex` lists counts the maintainer last manually updated; the live API may now serve more entries because the parser pipeline auto-detects new content. If Mega Crit shipped a content patch between the README's last manual count refresh and the paper's access date, the README would be stale.
2. **Counting methodology differs.** The paper may have counted:
   - Cards: base + upgraded forms as separate entries (paper's 576 / README's 403 = 1.43, ratio close to base+upgrade doubling minus innate cards).
   - Monsters: 111 visible + 4 hidden/scripted = 115.
   - Encounters: act-based compositions counted individually (no README total to compare against).
3. **Paper used the live `/api/*` endpoint counts directly.** The paper's author would have queried the API as a programmatic source — those numbers can drift independently of the README.

**Recommended verification step:** A future maintainer should hit `/api/cards`, `/api/relics`, `/api/monsters`, `/api/encounters`, `/api/events` from a real browser session (or a properly-headered HTTP client that passes the WAF), and either confirm the paper's exact numbers or document the live values for the May-2026 snapshot.

## What can be confidently asserted from the snapshot

- Spire Codex (`ptrlrd/spire-codex`) is a real, actively-maintained Slay the Spire 2 database (last commit 2026-05-22; 202 stars).
- It is the only project with that name in the GitHub search index.
- License: PolyForm Noncommercial 1.0.0 — code is free to use/modify for non-commercial purposes; commercial use requires separate licensing.
- The "66 events" figure in the paper matches the README exactly.
- The project's existence and broad scope (cards / relics / monsters / events / powers / achievements; 14 localizations) is fully confirmed and consistent with the paper's framing as a community reference for STS2 content.

## License / redistribution

Spire Codex source code is PolyForm Noncommercial 1.0.0. Game-data content is © Mega Crit Games served under fair-use. This snapshot extracts only the inventory counts and project description from the GitHub README (which is itself under the project's license terms) — fragments suitable for academic citation. The full README is NOT mirrored here; readers should consult `https://github.com/ptrlrd/spire-codex` for the complete document.
