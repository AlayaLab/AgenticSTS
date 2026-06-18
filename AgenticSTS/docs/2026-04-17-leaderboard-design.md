# STS2 Agent Leaderboard — Design Spec

**Status:** Draft v1
**Date:** 2026-04-17
**Target venue:** EMNLP paper companion + public community leaderboard
**Inspiration:** [arcprize.org/leaderboard/community](https://arcprize.org/leaderboard/community), [arcprize.org/arc-agi/3](https://arcprize.org/arc-agi/3)

---

## 1. Purpose & Positioning

A public-facing leaderboard for the question **"Can LLMs beat Slay the Spire 2? And how much does it cost?"** The site simultaneously serves three audiences:

1. **EMNLP reviewers** — need to see that STS2 is a rigorous benchmark and that our training-free HCM agent does well
2. **ML community (post-publication)** — want to compare methods and models, download data, maybe submit their own
3. **STS2 fans** — attracted by the visual game aesthetics, stay for the data

**Primary narrative:** *STS2 is a benchmark for LLM agents. Here's the leaderboard. Our training-free agent (with memory + skills + self-evolution) sits at the top, at a fraction of the cost of competitors.*

**One-sentence pitch (hero headline candidate):** "Can an LLM climb the Spire? One can."

---

## 2. Information Architecture

### Routes

```
/                          Hero + top-level leaderboard (Method view)
/leaderboard/methods       Method leaderboard (default tab)
/leaderboard/models        Model leaderboard (fix method=ours, compare LLMs)
/leaderboard/characters    Character leaderboard (only Silent for now; placeholder tab)
/submission/:id            Submission detail page (per-run breakdown, STS map trajectory)
/about                     What is STS2, what is this benchmark, how to submit
/methodology               Scoring formula, evaluation protocol, reproducibility notes
```

### Homepage vertical flow

1. **Hero band** — Headline + animated Trading Card Hero Deck (top 3 submissions, dealt onto screen)
2. **The Spire band** — Full-width signature visualization (6-tier tower, all submissions' flags climbing)
3. **Scatter band** — `Progress Score vs Cost` chart (ARC-style cost plot)
4. **Leaderboard band** — Tabbed submission table (with run-strip pills per row)
5. **Methodology band** — How scoring works, how to submit, link to GitHub
6. **Footer** — Paper citation, GitHub repo, Discord, contact

---

## 3. Data Model

### Source pipeline

```
data/runs/history.jsonl       (append-only, real runs)
      │
      ▼
scripts/build_leaderboard.py  (aggregator — groups runs, computes scores, emits JSON)
      │
      ▼
leaderboard/public/data/
  ├ submissions.json          (one entry per submission, top-level display)
  ├ runs/<submission_id>.json (detailed per-run data, lazy-loaded on detail page)
  └ metadata.json             (build timestamp, total runs, schema version)
```

Build invoked via `pnpm run build:data` before `pnpm build`. Also runs in CI on push.

### `submissions.json` schema

```typescript
interface Submission {
  id: string                    // "hcm-gemini-3-1-pro-silent-v03"
  method: {
    name: string                // "HCM-Agent"
    version: string             // "v0.3"
    authors: string[]
    description_short: string   // 1-liner for card flavor text
    github_url?: string
    paper_url?: string
    // Relic traits (STS-flavored feature tags)
    relics: Array<{
      id: 'memory-store' | 'skill-library' | 'evolution-engine' | 'web-search' | ...
      label: string
      description: string
    }>
  }
  model: {
    provider: 'anthropic' | 'openai' | 'google' | 'qwen' | 'other'
    name: string                // "Gemini 3.1 Pro"
    id: string                  // "gemini-3.1-pro-preview"
    // For fast/strategic/analysis split
    tier_breakdown?: Record<'fast' | 'strategic' | 'analysis', string>
  }
  character: 'Silent' | 'Regent' | ...   // currently only Silent
  runs: RunSummary[]            // exactly N runs (N = 10 for v1)
  aggregate: {
    ceiling: number             // 0-5, highest A beaten at least once
    ceiling_consistency: number // win rate at ceiling A (e.g. 0.2 = 2/10 wins at A4)
    progress_score_mean: number // mean of per_run_score across all runs
    progress_score_max: number  // max (best single run)
    avg_final_floor: number
    max_final_floor: number
    total_runs: number
    total_victories: number
  }
  cost: {
    total_usd: number
    total_input_tokens: number
    total_output_tokens: number
    cost_per_run_usd: number
    cost_per_ascension_unlocked_usd: number   // $ / A — efficiency metric
  }
  submitted_at: string          // ISO timestamp
  verified: boolean             // true if logs reproducibly reviewed
}

interface RunSummary {
  run_index: number             // 1..10
  ascension: number             // 0..5 (ascension started at)
  outcome: 'victory' | 'defeat' | 'abort'
  final_floor: number           // 1..50-ish
  final_act: 1 | 2 | 3
  death_cause?: string          // "Time Eater" | "Heart" | "out of HP on floor 22"
  duration_seconds: number
  per_run_score: number         // ascension*100 + (50 if victory else final_floor)
  run_log_url?: string          // link to detailed JSONL if we publish it
}
```

### `runs/<id>.json` schema (lazy-loaded for detail page)

Per-run full replay data: floor-by-floor deck state, decisions at key junctions, event choices, boss fights. Used by the Submission Detail page's STS Map View visualization. Schema TBD in v2 implementation — v1 uses RunSummary only.

---

## 4. Scoring & Ranking

### Per-run Progress Score

```
per_run_score = ascension × 100 + (50 if victory else final_floor)
```

Rationale:
- Each ascension tier worth 100 "progress units"
- Victory worth +50 (equivalent to half a run's length, matching STS2's ~50-floor structure)
- Higher A always beats lower A (since beating A_n requires having beaten A_(n-1))

Examples:
| Run | Score |
|---|---|
| A0 died floor 12 | 12 |
| A0 victory | 50 |
| A1 died floor 33 | 133 |
| A2 victory | 250 |
| A4 died floor 38 | 438 |
| A4 victory | 450 |
| A5 died floor 8 | 508 (higher than A4 victory — correctly reflects that reaching A5 means A4 was cleared) |

### Aggregate metrics

- **Ceiling (A)** — Highest ascension beaten at least once in the N=10 runs
- **Ceiling Consistency** — `wins_at_ceiling / attempts_at_ceiling`
- **Progress Score (mean)** — used as Y-axis on the scatter plot; represents *average run performance*
- **Progress Score (max)** — used as tiebreaker; represents *peak capability*

### Ranking rules (per leaderboard tab)

Primary sort: **Ceiling desc**, tiebreaker **Progress Score (mean) desc**, tiebreaker **Cost per A desc**.

### Cost metrics

- `total_usd` — headline cost over N runs
- `cost_per_ascension_unlocked_usd` — **$ / A** (THE efficiency number; this is our talking point)
- Token count shown as secondary (e.g. `$12.40 (2.4M tok)`)

---

## 5. Visual Design

### Color System

**Scholar View (light, default)**

| Token | Hex | Usage |
|---|---|---|
| `bg-base` | `#faf7f2` | Page background (warm parchment) |
| `bg-raised` | `#f0ebe0` | Cards, section backgrounds |
| `ink-primary` | `#1a1625` | Body text |
| `ink-secondary` | `#5a4f66` | Meta / captions |
| `accent-violet` | `#7c3aed` | Primary accent (STS rarity purple) |
| `accent-gold` | `#d4a017` | Victory / SOTA highlights |
| `accent-magenta` | `#c2185b` | CTA buttons (ARC Prize nod) |
| `success` | `#2d7a3e` | Positive deltas |
| `danger` | `#b33a3a` | Negative / fail |

**Spire Mode (dark)**

| Token | Hex | Usage |
|---|---|---|
| `bg-base` | `#0d0818` | Deep midnight purple-black |
| `bg-raised` | `#1a0f2e` | Card / panel bg |
| `ink-primary` | `#f0e6d2` | Warm cream text |
| `ink-secondary` | `#9b8aa3` | Muted lavender |
| `accent-gold` | `#f4c430` | Full STS gold |
| `accent-magenta` | `#e91e63` | Hot pink CTA |
| `accent-violet` | `#a78bfa` | Neon violet |
| `fire-glow` | `#f97316` | Orange flame/ember accents |

**STS Rarity Palette (for card borders & Ascension tiers)**

| Ascension | Rarity name | Color | Gradient? |
|---|---|---|---|
| A0 | Common | `#b0a89e` gray | No |
| A1 | Uncommon | `#5fa8d3` blue | No |
| A2 | Rare | `#9b59b6` purple | No |
| A3 | Elite | `#e67e22` orange | No |
| A4 | Legendary | `#e74c3c` → `#f4c430` | Yes, orange-gold |
| A5 | Mythic | rainbow holographic | Yes, animated |

### Typography

| Token | Family | Weight | Use case |
|---|---|---|---|
| `display-xl` | Cinzel | 700 | Hero headline (72px) |
| `display-lg` | Cinzel | 600 | Section titles (48px) |
| `display-md` | Cinzel | 600 | Card titles (24-32px) |
| `body-lg` | Fraunces | 400 | Paragraph lede (18px) |
| `body-md` | Fraunces | 400 | Standard body (16px) |
| `body-sm` | Fraunces | 400 | Captions (14px) |
| `mono-lg` | JetBrains Mono | 500 | Big numbers in stats (20-24px) |
| `mono-md` | JetBrains Mono | 400 | Table data (14px) |
| `pixel` | Press Start 2P | 400 | Game badges ONLY: "A4", "LEGENDARY", tiny pill text (8-10px) |

**NEVER** use Inter, Roboto, Space Grotesk, or generic system fonts.

Load via `<link>` from Google Fonts (Cinzel, Fraunces, JetBrains Mono, Press Start 2P).

### Spacing & Layout

- Grid: `max-width: 1200px` centered, 24px gutter
- Vertical rhythm: 8px base unit
- Scholar mode: generous whitespace, `--section-gap: 96px`
- Spire mode: denser `--section-gap: 64px` (feels more "packed treasure vault")

---

## 6. Key Components

### 6.1 Trading Card Hero

**Location:** Homepage hero band, top 3 submissions displayed side-by-side.

**Dimensions:** 280px × 420px (2:3 ratio). Responsive: stacks vertically on <768px.

**Layout:**

```
┌──────────────────────────────────┐  280px
│  ◆◇◆ LEGENDARY ◆◇◆    [pixel]   │   40px  ← rarity ribbon (color by ceiling)
├──────────────────────────────────┤
│  ╔══════════════════════╗        │
│  ║                      ║        │
│  ║   [Model portrait]   ║  180px ← illustration / logo with ornate frame
│  ║                      ║        │
│  ╚══════════════════════╝        │
├──────────────────────────────────┤
│   Gemini 3.1 Pro         [Cinzel]│   28px
│   + HCM Agent            [body]  │   22px
├──────────────────────────────────┤
│  CEILING    A4    ★★★★☆    [mono]│   18px
│  SCORE      438/600       [mono] │   18px
│  COST       $12.4 (2.4M)  [mono] │   18px
│  $/A        $3.10         [mono] │   18px
├──────────────────────────────────┤
│ [🧪][🧪][🧪]             [potion]│   24px ← cost viz: 3 potion bottles, fill level = affordability
├──────────────────────────────────┤
│ ▓▓▓▓▓▓▓▓▓▓  (10 mini pills)     │   30px ← run strip
├──────────────────────────────────┤
│ ❝Conquered the Heart❞   [italic] │   32px ← flavor text (auto-generated from ceiling+deepest boss)
└──────────────────────────────────┘
```

**Rarity border by ceiling:**
- A5 ceiling → animated holographic gradient (rainbow shift)
- A4 → gold-orange gradient with subtle shimmer
- A3 → solid purple with glow
- A2 → solid blue
- A1/A0 → neutral gray/white

**Interaction:**
- Hover: 3D tilt following mouse position (CSS `perspective(1000px) rotateX/Y`)
- Card shadow intensifies on hover
- Holographic gradient shifts with mouse position (Legendary/Mythic only)
- Click: navigates to `/submission/:id`

**Entrance animation** (page load):
- Cards fly in from offscreen right, one at a time (200ms stagger)
- Each settles with a slight overshoot bounce
- Accompanied by optional subtle "card dealt" sound effect (muted by default)

### 6.2 The Spire (signature visualization)

**Location:** Second band of homepage, full width within 1200px container.

**Dimensions:** ~800px tall, 1200px wide.

**Visual:**

```
                    ☁  ???  ☁               ← fog overlay + "??? The Peak"
                  ┏━━━━━━━━━━━━━━━┓
     A5 MYTHIC   ┃                 ┃         ← no flags here (yet)
                  ┗━━━━━━━━━━━━━━━┛
                  ┏━━━━━━━━━━━━━━━┓
     A4 LEGEND   ┃  🏴(HCM+Gemini) ┃         ← golden flame glow around top flag
                  ┗━━━━━━━━━━━━━━━┛
                  ┏━━━━━━━━━━━━━━━┓
     A3 ELITE    ┃  🏴(HCM+GPT)    ┃
                  ┗━━━━━━━━━━━━━━━┛
                  ┏━━━━━━━━━━━━━━━┓
     A2 RARE     ┃  🏴(Voyager)    ┃
                  ┗━━━━━━━━━━━━━━━┛
                  ┏━━━━━━━━━━━━━━━┓
     A1 UNCOMMON ┃                 ┃
                  ┗━━━━━━━━━━━━━━━┛
                  ┏━━━━━━━━━━━━━━━┓
     A0 COMMON   ┃                 ┃
                  ┗━━━━━━━━━━━━━━━┛
                  ═════════════════════
                     [Ground / Start]
```

**Per-tier composition:**
- Tier height: ~100px each (6 tiers × ~100px + headers = ~700px)
- Background: atmospheric illustration (stylized castle/cavern silhouette per A level, color-graded to tier)
- Foreground: horizontal row of flags (submissions that reached this ceiling)
- Label: `A4 — THE HEART` in Cinzel 24px on left edge
- Divider: thin gold line between tiers, ornate corner flourishes

**Flag component:**
- 48px circle avatar (model logo / first letter of method name)
- Cloth banner underneath with method name in Press Start 2P 10px
- Border glow matching ceiling rarity color
- Stacked horizontally within tier (max 8 per tier, overflow → "+N more" chip)

**Animations:**
- **Entrance (on intersection observer):** Each flag starts at the ground plane, animates upward to its target tier. 2s total duration, 200ms stagger between flags. Easing: `easeOutQuart`. Flag unfurls (scale-Y 0→1) on arrival.
- **Idle:** Subtle parallax on scroll (background moves slower than flags). Flame particles drift up at A4/A5 tiers. Fog swirls at A5 (unreached).
- **Hover flag:** Card lifts 8px, glow intensifies, tooltip appears on the right side showing `run-strip` preview + click hint.

**Interaction:**
- Click flag → `/submission/:id`
- Click tier label → filters leaderboard below to only submissions reaching that A

### 6.3 Run-Strip Pill

**Location:** Inside leaderboard table rows, inside Trading Card footer, inside tooltips.

**Per-pill:**

```
┌────┐
│ A4 │  ← pixel font 8px, rarity color
│ ·38│  ← mono 10px, floor; OR gold ✓ for victory
└────┘
```

- Size: 36px wide × 28px tall
- Border radius: 4px
- Background gradient:
  - Victory → full rarity gradient (A4 legendary = gold shimmer)
  - Died Act 3 (floor 35-49) → rarity color at 70% saturation
  - Died Act 2 (floor 18-34) → rarity color at 40%
  - Died Act 1 (floor 1-17) → grayscale
  - Aborted → dashed border, faded
- Hover: scale 1.1, tooltip appears above with full detail (`A4 Victory — Run 7`, `HP 54/89, gold 420, deck 24 cards, beat Heart in 8 turns`)

### 6.4 Ceiling × Cost Scatter

**Location:** Third band of homepage, 1200×500px.

**Axes:**
- X: `Cost per ascension unlocked` in USD, **log scale**
- Y: `Progress Score (mean)`, linear 0-600

**Points:**
- Each submission = one dot
- Dot size ∝ total runs (usually all 10, so uniform; future-proof)
- Dot color = method family (HCM variants in golds, Voyager in blue, baseline in gray)
- Dot shape = model family (circle = Gemini, triangle = GPT, square = Qwen, diamond = Claude, hex = other)

**Quadrant annotations** (subtle, background text):
- Top-left: "SOTA Zone" (high score, low cost) — ours should land here
- Top-right: "Brute Force" (high score, high cost)
- Bottom-left: "Underperforming"
- Bottom-right: "Wasteful"

**Interaction:**
- Hover dot: preview card floats in (mini version of Trading Card with stats)
- Click dot: scrolls to submission row in table below and highlights it

### 6.5 Leaderboard Table

**Location:** Fourth band, full-width.

**Tab bar** (above table):
- `Methods` | `Models` | `Characters` (disabled with tooltip "Coming soon — only Silent available")
- Sub-filters: character dropdown, ascension filter, date range, show/hide verified-only

**Columns:**

```
┌──────┬──────────────────┬──────────┬──────┬─────────┬──────┬────────┬─────────────────────────────┐
│ Rank │ Submission       │ Model    │ Char │ Ceiling │ Score│ Cost   │ Runs (10)                    │
├──────┼──────────────────┼──────────┼──────┼─────────┼──────┼────────┼─────────────────────────────┤
│  1   │ 🏆 HCM-Agent v0.3│ Gemini 3 │ 🗡️ S │   A4    │ 438  │ $12.4  │ ▓▓▓▓▓▓▓▓▓▓ (10 mini pills)  │
│      │   by Us          │  1 Pro   │      │  2/10 ✓ │      │  $3/A  │                              │
├──────┼──────────────────┼──────────┼──────┼─────────┼──────┼────────┼─────────────────────────────┤
│  2   │    HCM-Agent v0.3│ GPT-5.4  │ 🗡️ S │   A3    │ 312  │ $38.1  │ ▓▓▓▓▓▓▒▒▒▒                   │
│      │   by Us          │  Thinking│      │  4/10 ✓ │      │ $12/A  │                              │
├──────┼──────────────────┼──────────┼──────┼─────────┼──────┼────────┼─────────────────────────────┤
│  3   │    Voyager-STS   │ GPT-5.4  │ 🗡️ S │   A2    │ 187  │ $21.2  │ ▓▓▒▒▒░░░░░                   │
│      │   by Anon        │          │      │  1/10 ✓ │      │ $21/A  │                              │
└──────┴──────────────────┴──────────┴──────┴─────────┴──────┴────────┴─────────────────────────────┘
```

**Row interactions:**
- Entire row clickable → `/submission/:id`
- Hover row: subtle gold underline; rank badge glows
- Sort by any column

**Sub-row "relic traits" (collapsed by default, expands on click):**
- Below the main row, a thin strip showing method's relic icons with tooltips
- Example: `🧠 Memory Store`, `📚 Skill Library`, `🧬 Evolution Engine`

### 6.6 Submission Detail Page

Future page (`/submission/:id`) — not in v1 scope. Includes:
- Full trading card at top
- Per-run accordion: each run expands to show STS Map View (trajectory) + deck final state + key decisions
- Run-by-run cost breakdown
- Download JSON / raw logs

---

## 7. Interaction & Animation Catalog

### Page load sequence (homepage)

1. **0ms** — Background gradient fades in, page shell paint
2. **100ms** — Hero headline types in (character-by-character, like ARC-AGI-3's "PUT YOUR AGENT TO THE TEST!" text)
3. **600ms** — Cards dealt from offscreen-right, 200ms stagger
4. **1400ms** — "The Spire" section scrolled into view (if on screen): flags climb from ground to their tiers
5. **2000ms** — Scatter dots fade in with slight parallax from their final positions
6. **Thereafter** — idle animations: fog/ember particles, potion bubbles, flag wave

### Theme toggle

- Button: 🕯️ candle in top-right
- On click: fullscreen overlay fades in with flame particle burst, theme CSS variables swap, overlay fades out (~800ms total)
- Persisted via `localStorage.getItem('theme')`
- Respects `prefers-color-scheme` on first visit

### Hover micro-interactions (cumulative delight)

- Nav links: underline draws L→R
- Trading cards: 3D tilt + holographic shift
- Flags on Spire: lift + glow intensify
- Pills: scale + tooltip
- Scatter dots: preview card materializes
- Relic icons: glow + tooltip with description

### Reduced motion

- Respect `prefers-reduced-motion: reduce`
- Replace stagger/bounce with straight fades
- Disable parallax, fog drift, particle effects

---

## 8. Technical Architecture

### Project layout

```
AgenticSTS\
├── frontend/              ← existing monitor dashboard (UNTOUCHED)
├── leaderboard/           ← NEW — this project
│   ├── public/
│   │   ├── data/
│   │   │   ├── submissions.json      ← built artifact
│   │   │   ├── metadata.json
│   │   │   └── runs/*.json
│   │   └── assets/
│   │       ├── fonts/    ← locally hosted backup copies
│   │       ├── spire/    ← 6 tier background SVGs
│   │       ├── relics/   ← relic icon SVGs (memory-store.svg, etc.)
│   │       ├── potions/  ← potion bottle SVGs (3 fill levels)
│   │       └── models/   ← model provider logos
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes/
│   │   │   ├── Home.tsx
│   │   │   ├── About.tsx
│   │   │   ├── Methodology.tsx
│   │   │   └── SubmissionDetail.tsx   (v2)
│   │   ├── components/
│   │   │   ├── hero/
│   │   │   │   ├── HeroHeadline.tsx
│   │   │   │   └── TradingCard.tsx
│   │   │   ├── spire/
│   │   │   │   ├── TheSpire.tsx
│   │   │   │   ├── SpireTier.tsx
│   │   │   │   └── Flag.tsx
│   │   │   ├── scatter/
│   │   │   │   └── CeilingCostScatter.tsx
│   │   │   ├── leaderboard/
│   │   │   │   ├── LeaderboardTabs.tsx
│   │   │   │   ├── LeaderboardTable.tsx
│   │   │   │   └── RelicStrip.tsx
│   │   │   ├── shared/
│   │   │   │   ├── RunStrip.tsx
│   │   │   │   ├── RunPill.tsx
│   │   │   │   ├── PotionGauge.tsx
│   │   │   │   ├── RarityBorder.tsx
│   │   │   │   ├── ThemeToggle.tsx
│   │   │   │   └── Nav.tsx
│   │   │   └── tooltips/
│   │   │       └── *
│   │   ├── data/
│   │   │   ├── loadSubmissions.ts    ← fetch JSON, type-check with Zod
│   │   │   └── scoring.ts            ← progress score formula + sorting
│   │   ├── theme/
│   │   │   ├── tokens.css            ← CSS custom properties for both themes
│   │   │   └── ThemeProvider.tsx
│   │   └── hooks/
│   │       ├── useTheme.ts
│   │       └── useReducedMotion.ts
│   ├── scripts/
│   │   └── build_leaderboard.py      ← JSONL → JSON aggregator
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── README.md
└── scripts/
    └── build_leaderboard.py          ← symlink or separate; TBD
```

### Dependencies

```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "framer-motion": "^11.0.0",
    "recharts": "^2.12.0",
    "zod": "^3.23.0",
    "clsx": "^2.1.0"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "typescript": "^5.6.0",
    "tailwindcss": "^4.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0"
  }
}
```

### Build pipeline

```bash
# Local dev
cd leaderboard
pnpm install
pnpm run build:data       # runs python scripts/build_leaderboard.py, writes public/data/
pnpm run dev              # Vite dev server on localhost:5173

# Production
pnpm run build:data       # regenerate JSON from latest logs
pnpm run build            # Vite production build → dist/
pnpm run preview          # test dist/ locally

# Deploy (e.g. Cloudflare Pages / Vercel / GitHub Pages)
# Build command: pnpm run build:data && pnpm run build
# Output dir: leaderboard/dist
```

### Scoring utility (`src/data/scoring.ts`)

```typescript
export function perRunScore(run: RunSummary): number {
  return run.ascension * 100 + (run.outcome === 'victory' ? 50 : run.final_floor)
}

export function ceiling(runs: RunSummary[]): number {
  const victoryRuns = runs.filter(r => r.outcome === 'victory')
  if (victoryRuns.length === 0) return 0
  return Math.max(...victoryRuns.map(r => r.ascension))
}

export function consistencyAtCeiling(runs: RunSummary[], c: number): number {
  const attempts = runs.filter(r => r.ascension === c)
  if (attempts.length === 0) return 0
  return attempts.filter(r => r.outcome === 'victory').length / attempts.length
}
```

---

## 9. Implementation Phases

### Phase 1: MVP (v0.1) — "Static leaderboard with data"

**Goal:** A working, deployable site with real data and the two signature visualizations.

- [ ] Project scaffolding (Vite + React + TS + Tailwind v4)
- [ ] Theme system (tokens.css, ThemeToggle, useTheme hook)
- [ ] Data pipeline: `scripts/build_leaderboard.py` that reads `data/runs/history.jsonl` and emits `submissions.json`
- [ ] Mock data fixture with 5-10 submissions (hand-crafted for dev while real runs accumulate)
- [ ] Nav + Footer
- [ ] Hero headline (typing animation)
- [ ] Trading Card component (static, no 3D tilt yet) — top 3 in hero
- [ ] The Spire component (static, with climb animation)
- [ ] Leaderboard table (Methods tab only, with Run-Strip pills)
- [ ] Basic scatter plot
- [ ] Dark/light theme toggle
- [ ] Static deploy to Cloudflare Pages / Vercel

**Acceptance:** site is live, shows real submission data, passes Lighthouse > 85 on desktop.

### Phase 2 (v0.2) — "Polish + delight"

- [ ] Trading Card 3D tilt + holographic effect for Legendary/Mythic
- [ ] Flag hover tooltips with run-strip preview
- [ ] Scatter hover cards
- [ ] Relic traits sub-row
- [ ] Models tab + Characters tab (placeholder)
- [ ] About + Methodology pages
- [ ] Potion gauge component integrated into cards
- [ ] Particle effects (embers, fog at A5)
- [ ] Reduced-motion fallbacks

### Phase 3 (v0.3) — "Submission detail + STS Map"

- [ ] `/submission/:id` route
- [ ] Per-run detail expand
- [ ] STS Map View trajectory visualization (borrow pattern from C proposal)
- [ ] Raw log download links
- [ ] Share / deep-link to a specific run

### Phase 4 (v1.0) — "Public launch"

- [ ] "How to submit" documentation with PR template
- [ ] CSV/JSON data download button
- [ ] Citation block (BibTeX)
- [ ] OG image for social sharing (auto-generated per submission card)
- [ ] Analytics (privacy-respecting, e.g. Plausible)

### Out of scope for v1 (all phases)

- ❌ Live API / realtime run updates
- ❌ User-submitted runs via web form (only via PR for v1)
- ❌ Ablation tab (deferred per decision 2026-04-17)
- ❌ Multi-character leaderboards (only Silent exists)
- ❌ Head-to-head match replays
- ❌ Authentication / user accounts

---

## 10. Open Questions (to address before implementation)

1. **Real model portraits** — do we use each provider's official logo, or commission/AI-generate fantasy-styled portraits ("Gemini as a mage", "GPT as a knight")? The latter is WAY more on-brand and viral but costs more.
2. **Relic icon set** — design 5-8 custom relic SVGs (Memory Store, Skill Library, Evolution Engine, Web Search, Hierarchical Memory, etc.) — who draws them?
3. **Spire tier backgrounds** — 6 illustrations needed (dungeon, colosseum, caverns, castle, inferno, peak). Options: (a) commission, (b) AI-generate with Midjourney/Flux, (c) use licensed game-asset packs from itch.io, (d) defer illustrations and use atmospheric CSS gradients for v0.1.
4. **Domain** — where does this site live? `leaderboard.sts2-agent.dev`? Subdir on main project site? To discuss.
5. **Naming** — is "STS2 Agent Leaderboard" final, or do we want something punchier like "The Spire Bench" or "Ascension: LLM Edition"?

---

## 11. Decisions Log (from brainstorming 2026-04-17)

| Decision | Chosen | Rejected | Rationale |
|---|---|---|---|
| Primary narrative | Benchmark + method hybrid (B + A) | C (competitive arena) | EMNLP needs method story; benchmark framing makes work reusable |
| Primary metric | Ceiling + Consistency + Progress Score | single composite, win rate only | Auto-ascension progression naturally produces ceiling narrative |
| Run display | (ascension, outcome, floor) triple visible in table | Ceiling-only aggregation | Floor granularity carries critical info — A0 Victory ≠ A0 f33 |
| Runs per submission | 10 (5 shown + 5 expandable) | 5 fixed | 10 gives more statistical power for consistency stats |
| Cost dimensions | Both $ and tokens, plus $/A efficiency | $ only | Different models priced differently; $/A is the killer stat |
| Leaderboard structure | (iv) multi-tab + submission granularity | (i/ii/iii) | Clean separation of stories per audience |
| Ablation handling | Deferred to v2+ | Show in main table | Not at ablation stage yet |
| Signature visualization | A (Spire) + B (Trading Cards) | C (Map) as hero, heatmap ladder | Spire = brand recognition; Cards = shareable; heatmap felt too academic |
| STS elements used | Potion cost, Relic traits, Card rarity, Character avatar | Energy overload, Map as hero | Each element earns its keep |
| Color theme | Dual mode (Scholar default + Spire dark) | Dark-only or light-only | Reviewer friendly + fan delight |
| Fonts | Cinzel + Fraunces + JetBrains Mono + Press Start 2P | Inter, Space Grotesk, generic | Avoid AI-slop aesthetics |
| Data source | (a) static JSON | (b) live API, (c) cron refresh | KISS for v1; add cron later if needed |
| Project location | (β) new `leaderboard/` subdir | (α) merge with frontend, (γ) refactor | Clean separation of dev tool vs public site |

---

## 12. Success Criteria (for v0.1 MVP)

1. ✅ Site is live at a stable URL
2. ✅ Real submission data from our own runs is displayed
3. ✅ At least one competitor/baseline method shown alongside for comparison
4. ✅ Trading Cards and The Spire render correctly on desktop + mobile
5. ✅ Theme toggle works and persists
6. ✅ Lighthouse perf > 85 on desktop
7. ✅ Total bundle size < 500KB gzipped (excluding fonts)
8. ✅ At least one friendly reviewer (not me or the user) looks at the site and says "oh this is cool"

---

*End of spec. Next step: hand to `superpowers:writing-plans` to decompose Phase 1 into an executable implementation plan.*
