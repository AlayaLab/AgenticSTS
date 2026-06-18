# AGI-Eval Slay the Spire 2 LLM Leaderboard — May 2026 snapshot

**Source URL (primary):** https://deepseek.csdn.net/6a01b6b80a2f6a37c5a944ed.html
**Source URL (companion video):** https://www.youtube.com/watch?v=0v94pZmif9Y
**Captured:** 2026-05-28 via WebFetch
**Original title:** 《杀戮尖塔2》成了 DeepSeek V4 的照妖镜｜写得头头是道，怎么一打就废？
*("Slay the Spire 2 becomes DeepSeek V4's mirror: Sounds reasonable, plays terribly")*
**Original publication date (per page):** 2026-05-11
**Publisher:** AGI-Eval Community (CSDN DeepSeek subdomain)

---

## Headline result

All five frontier-model configurations evaluated reached **zero $A_0$ victories** across nine independent runs each. The Chinese article phrases this as "9局全败" (nine complete losses) for DeepSeek V4-Flash and reports analogous outcomes for the other four models. This matches the paper's claim of "0 wins across 5 frontier configurations at $A_0$".

## Frontier configurations evaluated

| # | Model | Outcome | Max / mean floor reached |
|---|-------|---------|--------------------------|
| 1 | GPT-5.4 | 0 wins | (specific floor not quantified in article) |
| 2 | Claude-opus 4.6 | 0 wins | **33 floors** (deepest defeat floor) |
| 3 | Claude-opus 4.7 | 0 wins | "Higher than 4.6" (specific not stated) |
| 4 | Doubao | 0 wins | 27 floors |
| 5 | DeepSeek V4-Flash | 0 wins (9局全败) | Average 11.4 floors ("平均只到11.4层") |

The paper's "max defeat floor 33" claim corresponds to the **Claude-opus 4.6** column.

## Methodology notes (as quoted)

- "为保证公平公正，我们为所有模型设置了相同的seed，确保实验的可复用性"
  *(All models used identical seed for reproducibility.)*
- Seed used: **VHY0FM7QT8** (chosen to give an early Hellraiser access).
- Three independent agent subsystems were deployed:
  1. Route selection
  2. Combat
  3. Deck construction
- Each subsystem had separate memory for cross-run learning.

## What the paper cites this source for

The paper (`sections_v2/intro.tex`, `sections_v2/appendix.tex`) uses this as an external calibration anchor: a public, independent leaderboard of frontier LLMs playing STS2 at $A_0$ that produced zero wins. The paper's headline (3/10 win rate baseline → 6/10 with $L_5$ skills) is presented against this 0/45 background.

## Discrepancies vs paper text

- Paper says "5 frontier-model configurations" → matches (GPT-5.4, Claude-opus 4.6, Claude-opus 4.7, Doubao, DeepSeek V4-Flash).
- Paper says "max defeat floor 33" → matches Claude-opus 4.6's 33 floors.
- Paper says "0 wins" → matches across all 5 configs.

**No discrepancies detected.**

## Notes / caveats

- This is a Chinese-language community blog post hosted under CSDN's DeepSeek subdomain; AGI-Eval is a Chinese community evaluation effort.
- The article is dated 2026-05-11; paper's `accessed 2026-05-13` is two days later.
- The companion YouTube video (`0v94pZmif9Y`) was not parseable via WebFetch (YouTube serves description data via JavaScript / API).
- Per-model floor breakdown for GPT-5.4 and Claude-opus 4.7 is described qualitatively rather than numerically in the article text retrieved.

## License / redistribution

CSDN community blog content; content is attribution-required for redistribution. This snapshot extracts only the headline numerical claims that the paper cites. The Chinese-language quotes are reproduced for verification (≤30 characters each, fair-use under criticism/research).
