# sts2.fun — STS2 Community Statistics — May 2026 snapshot

**Source URL:** https://www.sts2.fun/
**Captured:** 2026-05-28 via WebFetch
**Status:** FETCHED
**Source role:** Community-uploaded Slay the Spire 2 run statistics; serves as a human-reference data point in the paper's external calibration discussion. Also referred to as "Spiracle" in some community contexts.

---

## Headline numbers (as quoted from live page on 2026-05-28)

| Metric | Value |
|--------|------:|
| **Total community runs** | **239,445** |
| **Active players** | 2,081 |
| **Overall win rate** | **30.1%** |
| Runs uploaded this week | 17,633 |

(Direct quote: "Defect · top character, winning **32.8%** of runs"; "Big Bang · go-to card, picked **82%** of the time"; "Silken Tress · most coveted relic, picked **80%** of the time".)

## Patch / version breakdown

The site tracks runs across multiple game patches:

| Patch | Runs |
|-------|-----:|
| Main v0.103 (current at capture) | 43,061 |
| Main v0.99 | 90,554 |
| Main v0.98 | 67,210 |
| Beta v0.100 – v0.106 | 78,873 (combined) |

Sum of called-out patches: **279,698** (slightly larger than the headline 239,445 — likely because some beta runs predate the headline counter, or because the headline excludes corrupted / aborted runs).

## Character / ascension highlights

- Top character by win rate: **Defect** at **32.8%** of runs won.
- "Hardest challenge": **Necrobinder** at **A10** (highest ascension; "A10" matches the paper's $A_0$–$A_{10}$ ladder).
- Top card pick rate: **Big Bang** at **82%**.
- Top relic pick rate: **Silken Tress** at **80%**.

## Community / language footprint

- Discord community size: **54,000 members**
- Other community channels: Reddit, Steam
- Site languages: English, Chinese, Japanese, Korean, Spanish, French, German, Russian

## What the paper cites this source for

The paper (`sections_v2/intro.tex` Figure 1c row; `sections_v2/appendix.tex` calibration table) uses sts2.fun as a human-reference row alongside the Mega Crit 16% A0 figure. The paper does not directly cite the 239,445 / 30.1% / 32.8% numbers (those would be derived statistics by the paper's authors); the citation is for the existence and methodology of the community-uploaded survival-by-floor dataset.

## Verification status

- The site is publicly accessible without authentication.
- The numbers above are as displayed on the homepage on 2026-05-28 at capture time.
- The page is a live dashboard — these numbers will continue to drift as community uploads accumulate.
- The headline "30.1% overall win rate" is across **all ascensions and all characters**, not the $A_0$ subset that Mega Crit's 16% figure references. The two are **not directly comparable** without an ascension-filtered query (which the homepage does not expose).
- A future reader who wants the exact $A_0$-only number would need to query sts2.fun's drill-down views (not captured in this snapshot).

## Discrepancies vs paper text

The paper does NOT cite specific sts2.fun numbers; it cites the source as the existence-of-community-data anchor. **No discrepancies to flag.**

## Notes / caveats

- No explicit data-licensing notice was visible on the homepage at capture time.
- No "last updated" timestamp was visible; "17,633 runs uploaded this week" suggests a near-realtime feed.
- The site is referred to as "STS2 Stats" on the page itself and informally as "Spiracle" in some community contexts (matching the paper's `note` field in `refs.bib`).
- The headline character "Defect" matches the original Slay the Spire (StS1) playable character roster — STS2 retains a similar character set. The paper's primary character for evaluation is the **Silent**, which is not the same character but is in the same character family.

## License / redistribution

No explicit license posted on the homepage; community statistics aggregation. Attribution to "sts2.fun" / "STS2 Community Stats" is the conservative path. This snapshot extracts only headline numbers cited / contextualized by the paper. Full page content is NOT mirrored here.
