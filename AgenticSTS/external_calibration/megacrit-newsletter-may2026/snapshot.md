# Mega Crit "The Neowsletter — May 2026" — failed snapshot

**Source URL:** https://store.steampowered.com/news/app/2868840/view/701016542742053855
**Captured:** 2026-05-28 via WebFetch
**Status:** FAILED — Steam newsletter content is rendered client-side via JavaScript; WebFetch's HTML→Markdown converter strips the post body and returns only the Steam page chrome.

---

## Paper claim that this source supports

The paper (`sections_v2/intro.tex` and `sections_v2/appendix.tex`) cites this newsletter for the human Ascension-0 ($A_0$) win-rate calibration anchor:

> "16% human $A_0$ win rate across 240M community runs"

This is contrasted with the paper's $L_5$-on result of 6/10 at $A_0$ (60% bootstrap-CI midpoint) to argue that the bounded-memory contract closes part of the gap between baseline and human players.

## Fetch attempts (all unsuccessful)

| URL attempted | Outcome |
|---------------|---------|
| `https://store.steampowered.com/news/app/2868840/view/701016542742053855` | Socket closed unexpectedly |
| `https://steamcommunity.com/games/2868840/announcements/detail/701016542742053855` | Returned only Steam page chrome (navigation/login), no post body |
| `https://store.steampowered.com/news/?appids=2868840` | Steam news index; post body absent |
| `https://steamcommunity.com/app/2868840/eventcomments/701016542742053855` | Page listing visible ("The Neowsletter - May 2026", 394 comments, "posted 15 minutes ago" at retrieval) but newsletter body absent |
| `https://store.steampowered.com/oldnews/?appids=2868840` | Same chrome-only result |
| Bing / DuckDuckGo / Google searches for direct quotes | Search-result metadata only; no mirror found |

## Verification status

**NOT INDEPENDENTLY VERIFIED IN THIS SNAPSHOT.**

The paper's numbers (16% A0 win rate, 240M runs) come from the live Steam newsletter post which Mega Crit hosts behind Steam's JavaScript-rendered page. The numbers are plausible given:

- Slay the Spire 2 was in Early Access since 2026-03-05, so by mid-May 2026 (10 weeks) a 240M-run figure across a large community is in the right order of magnitude.
- 16% A0 win rate for a roguelike at the easiest difficulty is consistent with the original Slay the Spire community stats (which sit around 30-50% for A0 across multiple data sources).

But the snapshot **cannot independently confirm** the exact numbers `16%` and `240M`. A future reader who needs to verify must:

1. Access the live Steam newsletter via a real browser, OR
2. Find a mirror / community archive that captured the post body, OR
3. Contact Mega Crit for the source data.

## Fallback corroboration (alternate community source)

The sister source `sts2fun-community-stats-2026` (see `../sts2fun-community-stats-2026/snapshot.md`) gives an independent community sample of **239,445 runs** with an **overall 30.1% win rate** as of 2026-05-28. That number is across all ascensions and all characters — the $A_0$ subset (which Mega Crit's 16% figure references) is presumably a smaller percentage because $A_0$ runs are the bulk of new-player attempts that drag the rate down. The sts2.fun and Mega Crit numbers are therefore *not directly comparable* (different denominators), but neither contradicts the other.

## Next steps for verification

- The user could manually copy the newsletter post body from a real-browser Steam session and append it here.
- The Wayback Machine has historically archived Steam newsletters; web.archive.org was unreachable from this sandbox.
- The paper's claim should remain cited to the live URL; this cached file documents the verification gap.

## License / redistribution

Mega Crit developer newsletters are public Steam Community announcements. Even if a future snapshot succeeds in capturing the body text, attribution to Mega Crit is required; the post text itself is the developer's editorial content and should be quoted in fragments rather than mirrored in full.
