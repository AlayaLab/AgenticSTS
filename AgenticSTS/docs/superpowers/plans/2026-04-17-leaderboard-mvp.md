# STS2 Agent Leaderboard MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 1 MVP of the public STS2 Agent Leaderboard — a static-data, dual-theme React website with Trading Card Hero Deck, The Spire signature visualization, and sortable leaderboard table, deployable to Cloudflare Pages / Vercel.

**Architecture:** Independent Vite + React 19 + TypeScript + Tailwind v4 single-page app at `leaderboard/`, completely separate from the existing `frontend/` monitor dashboard. Data loaded at runtime from a static JSON fixture (real data pipeline deferred to v0.2). All React animations via `motion` (formerly Framer Motion). Scatter plot via Recharts. No backend required.

**Tech Stack:**
- **Runtime:** React 19, React Router v7
- **Build:** Vite 6, TypeScript 5.6, Tailwind v4
- **Animation:** `motion` library (successor to framer-motion)
- **Charts:** Recharts 2
- **Validation:** Zod 3
- **Testing:** Vitest + @testing-library/react
- **Package manager:** npm (matches existing `frontend/`)
- **Deployment:** Static (Cloudflare Pages or Vercel)

**Design spec:** `docs/2026-04-17-leaderboard-design.md` — read sections 1, 4, 5, 6, 11 before starting.

**Out of scope for this plan:**
- Python build script that reads real `data/runs/history.jsonl` (v0.2)
- Token aggregation from `logs/run_*.jsonl` (v0.2)
- Submission detail page `/submission/:id` (v0.3)
- STS Map View trajectory chart (v0.3)
- Real baseline competitor data (deferred — fake data for MVP)
- Real illustrations (placeholders via CSS gradients + emoji for MVP)

---

## File Structure

All paths are relative to `AgenticSTS\leaderboard\` unless noted.

```
leaderboard/
├── index.html                              (entry HTML, loads Google Fonts)
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── .gitignore
├── README.md
├── public/
│   └── data/
│       └── submissions.json                (mock fixture, 6 fake submissions)
├── src/
│   ├── main.tsx                            (root render)
│   ├── App.tsx                             (router + theme provider)
│   ├── index.css                           (Tailwind v4 @import + @theme tokens)
│   ├── routes/
│   │   └── Home.tsx                        (single route for MVP)
│   ├── types/
│   │   └── submission.ts                   (TS interfaces for Submission, RunSummary)
│   ├── data/
│   │   ├── schemas.ts                      (Zod schemas matching types)
│   │   ├── loadSubmissions.ts              (fetch + validate)
│   │   └── scoring.ts                      (pure scoring / aggregation functions)
│   ├── theme/
│   │   └── ThemeProvider.tsx               (light/dark context)
│   ├── hooks/
│   │   ├── useTheme.ts
│   │   └── useReducedMotion.ts
│   └── components/
│       ├── shared/
│       │   ├── Nav.tsx
│       │   ├── Footer.tsx
│       │   ├── ThemeToggle.tsx
│       │   ├── RunPill.tsx
│       │   ├── RunStrip.tsx
│       │   ├── PotionGauge.tsx
│       │   └── RarityBorder.tsx
│       ├── hero/
│       │   ├── HeroSection.tsx
│       │   ├── HeroHeadline.tsx
│       │   └── TradingCard.tsx
│       ├── spire/
│       │   ├── TheSpire.tsx
│       │   ├── SpireTier.tsx
│       │   └── Flag.tsx
│       ├── scatter/
│       │   └── CeilingCostScatter.tsx
│       └── leaderboard/
│           ├── LeaderboardSection.tsx
│           ├── LeaderboardTabs.tsx
│           └── LeaderboardTable.tsx
└── tests/
    ├── scoring.test.ts
    ├── schemas.test.ts
    └── components/
        ├── RunPill.test.tsx
        ├── RunStrip.test.tsx
        └── TradingCard.test.tsx
```

**Responsibilities:**

- **`index.css`**: Global tokens via `@theme` directive; one `:root` block with defaults, `.dark` class override for Spire Mode.
- **`types/submission.ts`**: Authoritative TS types — all other code imports from here.
- **`data/schemas.ts`**: Zod schemas — the *validator* of incoming JSON; must be kept in sync with types (use `z.infer` if possible).
- **`data/scoring.ts`**: Pure functions, fully unit-tested; no React.
- **`components/shared/`**: Primitive UI atoms reused across sections.
- **`components/hero|spire|scatter|leaderboard/`**: Page sections. Each folder owns its section.
- **`routes/Home.tsx`**: Orchestrates sections vertically.

---

## Testing Strategy

- **Pure functions** (`scoring.ts`, `schemas.ts`): Strict TDD — write failing test first, minimal implementation, iterate.
- **React components**: Smoke tests (renders without crashing, renders expected content given mock props). Use `@testing-library/react`. Do not test animation timing or visual pixel output.
- **Integration** (`Home.tsx`): Single end-to-end test that loads fixture and asserts key text appears.
- **Visual/aesthetic verification**: Manual, via `npm run dev` in browser. Not automated in MVP.

---

## Task List

### Task 1: Scaffold Vite + React + TypeScript project

**Files:**
- Create: `leaderboard/package.json`
- Create: `leaderboard/vite.config.ts`
- Create: `leaderboard/tsconfig.json`
- Create: `leaderboard/tsconfig.node.json`
- Create: `leaderboard/index.html`
- Create: `leaderboard/src/main.tsx`
- Create: `leaderboard/src/App.tsx`
- Create: `leaderboard/.gitignore`
- Create: `leaderboard/README.md`

- [ ] **Step 1: Create directory and initialize**

Run from repo root `AgenticSTS\`:

```bash
mkdir leaderboard
cd leaderboard
```

- [ ] **Step 2: Write `package.json`**

Create `leaderboard/package.json`:

```json
{
  "name": "sts2-leaderboard",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc -b"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "motion": "^11.15.0",
    "recharts": "^2.15.0",
    "zod": "^3.24.0",
    "clsx": "^2.1.1"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.4",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/user-event": "^14.5.2",
    "jsdom": "^25.0.1",
    "vitest": "^3.0.0",
    "typescript": "^5.6.3",
    "vite": "^6.0.5",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0"
  }
}
```

- [ ] **Step 3: Install**

```bash
cd AgenticSTS/leaderboard
npm install
```

Expected: installs without errors. If Tailwind v4 is not yet at `^4.0.0` release, fall back to `"tailwindcss": "^4.0.0-beta"` and rerun.

- [ ] **Step 4: Write `tsconfig.json` and `tsconfig.node.json`**

Create `leaderboard/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals"],
    "paths": {
      "@/*": ["./src/*"]
    },
    "baseUrl": "."
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `leaderboard/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "emitDeclarationOnly": true,
    "outDir": "./.tsbuild-node",
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts"]
}
```

Note: a composite referenced project cannot have `noEmit: true` (TS6310). We use `emitDeclarationOnly: true` with a gitignored `outDir` so a tiny `.d.ts` lands outside source. The root `tsconfig.json`'s `noEmit: true` still applies to user source. The `typecheck` script uses plain `tsc -b` (not `tsc -b --noEmit`) for the same reason.

- [ ] **Step 5: Write `vite.config.ts`**

Create `leaderboard/vite.config.ts`:

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
  },
})
```

Note: `defineConfig` is imported from `vitest/config` (a superset of `vite`'s `defineConfig`) so the top-level `test` field typechecks without a separate vitest config file. The triple-slash reference directive ensures TypeScript loads Vitest's types even when `types` in `tsconfig.json` doesn't list vitest explicitly.

- [ ] **Step 6: Write `index.html` with font preload**

Create `leaderboard/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>STS2 Agent Leaderboard</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;500;600;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400&family=JetBrains+Mono:wght@400;500;600&family=Press+Start+2P&display=swap" rel="stylesheet">
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Write minimal `main.tsx` and `App.tsx`**

Create `leaderboard/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Create `leaderboard/src/App.tsx`:

```tsx
export default function App() {
  return (
    <main style={{ fontFamily: 'Cinzel, serif', padding: '2rem', textAlign: 'center' }}>
      <h1 style={{ fontSize: '4rem' }}>The Spire Awaits</h1>
      <p style={{ fontFamily: 'Fraunces, serif' }}>Leaderboard scaffold online.</p>
    </main>
  )
}
```

Create minimal `leaderboard/src/index.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 8: Write `.gitignore` and `README.md`**

Create `leaderboard/.gitignore`:

```
node_modules
dist
.env
.env.local
*.log
.vite
coverage
*.tsbuildinfo
.tsbuild-node
```

Create `leaderboard/README.md`:

```markdown
# STS2 Agent Leaderboard

Public-facing leaderboard for LLM agents playing Slay the Spire 2.

## Development

```bash
npm install
npm run dev       # dev server on :5173
npm run test      # run tests
npm run build     # production build to dist/
npm run preview   # preview production build
```

See `../docs/2026-04-17-leaderboard-design.md` for design spec.
```

- [ ] **Step 9: Verify dev server starts**

Run:

```bash
cd AgenticSTS/leaderboard
npm run dev
```

Expected: Vite prints `Local: http://localhost:5173/`. Open in browser and verify the Cinzel-styled "The Spire Awaits" renders. Stop with Ctrl+C.

- [ ] **Step 10: Commit**

```bash
cd AgenticSTS
git add leaderboard/
git commit -m "feat(leaderboard): scaffold Vite + React 19 + TS + Tailwind v4 project"
```

---

### Task 2: Theme tokens CSS + ThemeProvider + ThemeToggle

**Files:**
- Modify: `leaderboard/src/index.css`
- Create: `leaderboard/src/theme/ThemeProvider.tsx`
- Create: `leaderboard/src/hooks/useTheme.ts`
- Create: `leaderboard/src/components/shared/ThemeToggle.tsx`
- Modify: `leaderboard/src/App.tsx`

- [ ] **Step 1: Write theme tokens into `index.css`**

Replace `leaderboard/src/index.css` contents with:

```css
@import "tailwindcss";

@theme {
  /* Scholar View (light, default) */
  --color-bg-base: #faf7f2;
  --color-bg-raised: #f0ebe0;
  --color-ink-primary: #1a1625;
  --color-ink-secondary: #5a4f66;
  --color-accent-violet: #7c3aed;
  --color-accent-gold: #d4a017;
  --color-accent-magenta: #c2185b;
  --color-success: #2d7a3e;
  --color-danger: #b33a3a;

  /* STS Rarity (shared between themes) */
  --color-rarity-common: #b0a89e;
  --color-rarity-uncommon: #5fa8d3;
  --color-rarity-rare: #9b59b6;
  --color-rarity-elite: #e67e22;
  --color-rarity-legendary-from: #e74c3c;
  --color-rarity-legendary-to: #f4c430;

  /* Typography */
  --font-display: 'Cinzel', serif;
  --font-body: 'Fraunces', serif;
  --font-mono: 'JetBrains Mono', monospace;
  --font-pixel: 'Press Start 2P', monospace;

  /* Spacing scale (8px base) */
  --spacing-section-gap: 96px;
}

/* Spire Mode (dark) overrides */
:where(.dark) {
  --color-bg-base: #0d0818;
  --color-bg-raised: #1a0f2e;
  --color-ink-primary: #f0e6d2;
  --color-ink-secondary: #9b8aa3;
  --color-accent-gold: #f4c430;
  --color-accent-magenta: #e91e63;
  --color-accent-violet: #a78bfa;
  --color-fire-glow: #f97316;
  --spacing-section-gap: 64px;
}

:root, :root.dark {
  color-scheme: light dark;
}

html, body {
  margin: 0;
  padding: 0;
  background-color: var(--color-bg-base);
  color: var(--color-ink-primary);
  font-family: var(--font-body);
  transition: background-color 300ms ease, color 300ms ease;
}

/* Utility classes for fonts (Tailwind v4 reads @theme automatically,
   but we add explicit classes for clarity) */
.font-display { font-family: var(--font-display); }
.font-body    { font-family: var(--font-body); }
.font-mono    { font-family: var(--font-mono); }
.font-pixel   { font-family: var(--font-pixel); }
```

- [ ] **Step 2: Write the failing test for `useTheme` hook**

Create `leaderboard/tests/setup.ts` (needed by vitest):

```ts
import '@testing-library/jest-dom'
```

Create `leaderboard/tests/useTheme.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTheme } from '@/hooks/useTheme'
import { ThemeProvider } from '@/theme/ThemeProvider'
import type { ReactNode } from 'react'

const wrapper = ({ children }: { children: ReactNode }) => (
  <ThemeProvider>{children}</ThemeProvider>
)

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('defaults to light (Scholar) when no preference', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.theme).toBe('light')
  })

  it('toggles from light to dark and persists to localStorage', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => result.current.toggle())
    expect(result.current.theme).toBe('dark')
    expect(localStorage.getItem('sts2-theme')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('reads persisted theme on init', () => {
    localStorage.setItem('sts2-theme', 'dark')
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.theme).toBe('dark')
  })
})
```

- [ ] **Step 3: Run test, verify it fails**

```bash
cd AgenticSTS/leaderboard
npm run test -- useTheme
```

Expected: FAIL — module `@/hooks/useTheme` does not exist.

- [ ] **Step 4: Implement `ThemeProvider` and `useTheme`**

Create `leaderboard/src/theme/ThemeProvider.tsx`:

```tsx
import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react'

export type Theme = 'light' | 'dark'

export interface ThemeContextValue {
  theme: Theme
  toggle: () => void
  setTheme: (t: Theme) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

const STORAGE_KEY = 'sts2-theme'

function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark'
  return 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readInitialTheme)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
    window.localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const setTheme = useCallback((t: Theme) => setThemeState(t), [])
  const toggle = useCallback(() => setThemeState((t) => (t === 'light' ? 'dark' : 'light')), [])

  return (
    <ThemeContext.Provider value={{ theme, toggle, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
```

Create `leaderboard/src/hooks/useTheme.ts`:

```ts
import { useContext } from 'react'
import { ThemeContext } from '@/theme/ThemeProvider'

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
```

- [ ] **Step 5: Run test, verify passes**

```bash
npm run test -- useTheme
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Implement `ThemeToggle` component**

Create `leaderboard/src/components/shared/ThemeToggle.tsx`:

```tsx
import { useTheme } from '@/hooks/useTheme'
import { motion } from 'motion/react'

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      onClick={toggle}
      aria-label={isDark ? 'Switch to Scholar View' : 'Switch to Spire Mode'}
      className="relative h-10 w-10 rounded-full border border-[color:var(--color-ink-secondary)] bg-[color:var(--color-bg-raised)] transition hover:scale-110"
    >
      <motion.span
        key={theme}
        initial={{ opacity: 0, rotate: -30 }}
        animate={{ opacity: 1, rotate: 0 }}
        transition={{ duration: 0.3 }}
        className="absolute inset-0 flex items-center justify-center text-lg"
      >
        {isDark ? '🔥' : '🕯️'}
      </motion.span>
    </button>
  )
}
```

- [ ] **Step 7: Wire `ThemeProvider` into `App.tsx`**

Replace `leaderboard/src/App.tsx` with:

```tsx
import { ThemeProvider } from '@/theme/ThemeProvider'
import { ThemeToggle } from '@/components/shared/ThemeToggle'

export default function App() {
  return (
    <ThemeProvider>
      <main className="min-h-screen bg-[color:var(--color-bg-base)] p-8 text-[color:var(--color-ink-primary)]">
        <div className="flex justify-end">
          <ThemeToggle />
        </div>
        <div className="mx-auto max-w-4xl text-center">
          <h1 className="font-display text-6xl">The Spire Awaits</h1>
          <p className="font-body mt-4 text-lg text-[color:var(--color-ink-secondary)]">
            Can an LLM climb the Spire? One can.
          </p>
        </div>
      </main>
    </ThemeProvider>
  )
}
```

- [ ] **Step 8: Manual verify in browser**

```bash
npm run dev
```

Open `http://localhost:5173`. Verify:
- Page uses Cinzel for headline (distinctive serif, not generic)
- Default background is warm off-white (Scholar View)
- Clicking the candle icon toggles to dark midnight purple background
- The icon morphs between 🕯️ and 🔥
- Reloading preserves the last chosen theme
- Stop dev server with Ctrl+C

- [ ] **Step 9: Commit**

```bash
git add leaderboard/src leaderboard/tests
git commit -m "feat(leaderboard): add dual theme system (Scholar/Spire) with persistent toggle"
```

---

### Task 3: Type definitions + Zod schemas (TDD)

**Files:**
- Create: `leaderboard/src/types/submission.ts`
- Create: `leaderboard/src/data/schemas.ts`
- Create: `leaderboard/tests/schemas.test.ts`

- [ ] **Step 1: Write TypeScript types**

Create `leaderboard/src/types/submission.ts`:

```ts
export type Ascension = 0 | 1 | 2 | 3 | 4 | 5

export type RunOutcome = 'victory' | 'defeat' | 'abort'

export interface RunSummary {
  run_index: number           // 1-based position within the submission's run sequence
  ascension: Ascension
  outcome: RunOutcome
  final_floor: number         // 1..50-ish; undefined death floor = 0
  final_act: 1 | 2 | 3
  death_cause?: string
  duration_seconds: number
  per_run_score: number
  run_log_url?: string
}

export interface Relic {
  id: string                  // 'memory-store' | 'skill-library' | 'evolution-engine' | ...
  label: string
  description: string
}

export interface MethodInfo {
  name: string
  version: string
  authors: string[]
  description_short: string
  github_url?: string
  paper_url?: string
  relics: Relic[]
}

export interface ModelInfo {
  provider: 'anthropic' | 'openai' | 'google' | 'qwen' | 'other'
  name: string
  id: string
  tier_breakdown?: Partial<Record<'fast' | 'strategic' | 'analysis', string>>
}

export type Character = 'Silent' | 'Regent' | 'Watcher' | 'Defect' | 'Ironclad'

export interface Aggregate {
  ceiling: Ascension
  ceiling_consistency: number     // 0..1
  progress_score_mean: number
  progress_score_max: number
  avg_final_floor: number
  max_final_floor: number
  total_runs: number
  total_victories: number
}

export interface Cost {
  total_usd: number
  total_input_tokens: number
  total_output_tokens: number
  cost_per_run_usd: number
  cost_per_ascension_unlocked_usd: number
}

export interface Submission {
  id: string
  method: MethodInfo
  model: ModelInfo
  character: Character
  runs: RunSummary[]
  aggregate: Aggregate
  cost: Cost
  submitted_at: string           // ISO timestamp
  verified: boolean
}

export interface SubmissionBundle {
  schema_version: '1.0'
  built_at: string
  submissions: Submission[]
}
```

- [ ] **Step 2: Write failing schema tests**

Create `leaderboard/tests/schemas.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { submissionBundleSchema, submissionSchema } from '@/data/schemas'

const validRun = {
  run_index: 1,
  ascension: 4,
  outcome: 'victory',
  final_floor: 50,
  final_act: 3,
  duration_seconds: 420,
  per_run_score: 450,
}

const validSubmission = {
  id: 'fake-hcm-gemini-v03',
  method: {
    name: 'HCM-Agent',
    version: 'v0.3',
    authors: ['Team Sneko'],
    description_short: 'Training-free HCM + skills + evolution',
    relics: [
      { id: 'memory-store', label: 'Memory Store', description: 'Retains episodic memory.' },
    ],
  },
  model: {
    provider: 'google',
    name: 'Gemini 3.1 Pro',
    id: 'gemini-3.1-pro-preview',
  },
  character: 'Silent',
  runs: [validRun],
  aggregate: {
    ceiling: 4,
    ceiling_consistency: 0.2,
    progress_score_mean: 250,
    progress_score_max: 450,
    avg_final_floor: 35,
    max_final_floor: 50,
    total_runs: 1,
    total_victories: 1,
  },
  cost: {
    total_usd: 12.4,
    total_input_tokens: 1_800_000,
    total_output_tokens: 600_000,
    cost_per_run_usd: 12.4,
    cost_per_ascension_unlocked_usd: 3.1,
  },
  submitted_at: '2026-04-17T10:00:00Z',
  verified: true,
}

describe('submissionSchema', () => {
  it('accepts a valid submission', () => {
    expect(() => submissionSchema.parse(validSubmission)).not.toThrow()
  })

  it('rejects ascension > 5', () => {
    expect(() => submissionSchema.parse({
      ...validSubmission,
      aggregate: { ...validSubmission.aggregate, ceiling: 6 },
    })).toThrow()
  })

  it('rejects unknown outcome', () => {
    expect(() => submissionSchema.parse({
      ...validSubmission,
      runs: [{ ...validRun, outcome: 'banana' }],
    })).toThrow()
  })

  it('rejects missing method.relics', () => {
    const bad: Record<string, unknown> = JSON.parse(JSON.stringify(validSubmission))
    const method = bad.method as Record<string, unknown>
    delete method.relics
    expect(() => submissionSchema.parse(bad)).toThrow()
  })
})

describe('submissionBundleSchema', () => {
  it('accepts a valid bundle', () => {
    expect(() => submissionBundleSchema.parse({
      schema_version: '1.0',
      built_at: '2026-04-17T10:00:00Z',
      submissions: [validSubmission],
    })).not.toThrow()
  })

  it('rejects unsupported schema_version', () => {
    expect(() => submissionBundleSchema.parse({
      schema_version: '2.0',
      built_at: '2026-04-17T10:00:00Z',
      submissions: [],
    })).toThrow()
  })
})
```

- [ ] **Step 3: Run tests, verify they fail**

```bash
npm run test -- schemas
```

Expected: FAIL — module `@/data/schemas` missing.

- [ ] **Step 4: Implement Zod schemas**

Create `leaderboard/src/data/schemas.ts`:

```ts
import { z } from 'zod'

export const ascensionSchema = z.union([
  z.literal(0), z.literal(1), z.literal(2),
  z.literal(3), z.literal(4), z.literal(5),
])

export const runOutcomeSchema = z.enum(['victory', 'defeat', 'abort'])

export const runSummarySchema = z.object({
  run_index: z.number().int().min(1),
  ascension: ascensionSchema,
  outcome: runOutcomeSchema,
  final_floor: z.number().int().min(0),
  final_act: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  death_cause: z.string().optional(),
  duration_seconds: z.number().nonnegative(),
  per_run_score: z.number().nonnegative(),
  run_log_url: z.string().url().optional(),
})

export const relicSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  description: z.string(),
})

export const methodInfoSchema = z.object({
  name: z.string().min(1),
  version: z.string().min(1),
  authors: z.array(z.string()).min(1),
  description_short: z.string(),
  github_url: z.string().url().optional(),
  paper_url: z.string().url().optional(),
  relics: z.array(relicSchema),
})

export const modelInfoSchema = z.object({
  provider: z.enum(['anthropic', 'openai', 'google', 'qwen', 'other']),
  name: z.string().min(1),
  id: z.string().min(1),
  tier_breakdown: z.record(z.enum(['fast', 'strategic', 'analysis']), z.string()).optional(),
})

export const characterSchema = z.enum(['Silent', 'Regent', 'Watcher', 'Defect', 'Ironclad'])

export const aggregateSchema = z.object({
  ceiling: ascensionSchema,
  ceiling_consistency: z.number().min(0).max(1),
  progress_score_mean: z.number().nonnegative(),
  progress_score_max: z.number().nonnegative(),
  avg_final_floor: z.number().nonnegative(),
  max_final_floor: z.number().nonnegative(),
  total_runs: z.number().int().nonnegative(),
  total_victories: z.number().int().nonnegative(),
})

export const costSchema = z.object({
  total_usd: z.number().nonnegative(),
  total_input_tokens: z.number().int().nonnegative(),
  total_output_tokens: z.number().int().nonnegative(),
  cost_per_run_usd: z.number().nonnegative(),
  cost_per_ascension_unlocked_usd: z.number().nonnegative(),
})

export const submissionSchema = z.object({
  id: z.string().min(1),
  method: methodInfoSchema,
  model: modelInfoSchema,
  character: characterSchema,
  runs: z.array(runSummarySchema).min(1),
  aggregate: aggregateSchema,
  cost: costSchema,
  submitted_at: z.string(),
  verified: z.boolean(),
})

export const submissionBundleSchema = z.object({
  schema_version: z.literal('1.0'),
  built_at: z.string(),
  submissions: z.array(submissionSchema),
})
```

- [ ] **Step 5: Run tests, verify pass**

```bash
npm run test -- schemas
```

Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add leaderboard/src/types leaderboard/src/data leaderboard/tests/schemas.test.ts
git commit -m "feat(leaderboard): add Submission types and Zod validation schemas"
```

---

### Task 4: Scoring utilities (TDD)

**Files:**
- Create: `leaderboard/src/data/scoring.ts`
- Create: `leaderboard/tests/scoring.test.ts`

- [ ] **Step 1: Write failing scoring tests**

Create `leaderboard/tests/scoring.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import {
  perRunScore,
  ceiling,
  consistencyAtCeiling,
  aggregateFromRuns,
  filterScorableRuns,
} from '@/data/scoring'
import type { RunSummary } from '@/types/submission'

function mk(overrides: Partial<RunSummary>): RunSummary {
  return {
    run_index: 1,
    ascension: 0,
    outcome: 'defeat',
    final_floor: 10,
    final_act: 1,
    duration_seconds: 100,
    per_run_score: 0,
    ...overrides,
  }
}

describe('perRunScore', () => {
  it('A0 defeat f12 = 12', () => {
    expect(perRunScore(mk({ ascension: 0, outcome: 'defeat', final_floor: 12 }))).toBe(12)
  })
  it('A0 victory = 50', () => {
    expect(perRunScore(mk({ ascension: 0, outcome: 'victory', final_floor: 50 }))).toBe(50)
  })
  it('A4 victory = 450', () => {
    expect(perRunScore(mk({ ascension: 4, outcome: 'victory', final_floor: 50 }))).toBe(450)
  })
  it('A5 defeat f8 = 508 (higher than A4 victory 450)', () => {
    const a5 = perRunScore(mk({ ascension: 5, outcome: 'defeat', final_floor: 8 }))
    const a4v = perRunScore(mk({ ascension: 4, outcome: 'victory', final_floor: 50 }))
    expect(a5).toBe(508)
    expect(a5).toBeGreaterThan(a4v)
  })
  it('abort returns 0 (excluded from scoring)', () => {
    expect(perRunScore(mk({ ascension: 3, outcome: 'abort', final_floor: 22 }))).toBe(0)
  })
})

describe('filterScorableRuns', () => {
  it('excludes aborts', () => {
    const runs = [
      mk({ outcome: 'victory' }),
      mk({ outcome: 'defeat' }),
      mk({ outcome: 'abort' }),
    ]
    expect(filterScorableRuns(runs).length).toBe(2)
  })
})

describe('ceiling', () => {
  it('returns 0 when no victories', () => {
    expect(ceiling([mk({ ascension: 3, outcome: 'defeat' })])).toBe(0)
  })
  it('returns highest A with victory', () => {
    const runs = [
      mk({ ascension: 0, outcome: 'victory' }),
      mk({ ascension: 2, outcome: 'victory' }),
      mk({ ascension: 3, outcome: 'defeat' }),
      mk({ ascension: 4, outcome: 'victory' }),
      mk({ ascension: 5, outcome: 'defeat' }),
    ]
    expect(ceiling(runs)).toBe(4)
  })
  it('ignores aborts', () => {
    expect(ceiling([mk({ ascension: 4, outcome: 'abort' })])).toBe(0)
  })
})

describe('consistencyAtCeiling', () => {
  it('0 if no attempts at that ceiling', () => {
    expect(consistencyAtCeiling([mk({ ascension: 2, outcome: 'victory' })], 4)).toBe(0)
  })
  it('fraction of victories among attempts at that A', () => {
    const runs = [
      mk({ ascension: 4, outcome: 'victory' }),
      mk({ ascension: 4, outcome: 'defeat' }),
      mk({ ascension: 4, outcome: 'defeat' }),
      mk({ ascension: 4, outcome: 'victory' }),
      mk({ ascension: 4, outcome: 'defeat' }),
    ]
    expect(consistencyAtCeiling(runs, 4)).toBeCloseTo(0.4)
  })
})

describe('aggregateFromRuns', () => {
  it('computes all fields, ignoring aborts', () => {
    const runs = [
      mk({ ascension: 0, outcome: 'victory', final_floor: 50 }),   // score 50
      mk({ ascension: 1, outcome: 'victory', final_floor: 50 }),   // 150
      mk({ ascension: 2, outcome: 'defeat', final_floor: 34 }),    // 234
      mk({ ascension: 3, outcome: 'abort', final_floor: 1 }),      // excluded
    ]
    const agg = aggregateFromRuns(runs)
    expect(agg.ceiling).toBe(1)
    expect(agg.total_runs).toBe(3)
    expect(agg.total_victories).toBe(2)
    expect(agg.progress_score_max).toBe(234)
    expect(agg.progress_score_mean).toBeCloseTo((50 + 150 + 234) / 3)
    expect(agg.avg_final_floor).toBeCloseTo((50 + 50 + 34) / 3)
    expect(agg.max_final_floor).toBe(50)
  })
})
```

- [ ] **Step 2: Run, verify fail**

```bash
npm run test -- scoring
```

Expected: FAIL — module `@/data/scoring` missing.

- [ ] **Step 3: Implement scoring functions**

Create `leaderboard/src/data/scoring.ts`:

```ts
import type { Aggregate, Ascension, RunSummary } from '@/types/submission'

/**
 * Per-run progress score.
 *
 * Formula: ascension * 100 + (50 if victory else final_floor)
 *
 * Reasoning: Each ascension tier is worth 100 "progress units" (since reaching
 * A_n requires having beaten A_(n-1)). Victory is worth +50, equivalent to
 * completing the ~50-floor tower. Aborts are excluded (return 0).
 */
export function perRunScore(run: RunSummary): number {
  if (run.outcome === 'abort') return 0
  return run.ascension * 100 + (run.outcome === 'victory' ? 50 : run.final_floor)
}

/** Filter out aborts — they don't count toward any aggregate statistic. */
export function filterScorableRuns(runs: readonly RunSummary[]): RunSummary[] {
  return runs.filter((r) => r.outcome !== 'abort')
}

/** Highest ascension with at least one victory. Returns 0 if no victories. */
export function ceiling(runs: readonly RunSummary[]): Ascension {
  const victories = runs.filter((r) => r.outcome === 'victory')
  if (victories.length === 0) return 0
  const maxA = Math.max(...victories.map((r) => r.ascension))
  return maxA as Ascension
}

/** Win rate among runs that attempted the given ascension. 0 if no attempts. */
export function consistencyAtCeiling(runs: readonly RunSummary[], c: Ascension): number {
  const attempts = runs.filter((r) => r.ascension === c && r.outcome !== 'abort')
  if (attempts.length === 0) return 0
  const wins = attempts.filter((r) => r.outcome === 'victory').length
  return wins / attempts.length
}

/** Compute all aggregate stats for a submission from its runs. */
export function aggregateFromRuns(runs: readonly RunSummary[]): Aggregate {
  const scorable = filterScorableRuns(runs)
  const scores = scorable.map(perRunScore)
  const floors = scorable.map((r) => r.final_floor)
  const c = ceiling(scorable)

  const mean = (xs: number[]) => (xs.length === 0 ? 0 : xs.reduce((a, b) => a + b, 0) / xs.length)
  const max = (xs: number[]) => (xs.length === 0 ? 0 : Math.max(...xs))

  return {
    ceiling: c,
    ceiling_consistency: consistencyAtCeiling(scorable, c),
    progress_score_mean: mean(scores),
    progress_score_max: max(scores),
    avg_final_floor: mean(floors),
    max_final_floor: max(floors),
    total_runs: scorable.length,
    total_victories: scorable.filter((r) => r.outcome === 'victory').length,
  }
}
```

- [ ] **Step 4: Run, verify pass**

```bash
npm run test -- scoring
```

Expected: all ~10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add leaderboard/src/data/scoring.ts leaderboard/tests/scoring.test.ts
git commit -m "feat(leaderboard): add progress score + aggregate computation (TDD)"
```

---

### Task 5: Mock fixture data

**Files:**
- Create: `leaderboard/public/data/submissions.json`

- [ ] **Step 1: Design 6 fake submissions with realistic variety**

The fixture must include:
- 1 SOTA submission (ours, Gemini, ceiling A4)
- 1 secondary strong submission (ours, GPT, ceiling A3)
- 1 budget submission (ours, Qwen, ceiling A2, cheapest)
- 2 competitor baselines (fake names, ceilings A1-A2)
- 1 weak baseline (ceiling A0)

- [ ] **Step 2: Write fixture**

Create `leaderboard/public/data/submissions.json`:

```json
{
  "schema_version": "1.0",
  "built_at": "2026-04-17T12:00:00Z",
  "submissions": [
    {
      "id": "hcm-gemini-3-1-pro-silent",
      "method": {
        "name": "HCM-Agent",
        "version": "v0.3",
        "authors": ["Team Sneko"],
        "description_short": "Training-free hierarchical memory + skill retrieval + self-evolution.",
        "relics": [
          { "id": "memory-store", "label": "Memory Store", "description": "Hierarchical categorical episodic memory." },
          { "id": "skill-library", "label": "Skill Library", "description": "Retrieval-augmented strategy skills." },
          { "id": "evolution-engine", "label": "Evolution Engine", "description": "Post-run LLM self-evolution." }
        ]
      },
      "model": { "provider": "google", "name": "Gemini 3.1 Pro", "id": "gemini-3.1-pro-preview" },
      "character": "Silent",
      "runs": [
        { "run_index": 1,  "ascension": 0, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 480, "per_run_score": 50 },
        { "run_index": 2,  "ascension": 1, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 510, "per_run_score": 150 },
        { "run_index": 3,  "ascension": 2, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 520, "per_run_score": 250 },
        { "run_index": 4,  "ascension": 3, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 540, "per_run_score": 350 },
        { "run_index": 5,  "ascension": 4, "outcome": "defeat",  "final_floor": 38, "final_act": 3, "death_cause": "Time Eater", "duration_seconds": 410, "per_run_score": 438 },
        { "run_index": 6,  "ascension": 4, "outcome": "defeat",  "final_floor": 42, "final_act": 3, "death_cause": "Awakened One", "duration_seconds": 430, "per_run_score": 442 },
        { "run_index": 7,  "ascension": 4, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 560, "per_run_score": 450 },
        { "run_index": 8,  "ascension": 5, "outcome": "defeat",  "final_floor": 8,  "final_act": 1, "death_cause": "Reptomancer (Elite)", "duration_seconds": 120, "per_run_score": 508 },
        { "run_index": 9,  "ascension": 5, "outcome": "defeat",  "final_floor": 12, "final_act": 1, "death_cause": "Sentry Trio", "duration_seconds": 180, "per_run_score": 512 },
        { "run_index": 10, "ascension": 5, "outcome": "defeat",  "final_floor": 6,  "final_act": 1, "death_cause": "Gremlin Nob (Elite)", "duration_seconds": 95, "per_run_score": 506 }
      ],
      "aggregate": {
        "ceiling": 4,
        "ceiling_consistency": 0.33,
        "progress_score_mean": 365.6,
        "progress_score_max": 512,
        "avg_final_floor": 35.6,
        "max_final_floor": 50,
        "total_runs": 10,
        "total_victories": 5
      },
      "cost": {
        "total_usd": 12.40,
        "total_input_tokens": 1800000,
        "total_output_tokens": 600000,
        "cost_per_run_usd": 1.24,
        "cost_per_ascension_unlocked_usd": 3.10
      },
      "submitted_at": "2026-04-16T20:00:00Z",
      "verified": true
    },
    {
      "id": "hcm-gpt-5-4-thinking-silent",
      "method": {
        "name": "HCM-Agent",
        "version": "v0.3",
        "authors": ["Team Sneko"],
        "description_short": "Same HCM pipeline, different model.",
        "relics": [
          { "id": "memory-store", "label": "Memory Store", "description": "Hierarchical categorical episodic memory." },
          { "id": "skill-library", "label": "Skill Library", "description": "Retrieval-augmented strategy skills." },
          { "id": "evolution-engine", "label": "Evolution Engine", "description": "Post-run LLM self-evolution." }
        ]
      },
      "model": { "provider": "openai", "name": "GPT-5.4 Thinking", "id": "gpt-5.4-thinking" },
      "character": "Silent",
      "runs": [
        { "run_index": 1,  "ascension": 0, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 700, "per_run_score": 50 },
        { "run_index": 2,  "ascension": 1, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 720, "per_run_score": 150 },
        { "run_index": 3,  "ascension": 2, "outcome": "defeat",  "final_floor": 28, "final_act": 2, "death_cause": "Slavers", "duration_seconds": 380, "per_run_score": 228 },
        { "run_index": 4,  "ascension": 2, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 760, "per_run_score": 250 },
        { "run_index": 5,  "ascension": 3, "outcome": "defeat",  "final_floor": 22, "final_act": 2, "death_cause": "Champion", "duration_seconds": 320, "per_run_score": 322 },
        { "run_index": 6,  "ascension": 3, "outcome": "defeat",  "final_floor": 18, "final_act": 2, "death_cause": "Hexaghost", "duration_seconds": 280, "per_run_score": 318 },
        { "run_index": 7,  "ascension": 3, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 810, "per_run_score": 350 },
        { "run_index": 8,  "ascension": 4, "outcome": "defeat",  "final_floor": 15, "final_act": 1, "death_cause": "Lagavulin (Elite)", "duration_seconds": 220, "per_run_score": 415 },
        { "run_index": 9,  "ascension": 4, "outcome": "defeat",  "final_floor": 9,  "final_act": 1, "death_cause": "Louse pack", "duration_seconds": 140, "per_run_score": 409 },
        { "run_index": 10, "ascension": 4, "outcome": "defeat",  "final_floor": 5,  "final_act": 1, "death_cause": "Gremlin Gang", "duration_seconds": 80,  "per_run_score": 405 }
      ],
      "aggregate": {
        "ceiling": 3,
        "ceiling_consistency": 0.33,
        "progress_score_mean": 289.7,
        "progress_score_max": 415,
        "avg_final_floor": 32.7,
        "max_final_floor": 50,
        "total_runs": 10,
        "total_victories": 4
      },
      "cost": {
        "total_usd": 38.10,
        "total_input_tokens": 900000,
        "total_output_tokens": 400000,
        "cost_per_run_usd": 3.81,
        "cost_per_ascension_unlocked_usd": 12.70
      },
      "submitted_at": "2026-04-15T18:00:00Z",
      "verified": true
    },
    {
      "id": "hcm-qwen-3-5-silent",
      "method": {
        "name": "HCM-Agent",
        "version": "v0.3",
        "authors": ["Team Sneko"],
        "description_short": "Budget-tier run — same HCM on Qwen.",
        "relics": [
          { "id": "memory-store", "label": "Memory Store", "description": "Hierarchical categorical episodic memory." },
          { "id": "skill-library", "label": "Skill Library", "description": "Retrieval-augmented strategy skills." }
        ]
      },
      "model": { "provider": "qwen", "name": "Qwen 3.5 Max", "id": "qwen-3.5-max" },
      "character": "Silent",
      "runs": [
        { "run_index": 1,  "ascension": 0, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 360, "per_run_score": 50 },
        { "run_index": 2,  "ascension": 1, "outcome": "defeat",  "final_floor": 34, "final_act": 2, "death_cause": "Collector", "duration_seconds": 290, "per_run_score": 134 },
        { "run_index": 3,  "ascension": 1, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 380, "per_run_score": 150 },
        { "run_index": 4,  "ascension": 2, "outcome": "defeat",  "final_floor": 20, "final_act": 2, "death_cause": "Book of Stabbing", "duration_seconds": 230, "per_run_score": 220 },
        { "run_index": 5,  "ascension": 2, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 410, "per_run_score": 250 },
        { "run_index": 6,  "ascension": 3, "outcome": "defeat",  "final_floor": 11, "final_act": 1, "death_cause": "Looter", "duration_seconds": 160, "per_run_score": 311 },
        { "run_index": 7,  "ascension": 3, "outcome": "defeat",  "final_floor": 8,  "final_act": 1, "death_cause": "Jaw Worm", "duration_seconds": 100, "per_run_score": 308 },
        { "run_index": 8,  "ascension": 3, "outcome": "defeat",  "final_floor": 14, "final_act": 1, "death_cause": "Exordium Thugs", "duration_seconds": 180, "per_run_score": 314 },
        { "run_index": 9,  "ascension": 3, "outcome": "defeat",  "final_floor": 7,  "final_act": 1, "death_cause": "Cultist", "duration_seconds": 90,  "per_run_score": 307 },
        { "run_index": 10, "ascension": 3, "outcome": "defeat",  "final_floor": 10, "final_act": 1, "death_cause": "Sentry Pair", "duration_seconds": 120, "per_run_score": 310 }
      ],
      "aggregate": {
        "ceiling": 2,
        "ceiling_consistency": 0.50,
        "progress_score_mean": 235.4,
        "progress_score_max": 314,
        "avg_final_floor": 25.4,
        "max_final_floor": 50,
        "total_runs": 10,
        "total_victories": 3
      },
      "cost": {
        "total_usd": 4.20,
        "total_input_tokens": 2100000,
        "total_output_tokens": 700000,
        "cost_per_run_usd": 0.42,
        "cost_per_ascension_unlocked_usd": 2.10
      },
      "submitted_at": "2026-04-14T12:00:00Z",
      "verified": true
    },
    {
      "id": "voyager-sts-gpt-silent",
      "method": {
        "name": "Voyager-STS",
        "version": "v0.1",
        "authors": ["Anonymous Baseline"],
        "description_short": "Adapted Voyager architecture with code-based skill library.",
        "relics": [
          { "id": "skill-library", "label": "Skill Library", "description": "Code-based iterative skill bank." }
        ]
      },
      "model": { "provider": "openai", "name": "GPT-5.4", "id": "gpt-5.4" },
      "character": "Silent",
      "runs": [
        { "run_index": 1,  "ascension": 0, "outcome": "defeat",  "final_floor": 34, "final_act": 2, "death_cause": "Collector", "duration_seconds": 420, "per_run_score": 34 },
        { "run_index": 2,  "ascension": 0, "outcome": "defeat",  "final_floor": 12, "final_act": 1, "death_cause": "Jaw Worm", "duration_seconds": 160, "per_run_score": 12 },
        { "run_index": 3,  "ascension": 0, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 780, "per_run_score": 50 },
        { "run_index": 4,  "ascension": 1, "outcome": "defeat",  "final_floor": 8,  "final_act": 1, "death_cause": "Louses", "duration_seconds": 110, "per_run_score": 108 },
        { "run_index": 5,  "ascension": 1, "outcome": "defeat",  "final_floor": 24, "final_act": 2, "death_cause": "Slavers", "duration_seconds": 330, "per_run_score": 124 },
        { "run_index": 6,  "ascension": 1, "outcome": "defeat",  "final_floor": 15, "final_act": 1, "death_cause": "Sentry Trio", "duration_seconds": 210, "per_run_score": 115 },
        { "run_index": 7,  "ascension": 1, "outcome": "defeat",  "final_floor": 12, "final_act": 1, "death_cause": "Gremlin Nob (Elite)", "duration_seconds": 170, "per_run_score": 112 },
        { "run_index": 8,  "ascension": 1, "outcome": "defeat",  "final_floor": 5,  "final_act": 1, "death_cause": "Exordium Wildlife", "duration_seconds": 60,  "per_run_score": 105 },
        { "run_index": 9,  "ascension": 1, "outcome": "defeat",  "final_floor": 3,  "final_act": 1, "death_cause": "Cultist", "duration_seconds": 45,  "per_run_score": 103 },
        { "run_index": 10, "ascension": 1, "outcome": "defeat",  "final_floor": 7,  "final_act": 1, "death_cause": "Fungi Beasts", "duration_seconds": 90,  "per_run_score": 107 }
      ],
      "aggregate": {
        "ceiling": 0,
        "ceiling_consistency": 0.33,
        "progress_score_mean": 87.0,
        "progress_score_max": 124,
        "avg_final_floor": 17.0,
        "max_final_floor": 50,
        "total_runs": 10,
        "total_victories": 1
      },
      "cost": {
        "total_usd": 21.20,
        "total_input_tokens": 800000,
        "total_output_tokens": 300000,
        "cost_per_run_usd": 2.12,
        "cost_per_ascension_unlocked_usd": 21.20
      },
      "submitted_at": "2026-04-10T09:00:00Z",
      "verified": true
    },
    {
      "id": "react-rag-claude-silent",
      "method": {
        "name": "ReAct+RAG",
        "version": "v1.0",
        "authors": ["Anonymous Baseline"],
        "description_short": "Vanilla ReAct agent with RAG over game wiki.",
        "relics": [
          { "id": "web-search", "label": "Wiki RAG", "description": "Retrieves from STS wiki." }
        ]
      },
      "model": { "provider": "anthropic", "name": "Claude 4.6 Sonnet", "id": "claude-4.6-sonnet" },
      "character": "Silent",
      "runs": [
        { "run_index": 1,  "ascension": 0, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 540, "per_run_score": 50 },
        { "run_index": 2,  "ascension": 1, "outcome": "defeat",  "final_floor": 30, "final_act": 2, "death_cause": "Reptomancer", "duration_seconds": 380, "per_run_score": 130 },
        { "run_index": 3,  "ascension": 1, "outcome": "defeat",  "final_floor": 22, "final_act": 2, "death_cause": "Champion", "duration_seconds": 290, "per_run_score": 122 },
        { "run_index": 4,  "ascension": 1, "outcome": "victory", "final_floor": 50, "final_act": 3, "duration_seconds": 610, "per_run_score": 150 },
        { "run_index": 5,  "ascension": 2, "outcome": "defeat",  "final_floor": 14, "final_act": 1, "death_cause": "Lagavulin (Elite)", "duration_seconds": 200, "per_run_score": 214 },
        { "run_index": 6,  "ascension": 2, "outcome": "defeat",  "final_floor": 19, "final_act": 2, "death_cause": "Book of Stabbing", "duration_seconds": 260, "per_run_score": 219 },
        { "run_index": 7,  "ascension": 2, "outcome": "defeat",  "final_floor": 11, "final_act": 1, "death_cause": "Fungi Beasts", "duration_seconds": 150, "per_run_score": 211 },
        { "run_index": 8,  "ascension": 2, "outcome": "defeat",  "final_floor": 7,  "final_act": 1, "death_cause": "Cultist", "duration_seconds": 100, "per_run_score": 207 },
        { "run_index": 9,  "ascension": 2, "outcome": "defeat",  "final_floor": 13, "final_act": 1, "death_cause": "Sentry Trio", "duration_seconds": 180, "per_run_score": 213 },
        { "run_index": 10, "ascension": 2, "outcome": "defeat",  "final_floor": 6,  "final_act": 1, "death_cause": "Exordium Thugs", "duration_seconds": 85,  "per_run_score": 206 }
      ],
      "aggregate": {
        "ceiling": 1,
        "ceiling_consistency": 0.33,
        "progress_score_mean": 172.2,
        "progress_score_max": 219,
        "avg_final_floor": 22.2,
        "max_final_floor": 50,
        "total_runs": 10,
        "total_victories": 2
      },
      "cost": {
        "total_usd": 18.50,
        "total_input_tokens": 600000,
        "total_output_tokens": 200000,
        "cost_per_run_usd": 1.85,
        "cost_per_ascension_unlocked_usd": 18.50
      },
      "submitted_at": "2026-04-08T15:00:00Z",
      "verified": true
    },
    {
      "id": "naive-prompt-gpt-silent",
      "method": {
        "name": "Zero-Shot",
        "version": "v0.1",
        "authors": ["Anonymous Baseline"],
        "description_short": "Plain prompt, no memory, no skills, no retrieval.",
        "relics": []
      },
      "model": { "provider": "openai", "name": "GPT-5.4", "id": "gpt-5.4" },
      "character": "Silent",
      "runs": [
        { "run_index": 1,  "ascension": 0, "outcome": "defeat",  "final_floor": 22, "final_act": 2, "death_cause": "Slavers", "duration_seconds": 300, "per_run_score": 22 },
        { "run_index": 2,  "ascension": 0, "outcome": "defeat",  "final_floor": 10, "final_act": 1, "death_cause": "Gremlin Pack", "duration_seconds": 140, "per_run_score": 10 },
        { "run_index": 3,  "ascension": 0, "outcome": "defeat",  "final_floor": 8,  "final_act": 1, "death_cause": "Louses", "duration_seconds": 100, "per_run_score": 8 },
        { "run_index": 4,  "ascension": 0, "outcome": "defeat",  "final_floor": 14, "final_act": 1, "death_cause": "Sentry Trio", "duration_seconds": 180, "per_run_score": 14 },
        { "run_index": 5,  "ascension": 0, "outcome": "defeat",  "final_floor": 6,  "final_act": 1, "death_cause": "Cultist", "duration_seconds": 80,  "per_run_score": 6 },
        { "run_index": 6,  "ascension": 0, "outcome": "defeat",  "final_floor": 11, "final_act": 1, "death_cause": "Fungi Beasts", "duration_seconds": 140, "per_run_score": 11 },
        { "run_index": 7,  "ascension": 0, "outcome": "defeat",  "final_floor": 18, "final_act": 2, "death_cause": "Hexaghost", "duration_seconds": 250, "per_run_score": 18 },
        { "run_index": 8,  "ascension": 0, "outcome": "defeat",  "final_floor": 9,  "final_act": 1, "death_cause": "Jaw Worm", "duration_seconds": 110, "per_run_score": 9 },
        { "run_index": 9,  "ascension": 0, "outcome": "defeat",  "final_floor": 13, "final_act": 1, "death_cause": "Exordium Wildlife", "duration_seconds": 170, "per_run_score": 13 },
        { "run_index": 10, "ascension": 0, "outcome": "defeat",  "final_floor": 7,  "final_act": 1, "death_cause": "Lagavulin (Elite)", "duration_seconds": 95,  "per_run_score": 7 }
      ],
      "aggregate": {
        "ceiling": 0,
        "ceiling_consistency": 0.0,
        "progress_score_mean": 11.8,
        "progress_score_max": 22,
        "avg_final_floor": 11.8,
        "max_final_floor": 22,
        "total_runs": 10,
        "total_victories": 0
      },
      "cost": {
        "total_usd": 8.60,
        "total_input_tokens": 400000,
        "total_output_tokens": 150000,
        "cost_per_run_usd": 0.86,
        "cost_per_ascension_unlocked_usd": 999.99
      },
      "submitted_at": "2026-04-05T11:00:00Z",
      "verified": true
    }
  ]
}
```

- [ ] **Step 3: Validate fixture against schema**

Add this test to `leaderboard/tests/schemas.test.ts` (append to the file):

```ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('fixture submissions.json', () => {
  it('validates against submissionBundleSchema', () => {
    const raw = readFileSync(
      resolve(__dirname, '../public/data/submissions.json'),
      'utf-8',
    )
    const data = JSON.parse(raw)
    expect(() => submissionBundleSchema.parse(data)).not.toThrow()
  })
})
```

- [ ] **Step 4: Run**

```bash
npm run test -- schemas
```

Expected: all tests PASS (including the fixture validation).

- [ ] **Step 5: Commit**

```bash
git add leaderboard/public/data/submissions.json leaderboard/tests/schemas.test.ts
git commit -m "feat(leaderboard): add mock fixture with 6 submissions spanning A0-A4 ceilings"
```

---

### Task 6: Data loader

**Files:**
- Create: `leaderboard/src/data/loadSubmissions.ts`
- Create: `leaderboard/tests/loadSubmissions.test.ts`

- [ ] **Step 1: Write failing test**

Create `leaderboard/tests/loadSubmissions.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { loadSubmissions } from '@/data/loadSubmissions'

const validBundle = {
  schema_version: '1.0',
  built_at: '2026-04-17T12:00:00Z',
  submissions: [],
}

describe('loadSubmissions', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches /data/submissions.json and returns parsed bundle', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => validBundle,
    })
    vi.stubGlobal('fetch', fetchMock)

    const bundle = await loadSubmissions()
    expect(fetchMock).toHaveBeenCalledWith('/data/submissions.json')
    expect(bundle.schema_version).toBe('1.0')
  })

  it('throws if HTTP fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))
    await expect(loadSubmissions()).rejects.toThrow(/HTTP 500/)
  })

  it('throws on schema validation failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ schema_version: '9.9', built_at: '', submissions: [] }),
    }))
    await expect(loadSubmissions()).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Run, verify fail**

```bash
npm run test -- loadSubmissions
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement loader**

Create `leaderboard/src/data/loadSubmissions.ts`:

```ts
import { submissionBundleSchema } from './schemas'
import type { SubmissionBundle } from '@/types/submission'

export async function loadSubmissions(
  url = '/data/submissions.json',
): Promise<SubmissionBundle> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status} loading submissions`)
  const raw = await res.json()
  return submissionBundleSchema.parse(raw) as SubmissionBundle
}
```

- [ ] **Step 4: Run, verify pass**

```bash
npm run test -- loadSubmissions
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add leaderboard/src/data/loadSubmissions.ts leaderboard/tests/loadSubmissions.test.ts
git commit -m "feat(leaderboard): add fetch+validate data loader"
```

---

### Task 7: RunPill + RunStrip components

**Files:**
- Create: `leaderboard/src/components/shared/RunPill.tsx`
- Create: `leaderboard/src/components/shared/RunStrip.tsx`
- Create: `leaderboard/tests/components/RunPill.test.tsx`
- Create: `leaderboard/tests/components/RunStrip.test.tsx`

- [ ] **Step 1: Write failing RunPill test**

Create `leaderboard/tests/components/RunPill.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RunPill } from '@/components/shared/RunPill'
import type { RunSummary } from '@/types/submission'

const mk = (overrides: Partial<RunSummary>): RunSummary => ({
  run_index: 1,
  ascension: 0,
  outcome: 'defeat',
  final_floor: 10,
  final_act: 1,
  duration_seconds: 100,
  per_run_score: 0,
  ...overrides,
})

describe('RunPill', () => {
  it('shows A4 and checkmark for A4 victory', () => {
    render(<RunPill run={mk({ ascension: 4, outcome: 'victory', final_floor: 50, final_act: 3 })} />)
    expect(screen.getByText(/A4/)).toBeInTheDocument()
    expect(screen.getByText(/✓/)).toBeInTheDocument()
  })

  it('shows A2 and floor number for A2 defeat on floor 28', () => {
    render(<RunPill run={mk({ ascension: 2, outcome: 'defeat', final_floor: 28, final_act: 2 })} />)
    expect(screen.getByText(/A2/)).toBeInTheDocument()
    expect(screen.getByText(/28/)).toBeInTheDocument()
  })

  it('shows "—" for abort', () => {
    render(<RunPill run={mk({ ascension: 3, outcome: 'abort' })} />)
    expect(screen.getByText(/A3/)).toBeInTheDocument()
    expect(screen.getByText(/—/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run, verify fail**

```bash
npm run test -- RunPill
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement RunPill**

Create `leaderboard/src/components/shared/RunPill.tsx`:

```tsx
import clsx from 'clsx'
import type { RunSummary } from '@/types/submission'

const RARITY_BG: Record<number, string> = {
  0: 'bg-[color:var(--color-rarity-common)]',
  1: 'bg-[color:var(--color-rarity-uncommon)]',
  2: 'bg-[color:var(--color-rarity-rare)]',
  3: 'bg-[color:var(--color-rarity-elite)]',
  4: 'bg-gradient-to-br from-[color:var(--color-rarity-legendary-from)] to-[color:var(--color-rarity-legendary-to)]',
  5: 'bg-gradient-to-br from-fuchsia-500 via-yellow-400 to-cyan-400 animate-pulse',
}

function saturationClass(outcome: RunSummary['outcome'], finalAct: RunSummary['final_act']): string {
  if (outcome === 'victory') return 'opacity-100 ring-2 ring-[color:var(--color-accent-gold)]'
  if (outcome === 'abort') return 'opacity-30 border border-dashed border-[color:var(--color-ink-secondary)]'
  // defeat: saturation by act
  if (finalAct === 3) return 'opacity-80'
  if (finalAct === 2) return 'opacity-55'
  return 'opacity-30'
}

export interface RunPillProps {
  run: RunSummary
  onMouseEnter?: () => void
}

export function RunPill({ run, onMouseEnter }: RunPillProps) {
  const label =
    run.outcome === 'victory' ? '✓' :
    run.outcome === 'abort' ? '—' :
    String(run.final_floor)

  const title =
    run.outcome === 'victory' ? `A${run.ascension} Victory — Run ${run.run_index}` :
    run.outcome === 'abort'   ? `A${run.ascension} Aborted — Run ${run.run_index}` :
                                `A${run.ascension}, died floor ${run.final_floor}` +
                                (run.death_cause ? ` (${run.death_cause})` : '') +
                                ` — Run ${run.run_index}`

  return (
    <div
      onMouseEnter={onMouseEnter}
      title={title}
      className={clsx(
        'inline-flex h-7 w-9 flex-col items-center justify-center rounded text-center transition-transform hover:scale-110',
        RARITY_BG[run.ascension],
        saturationClass(run.outcome, run.final_act),
      )}
    >
      <span className="font-pixel text-[8px] leading-none text-white drop-shadow">A{run.ascension}</span>
      <span className="font-mono text-[10px] leading-none text-white drop-shadow">{label}</span>
    </div>
  )
}
```

- [ ] **Step 4: Run, verify RunPill tests pass**

```bash
npm run test -- RunPill
```

Expected: 3 tests PASS.

- [ ] **Step 5: Write failing RunStrip test**

Create `leaderboard/tests/components/RunStrip.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { RunStrip } from '@/components/shared/RunStrip'
import type { RunSummary } from '@/types/submission'

const mkRuns = (n: number): RunSummary[] =>
  Array.from({ length: n }, (_, i) => ({
    run_index: i + 1,
    ascension: 0,
    outcome: 'defeat',
    final_floor: 10,
    final_act: 1,
    duration_seconds: 100,
    per_run_score: 10,
  }))

describe('RunStrip', () => {
  it('renders N pills for N runs', () => {
    const { container } = render(<RunStrip runs={mkRuns(10)} />)
    const pills = container.querySelectorAll('[title]')
    expect(pills.length).toBe(10)
  })
})
```

- [ ] **Step 6: Implement RunStrip**

Create `leaderboard/src/components/shared/RunStrip.tsx`:

```tsx
import type { RunSummary } from '@/types/submission'
import { RunPill } from './RunPill'

export interface RunStripProps {
  runs: RunSummary[]
}

export function RunStrip({ runs }: RunStripProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {runs.map((r) => (
        <RunPill key={r.run_index} run={r} />
      ))}
    </div>
  )
}
```

- [ ] **Step 7: Run all component tests**

```bash
npm run test -- components
```

Expected: RunPill (3) + RunStrip (1) tests PASS.

- [ ] **Step 8: Commit**

```bash
git add leaderboard/src/components/shared/RunPill.tsx leaderboard/src/components/shared/RunStrip.tsx leaderboard/tests/components
git commit -m "feat(leaderboard): add RunPill + RunStrip for compact run sequence display"
```

---

### Task 8: PotionGauge + RarityBorder primitives

**Files:**
- Create: `leaderboard/src/components/shared/PotionGauge.tsx`
- Create: `leaderboard/src/components/shared/RarityBorder.tsx`
- Create: `leaderboard/tests/components/PotionGauge.test.tsx`

- [ ] **Step 1: Write failing PotionGauge test**

Create `leaderboard/tests/components/PotionGauge.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PotionGauge } from '@/components/shared/PotionGauge'

describe('PotionGauge', () => {
  it('shows 3 full bottles for cheapest (well below median)', () => {
    render(<PotionGauge costUsd={4} medianUsd={20} />)
    expect(screen.getByLabelText(/3 \/ 3/)).toBeInTheDocument()
  })

  it('shows 2 bottles for around-median', () => {
    render(<PotionGauge costUsd={20} medianUsd={20} />)
    expect(screen.getByLabelText(/2 \/ 3/)).toBeInTheDocument()
  })

  it('shows 1 bottle for far above median', () => {
    render(<PotionGauge costUsd={80} medianUsd={20} />)
    expect(screen.getByLabelText(/1 \/ 3/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Implement PotionGauge**

Create `leaderboard/src/components/shared/PotionGauge.tsx`:

```tsx
import clsx from 'clsx'

export interface PotionGaugeProps {
  /** Cost in USD for this submission. */
  costUsd: number
  /** Median cost across all submissions (for relative scaling). */
  medianUsd: number
}

/** 3 bottles = cheaper than half of median, 2 = roughly median, 1 = far above */
function bottlesFor(costUsd: number, medianUsd: number): 1 | 2 | 3 {
  const ratio = costUsd / medianUsd
  if (ratio <= 0.5) return 3
  if (ratio <= 1.5) return 2
  return 1
}

function Bottle({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 16 24" width="16" height="24" aria-hidden="true">
      <rect x="6" y="1" width="4" height="3" rx="1" fill="currentColor" opacity="0.6" />
      <rect x="5" y="4" width="6" height="2" fill="currentColor" opacity="0.4" />
      <path
        d="M 4 6 L 12 6 L 13 10 Q 14 14 13 18 Q 12 22 8 22 Q 4 22 3 18 Q 2 14 3 10 Z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1"
      />
    </svg>
  )
}

export function PotionGauge({ costUsd, medianUsd }: PotionGaugeProps) {
  const filled = bottlesFor(costUsd, medianUsd)
  return (
    <div
      aria-label={`Cost efficiency: ${filled} / 3 potions`}
      className={clsx('inline-flex gap-0.5', {
        'text-[color:var(--color-success)]': filled === 3,
        'text-[color:var(--color-accent-gold)]': filled === 2,
        'text-[color:var(--color-danger)]': filled === 1,
      })}
    >
      {[0, 1, 2].map((i) => (
        <Bottle key={i} filled={i < filled} />
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Run tests**

```bash
npm run test -- PotionGauge
```

Expected: 3 tests PASS.

- [ ] **Step 4: Implement RarityBorder**

Create `leaderboard/src/components/shared/RarityBorder.tsx`:

```tsx
import clsx from 'clsx'
import type { Ascension } from '@/types/submission'
import type { ReactNode } from 'react'

export interface RarityBorderProps {
  ceiling: Ascension
  children: ReactNode
  className?: string
}

const RARITY_LABEL: Record<Ascension, string> = {
  0: 'COMMON',
  1: 'UNCOMMON',
  2: 'RARE',
  3: 'ELITE',
  4: 'LEGENDARY',
  5: 'MYTHIC',
}

const RARITY_RING: Record<Ascension, string> = {
  0: 'ring-2 ring-[color:var(--color-rarity-common)]',
  1: 'ring-2 ring-[color:var(--color-rarity-uncommon)]',
  2: 'ring-2 ring-[color:var(--color-rarity-rare)]',
  3: 'ring-4 ring-[color:var(--color-rarity-elite)] shadow-[0_0_24px_color-mix(in_srgb,var(--color-rarity-elite)_60%,transparent)]',
  4: 'ring-4 ring-[color:var(--color-rarity-legendary-to)] shadow-[0_0_36px_color-mix(in_srgb,var(--color-rarity-legendary-from)_70%,transparent)]',
  5: 'ring-4 ring-fuchsia-400 shadow-[0_0_40px_rgba(168,85,247,0.8)] animate-pulse',
}

export function RarityBorder({ ceiling, children, className }: RarityBorderProps) {
  return (
    <div className={clsx('relative rounded-xl', RARITY_RING[ceiling], className)}>
      <div className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-[color:var(--color-bg-raised)] px-2 py-0.5 font-pixel text-[8px]">
        {RARITY_LABEL[ceiling]}
      </div>
      {children}
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add leaderboard/src/components/shared leaderboard/tests/components/PotionGauge.test.tsx
git commit -m "feat(leaderboard): add PotionGauge + RarityBorder primitives"
```

---

### Task 9: TradingCard component

**Files:**
- Create: `leaderboard/src/components/hero/TradingCard.tsx`
- Create: `leaderboard/tests/components/TradingCard.test.tsx`

- [ ] **Step 1: Write failing smoke test**

Create `leaderboard/tests/components/TradingCard.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TradingCard } from '@/components/hero/TradingCard'
import type { Submission } from '@/types/submission'

const fake: Submission = {
  id: 'test-sub',
  method: {
    name: 'HCM-Agent',
    version: 'v0.3',
    authors: ['Team'],
    description_short: 'Test.',
    relics: [],
  },
  model: { provider: 'google', name: 'Gemini 3.1 Pro', id: 'g' },
  character: 'Silent',
  runs: [{
    run_index: 1, ascension: 4, outcome: 'victory',
    final_floor: 50, final_act: 3, duration_seconds: 500, per_run_score: 450,
  }],
  aggregate: {
    ceiling: 4, ceiling_consistency: 0.33, progress_score_mean: 365,
    progress_score_max: 508, avg_final_floor: 35, max_final_floor: 50,
    total_runs: 1, total_victories: 1,
  },
  cost: {
    total_usd: 12.4, total_input_tokens: 1_800_000, total_output_tokens: 600_000,
    cost_per_run_usd: 1.24, cost_per_ascension_unlocked_usd: 3.1,
  },
  submitted_at: '2026-04-17T10:00:00Z',
  verified: true,
}

describe('TradingCard', () => {
  it('renders submission name and key stats', () => {
    render(<TradingCard submission={fake} medianCostUsd={20} />)
    expect(screen.getByText(/HCM-Agent/)).toBeInTheDocument()
    expect(screen.getByText(/Gemini 3.1 Pro/)).toBeInTheDocument()
    expect(screen.getByText(/A4/)).toBeInTheDocument()
    expect(screen.getByText(/\$12.40/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Implement TradingCard**

Create `leaderboard/src/components/hero/TradingCard.tsx`:

```tsx
import type { Submission } from '@/types/submission'
import { RarityBorder } from '@/components/shared/RarityBorder'
import { RunStrip } from '@/components/shared/RunStrip'
import { PotionGauge } from '@/components/shared/PotionGauge'
import { motion } from 'motion/react'

const PROVIDER_EMOJI: Record<Submission['model']['provider'], string> = {
  google: '💠',
  openai: '⚡',
  anthropic: '✶',
  qwen: '◈',
  other: '◉',
}

function flavorText(sub: Submission): string {
  const { ceiling, total_victories } = sub.aggregate
  if (ceiling === 5) return '"Peak of the Spire beckons."'
  if (ceiling === 4) return '"Conquered the Heart — almost."'
  if (ceiling === 3) return '"A steady climber."'
  if (ceiling === 2) return '"Knows the early floors."'
  if (ceiling === 1) return '"Breached the colosseum."'
  if (total_victories > 0) return '"Survived the tutorial."'
  return '"The Spire endures."'
}

function Stars({ ceiling }: { ceiling: number }) {
  const filled = ceiling
  return (
    <span className="font-mono text-sm tracking-wider">
      {'★'.repeat(filled)}{'☆'.repeat(5 - filled)}
    </span>
  )
}

export interface TradingCardProps {
  submission: Submission
  medianCostUsd: number
  delay?: number
}

export function TradingCard({ submission, medianCostUsd, delay = 0 }: TradingCardProps) {
  const { method, model, aggregate, cost } = submission

  return (
    <motion.div
      initial={{ opacity: 0, y: 40, rotateY: 30 }}
      animate={{ opacity: 1, y: 0, rotateY: 0 }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -8, rotateY: 4, rotateX: -2 }}
      style={{ perspective: 1000 }}
      className="w-[280px] shrink-0"
    >
      <RarityBorder ceiling={aggregate.ceiling} className="bg-[color:var(--color-bg-raised)] p-4">
        <div className="mt-3 flex h-44 items-center justify-center rounded-lg bg-gradient-to-br from-[color:var(--color-bg-base)] to-[color:var(--color-bg-raised)] text-6xl">
          {PROVIDER_EMOJI[model.provider]}
        </div>

        <div className="mt-3">
          <h3 className="font-display text-lg leading-tight">
            {method.name} <span className="text-[color:var(--color-ink-secondary)]">{method.version}</span>
          </h3>
          <p className="font-body text-sm text-[color:var(--color-ink-secondary)]">{model.name}</p>
        </div>

        <dl className="mt-3 space-y-1 text-sm">
          <div className="flex justify-between font-mono">
            <dt className="text-[color:var(--color-ink-secondary)]">CEILING</dt>
            <dd>A{aggregate.ceiling} <Stars ceiling={aggregate.ceiling} /></dd>
          </div>
          <div className="flex justify-between font-mono">
            <dt className="text-[color:var(--color-ink-secondary)]">SCORE</dt>
            <dd>{aggregate.progress_score_mean.toFixed(0)} / 600</dd>
          </div>
          <div className="flex justify-between font-mono">
            <dt className="text-[color:var(--color-ink-secondary)]">COST</dt>
            <dd>${cost.total_usd.toFixed(2)}</dd>
          </div>
          <div className="flex justify-between font-mono">
            <dt className="text-[color:var(--color-ink-secondary)]">$/A</dt>
            <dd>${cost.cost_per_ascension_unlocked_usd.toFixed(2)}</dd>
          </div>
        </dl>

        <div className="mt-3 flex justify-center">
          <PotionGauge costUsd={cost.total_usd} medianUsd={medianCostUsd} />
        </div>

        <div className="mt-3">
          <RunStrip runs={submission.runs} />
        </div>

        <p className="mt-3 italic font-body text-xs text-center text-[color:var(--color-ink-secondary)]">
          {flavorText(submission)}
        </p>
      </RarityBorder>
    </motion.div>
  )
}
```

- [ ] **Step 3: Run tests**

```bash
npm run test -- TradingCard
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add leaderboard/src/components/hero/TradingCard.tsx leaderboard/tests/components/TradingCard.test.tsx
git commit -m "feat(leaderboard): add TradingCard with rarity border, stats, potion gauge, run strip"
```

---

### Task 10: HeroSection (headline + card deck)

**Files:**
- Create: `leaderboard/src/components/hero/HeroHeadline.tsx`
- Create: `leaderboard/src/components/hero/HeroSection.tsx`

- [ ] **Step 1: Implement HeroHeadline with typing animation**

Create `leaderboard/src/components/hero/HeroHeadline.tsx`:

```tsx
import { motion } from 'motion/react'

const HEADLINE = 'Can an LLM climb the Spire?'
const SUBLINE = 'One can.'

export function HeroHeadline() {
  return (
    <div className="text-center">
      <h1 className="font-display text-5xl leading-tight md:text-7xl">
        {HEADLINE.split('').map((ch, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.05, delay: 0.02 * i }}
            className="inline-block"
          >
            {ch === ' ' ? '\u00A0' : ch}
          </motion.span>
        ))}
      </h1>
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8 }}
        className="font-body mt-4 text-xl text-[color:var(--color-accent-magenta)] md:text-2xl"
      >
        {SUBLINE}
      </motion.p>
    </div>
  )
}
```

- [ ] **Step 2: Implement HeroSection composing headline + top 3 cards**

Create `leaderboard/src/components/hero/HeroSection.tsx`:

```tsx
import type { Submission } from '@/types/submission'
import { TradingCard } from './TradingCard'
import { HeroHeadline } from './HeroHeadline'

export interface HeroSectionProps {
  submissions: Submission[]
}

function median(xs: number[]): number {
  if (xs.length === 0) return 1
  const s = [...xs].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 === 0 ? (s[mid - 1] + s[mid]) / 2 : s[mid]
}

function rankedTop3(subs: Submission[]): Submission[] {
  return [...subs]
    .sort((a, b) => {
      if (b.aggregate.ceiling !== a.aggregate.ceiling) return b.aggregate.ceiling - a.aggregate.ceiling
      return b.aggregate.progress_score_mean - a.aggregate.progress_score_mean
    })
    .slice(0, 3)
}

export function HeroSection({ submissions }: HeroSectionProps) {
  const top3 = rankedTop3(submissions)
  const medianCost = median(submissions.map((s) => s.cost.total_usd))

  return (
    <section className="px-6 pb-24 pt-16 md:pt-32">
      <HeroHeadline />
      <div className="mx-auto mt-16 flex max-w-6xl flex-wrap justify-center gap-8">
        {top3.map((s, i) => (
          <TradingCard key={s.id} submission={s} medianCostUsd={medianCost} delay={1.2 + i * 0.2} />
        ))}
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Update `App.tsx` to render HeroSection with fixture**

Replace `leaderboard/src/App.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { ThemeProvider } from '@/theme/ThemeProvider'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { HeroSection } from '@/components/hero/HeroSection'
import { loadSubmissions } from '@/data/loadSubmissions'
import type { SubmissionBundle } from '@/types/submission'

export default function App() {
  const [bundle, setBundle] = useState<SubmissionBundle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadSubmissions()
      .then(setBundle)
      .catch((e) => setError(String(e)))
  }, [])

  return (
    <ThemeProvider>
      <main className="min-h-screen bg-[color:var(--color-bg-base)] text-[color:var(--color-ink-primary)]">
        <header className="flex items-center justify-end px-6 py-4">
          <ThemeToggle />
        </header>
        {error && (
          <p className="p-8 text-center text-[color:var(--color-danger)]">Error: {error}</p>
        )}
        {bundle && <HeroSection submissions={bundle.submissions} />}
      </main>
    </ThemeProvider>
  )
}
```

- [ ] **Step 4: Manual verify in browser**

```bash
npm run dev
```

Open `http://localhost:5173`. Verify:
- Headline types out character by character
- Three trading cards deal onto screen with staggered entrance
- Top card has legendary rarity (A4), golden glow
- Stats visible on each card
- Hover a card → tilts slightly
- Toggle theme → colors invert but layout stays
- Stop with Ctrl+C

- [ ] **Step 5: Commit**

```bash
git add leaderboard/src/components/hero leaderboard/src/App.tsx
git commit -m "feat(leaderboard): add animated hero section with top-3 trading card deck"
```

---

### Task 11: Flag + SpireTier components

**Files:**
- Create: `leaderboard/src/components/spire/Flag.tsx`
- Create: `leaderboard/src/components/spire/SpireTier.tsx`

- [ ] **Step 1: Implement Flag**

Create `leaderboard/src/components/spire/Flag.tsx`:

```tsx
import clsx from 'clsx'
import type { Submission } from '@/types/submission'
import { motion } from 'motion/react'

const PROVIDER_EMOJI: Record<Submission['model']['provider'], string> = {
  google: '💠',
  openai: '⚡',
  anthropic: '✶',
  qwen: '◈',
  other: '◉',
}

const CEILING_GLOW: Record<number, string> = {
  0: 'shadow-[0_0_8px_rgba(176,168,158,0.5)]',
  1: 'shadow-[0_0_12px_rgba(95,168,211,0.6)]',
  2: 'shadow-[0_0_16px_rgba(155,89,182,0.6)]',
  3: 'shadow-[0_0_20px_rgba(230,126,34,0.7)]',
  4: 'shadow-[0_0_28px_rgba(244,196,48,0.8)]',
  5: 'shadow-[0_0_32px_rgba(236,72,153,0.9)]',
}

export interface FlagProps {
  submission: Submission
  delay?: number
}

export function Flag({ submission, delay = 0 }: FlagProps) {
  const { method, model, aggregate } = submission

  return (
    <motion.div
      initial={{ y: 120, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.9, delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -6, scale: 1.05 }}
      className="group relative flex flex-col items-center"
    >
      <div
        className={clsx(
          'flex h-12 w-12 items-center justify-center rounded-full border-2 border-[color:var(--color-accent-gold)] bg-[color:var(--color-bg-raised)] text-2xl',
          CEILING_GLOW[aggregate.ceiling],
        )}
      >
        {PROVIDER_EMOJI[model.provider]}
      </div>
      <div className="mt-1 max-w-[90px] truncate rounded bg-[color:var(--color-bg-raised)] px-2 py-0.5 font-pixel text-[7px] text-[color:var(--color-ink-primary)]">
        {method.name}
      </div>
      <div className="pointer-events-none absolute left-full top-0 ml-4 hidden w-56 rounded-lg border border-[color:var(--color-ink-secondary)] bg-[color:var(--color-bg-raised)] p-3 shadow-xl group-hover:block">
        <p className="font-display text-sm">{method.name} {method.version}</p>
        <p className="font-body text-xs text-[color:var(--color-ink-secondary)]">{model.name}</p>
        <p className="mt-2 font-mono text-xs">
          Ceiling A{aggregate.ceiling} · {(aggregate.ceiling_consistency * 100).toFixed(0)}% consistent
        </p>
        <p className="font-mono text-xs">Score {aggregate.progress_score_mean.toFixed(0)}</p>
      </div>
    </motion.div>
  )
}
```

- [ ] **Step 2: Implement SpireTier**

Create `leaderboard/src/components/spire/SpireTier.tsx`:

```tsx
import clsx from 'clsx'
import type { Ascension, Submission } from '@/types/submission'
import { Flag } from './Flag'

export interface SpireTierProps {
  ascension: Ascension
  label: string
  submissions: Submission[]   // submissions whose ceiling === this tier's ascension
  isPeak?: boolean            // A5 — always fog-covered in v1
  flagStartDelay?: number
}

const TIER_BG: Record<Ascension, string> = {
  0: 'from-stone-200/40 to-stone-100/20',
  1: 'from-sky-300/30 to-sky-100/10',
  2: 'from-purple-400/30 to-purple-200/10',
  3: 'from-orange-400/30 to-orange-200/10',
  4: 'from-red-500/40 via-amber-400/30 to-amber-200/10',
  5: 'from-fuchsia-500/30 via-yellow-400/20 to-cyan-300/10',
}

export function SpireTier({
  ascension,
  label,
  submissions,
  isPeak = false,
  flagStartDelay = 0,
}: SpireTierProps) {
  return (
    <div className="relative flex min-h-[108px] items-center gap-4 border-b border-[color:var(--color-accent-gold)]/30">
      <div className="w-28 shrink-0 py-4 pr-2 text-right">
        <div className="font-pixel text-[9px] text-[color:var(--color-accent-gold)]">A{ascension}</div>
        <div className="font-display text-sm leading-tight">{label}</div>
      </div>

      <div className={clsx('relative flex flex-1 flex-wrap items-center gap-3 rounded-r-lg bg-gradient-to-r px-6 py-4', TIER_BG[ascension])}>
        {isPeak && (
          <div className="absolute inset-0 flex items-center justify-center rounded-r-lg bg-[color:var(--color-bg-base)]/70 backdrop-blur-sm">
            <span className="font-display text-xl tracking-widest text-[color:var(--color-ink-secondary)]">??? The Peak ???</span>
          </div>
        )}
        {!isPeak && submissions.length === 0 && (
          <span className="font-body text-sm italic text-[color:var(--color-ink-secondary)]">— no climbers yet —</span>
        )}
        {!isPeak && submissions.map((s, i) => (
          <Flag key={s.id} submission={s} delay={flagStartDelay + i * 0.12} />
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add leaderboard/src/components/spire/Flag.tsx leaderboard/src/components/spire/SpireTier.tsx
git commit -m "feat(leaderboard): add Flag + SpireTier for climbing visualization"
```

---

### Task 12: TheSpire component

**Files:**
- Create: `leaderboard/src/components/spire/TheSpire.tsx`
- Modify: `leaderboard/src/App.tsx`

- [ ] **Step 1: Implement TheSpire**

Create `leaderboard/src/components/spire/TheSpire.tsx`:

```tsx
import type { Ascension, Submission } from '@/types/submission'
import { SpireTier } from './SpireTier'

const TIERS: { a: Ascension; label: string; isPeak?: boolean }[] = [
  { a: 5, label: 'THE PEAK',         isPeak: true },
  { a: 4, label: 'HEART OF THE SPIRE' },
  { a: 3, label: 'CHAMPION\'S GATE' },
  { a: 2, label: 'COLOSSEUM' },
  { a: 1, label: 'FIRST ELITE' },
  { a: 0, label: 'EXORDIUM' },
]

export interface TheSpireProps {
  submissions: Submission[]
}

export function TheSpire({ submissions }: TheSpireProps) {
  const byCeiling = new Map<Ascension, Submission[]>()
  for (const tier of TIERS) byCeiling.set(tier.a, [])
  for (const s of submissions) {
    const list = byCeiling.get(s.aggregate.ceiling)
    if (list) list.push(s)
  }

  return (
    <section className="px-6 py-24">
      <h2 className="mb-12 text-center font-display text-4xl md:text-5xl">The Spire</h2>
      <p className="mx-auto mb-12 max-w-2xl text-center font-body text-[color:var(--color-ink-secondary)]">
        Each submission plants its flag at the highest ascension it has conquered.
        The peak awaits its first climber.
      </p>

      <div className="mx-auto max-w-5xl overflow-hidden rounded-xl border border-[color:var(--color-accent-gold)]/40 bg-[color:var(--color-bg-raised)]">
        {TIERS.map((tier, i) => (
          <SpireTier
            key={tier.a}
            ascension={tier.a}
            label={tier.label}
            isPeak={tier.isPeak}
            submissions={byCeiling.get(tier.a) ?? []}
            flagStartDelay={0.2 + i * 0.15}
          />
        ))}
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Wire TheSpire into App.tsx**

Replace the body of `leaderboard/src/App.tsx` to add the Spire below the hero:

```tsx
import { useEffect, useState } from 'react'
import { ThemeProvider } from '@/theme/ThemeProvider'
import { ThemeToggle } from '@/components/shared/ThemeToggle'
import { HeroSection } from '@/components/hero/HeroSection'
import { TheSpire } from '@/components/spire/TheSpire'
import { loadSubmissions } from '@/data/loadSubmissions'
import type { SubmissionBundle } from '@/types/submission'

export default function App() {
  const [bundle, setBundle] = useState<SubmissionBundle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadSubmissions().then(setBundle).catch((e) => setError(String(e)))
  }, [])

  return (
    <ThemeProvider>
      <main className="min-h-screen bg-[color:var(--color-bg-base)] text-[color:var(--color-ink-primary)]">
        <header className="flex items-center justify-end px-6 py-4">
          <ThemeToggle />
        </header>
        {error && <p className="p-8 text-center text-[color:var(--color-danger)]">Error: {error}</p>}
        {bundle && (
          <>
            <HeroSection submissions={bundle.submissions} />
            <TheSpire submissions={bundle.submissions} />
          </>
        )}
      </main>
    </ThemeProvider>
  )
}
```

- [ ] **Step 3: Manual verify**

```bash
npm run dev
```

Verify:
- Scroll past hero → see "The Spire" section
- Six horizontal tiers from A5 (peak, fog-covered) at top down to A0 at bottom
- Flags appear at their correct ceiling tier with a climbing entrance animation
- Hovering a flag shows a detail tooltip
- Ctrl+C to stop

- [ ] **Step 4: Commit**

```bash
git add leaderboard/src/components/spire/TheSpire.tsx leaderboard/src/App.tsx
git commit -m "feat(leaderboard): add The Spire signature visualization with 6 ascension tiers"
```

---

### Task 13: LeaderboardTable + LeaderboardTabs + LeaderboardSection

**Files:**
- Create: `leaderboard/src/components/leaderboard/LeaderboardTable.tsx`
- Create: `leaderboard/src/components/leaderboard/LeaderboardTabs.tsx`
- Create: `leaderboard/src/components/leaderboard/LeaderboardSection.tsx`

- [ ] **Step 1: Implement LeaderboardTable**

Create `leaderboard/src/components/leaderboard/LeaderboardTable.tsx`:

```tsx
import type { Submission } from '@/types/submission'
import { RunStrip } from '@/components/shared/RunStrip'
import clsx from 'clsx'

const PROVIDER_EMOJI: Record<Submission['model']['provider'], string> = {
  google: '💠', openai: '⚡', anthropic: '✶', qwen: '◈', other: '◉',
}

export interface LeaderboardTableProps {
  submissions: Submission[]
}

function rankMedal(rank: number): string {
  if (rank === 1) return '🏆'
  if (rank === 2) return '🥈'
  if (rank === 3) return '🥉'
  return String(rank)
}

export function LeaderboardTable({ submissions }: LeaderboardTableProps) {
  const ranked = [...submissions].sort((a, b) => {
    if (b.aggregate.ceiling !== a.aggregate.ceiling) return b.aggregate.ceiling - a.aggregate.ceiling
    return b.aggregate.progress_score_mean - a.aggregate.progress_score_mean
  })

  return (
    <div className="overflow-x-auto rounded-lg border border-[color:var(--color-ink-secondary)]/20">
      <table className="w-full min-w-[960px] text-left">
        <thead className="bg-[color:var(--color-bg-raised)] font-pixel text-[9px] uppercase tracking-wider">
          <tr>
            <th className="px-4 py-3">Rank</th>
            <th className="px-4 py-3">Submission</th>
            <th className="px-4 py-3">Model</th>
            <th className="px-4 py-3">Char</th>
            <th className="px-4 py-3">Ceiling</th>
            <th className="px-4 py-3">Score</th>
            <th className="px-4 py-3">Cost</th>
            <th className="px-4 py-3">Runs (10)</th>
          </tr>
        </thead>
        <tbody className="font-mono text-sm">
          {ranked.map((s, i) => (
            <tr
              key={s.id}
              className={clsx(
                'border-t border-[color:var(--color-ink-secondary)]/10 transition',
                'hover:bg-[color:var(--color-bg-raised)]',
              )}
            >
              <td className="px-4 py-3 text-2xl">{rankMedal(i + 1)}</td>
              <td className="px-4 py-3">
                <div className="font-display text-base leading-tight">
                  {s.method.name} {s.method.version}
                </div>
                <div className="text-xs text-[color:var(--color-ink-secondary)]">
                  by {s.method.authors.join(', ')}
                </div>
              </td>
              <td className="px-4 py-3">
                <span className="mr-2">{PROVIDER_EMOJI[s.model.provider]}</span>
                {s.model.name}
              </td>
              <td className="px-4 py-3">{s.character}</td>
              <td className="px-4 py-3">
                <div className="font-pixel text-xs text-[color:var(--color-accent-gold)]">A{s.aggregate.ceiling}</div>
                <div className="text-xs text-[color:var(--color-ink-secondary)]">
                  {s.aggregate.total_victories}/{s.aggregate.total_runs} ✓
                </div>
              </td>
              <td className="px-4 py-3">{s.aggregate.progress_score_mean.toFixed(0)}</td>
              <td className="px-4 py-3">
                <div>${s.cost.total_usd.toFixed(2)}</div>
                <div className="text-xs text-[color:var(--color-ink-secondary)]">
                  ${s.cost.cost_per_ascension_unlocked_usd.toFixed(2)}/A
                </div>
              </td>
              <td className="px-4 py-3">
                <RunStrip runs={s.runs} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Implement LeaderboardTabs**

Create `leaderboard/src/components/leaderboard/LeaderboardTabs.tsx`:

```tsx
import clsx from 'clsx'

export type LeaderboardTab = 'methods' | 'models' | 'characters'

export interface LeaderboardTabsProps {
  active: LeaderboardTab
  onChange: (tab: LeaderboardTab) => void
}

const TABS: { id: LeaderboardTab; label: string; disabled?: string }[] = [
  { id: 'methods', label: 'Methods' },
  { id: 'models', label: 'Models' },
  { id: 'characters', label: 'Characters', disabled: 'Coming soon — only Silent is playable.' },
]

export function LeaderboardTabs({ active, onChange }: LeaderboardTabsProps) {
  return (
    <div className="flex gap-2 border-b border-[color:var(--color-ink-secondary)]/30">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          disabled={!!tab.disabled}
          title={tab.disabled}
          onClick={() => !tab.disabled && onChange(tab.id)}
          className={clsx(
            'relative px-5 py-3 font-display text-lg transition',
            active === tab.id
              ? 'text-[color:var(--color-accent-gold)]'
              : 'text-[color:var(--color-ink-secondary)] hover:text-[color:var(--color-ink-primary)]',
            tab.disabled && 'cursor-not-allowed opacity-40',
          )}
        >
          {tab.label}
          {active === tab.id && (
            <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[color:var(--color-accent-gold)]" />
          )}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Implement LeaderboardSection with tab-based filtering**

Create `leaderboard/src/components/leaderboard/LeaderboardSection.tsx`:

```tsx
import { useMemo, useState } from 'react'
import type { Submission } from '@/types/submission'
import { LeaderboardTable } from './LeaderboardTable'
import { LeaderboardTabs, type LeaderboardTab } from './LeaderboardTabs'

export interface LeaderboardSectionProps {
  submissions: Submission[]
}

const OUR_METHOD_NAME = 'HCM-Agent'

function filterForTab(subs: Submission[], tab: LeaderboardTab): Submission[] {
  if (tab === 'models') {
    // Models view: fix method = ours, compare LLMs
    return subs.filter((s) => s.method.name === OUR_METHOD_NAME)
  }
  // Methods view (default): everyone
  // Characters view: disabled in MVP, never reaches here
  return subs
}

export function LeaderboardSection({ submissions }: LeaderboardSectionProps) {
  const [tab, setTab] = useState<LeaderboardTab>('methods')
  const filtered = useMemo(() => filterForTab(submissions, tab), [submissions, tab])

  const helpText =
    tab === 'methods' ? 'Every method × model × character submission, sorted by ceiling.' :
    tab === 'models'  ? `Head-to-head comparison of LLMs running the ${OUR_METHOD_NAME} pipeline.` :
                        ''

  return (
    <section className="px-6 py-24">
      <h2 className="mb-8 text-center font-display text-4xl md:text-5xl">Leaderboard</h2>
      <div className="mx-auto max-w-6xl">
        <LeaderboardTabs active={tab} onChange={setTab} />
        <p className="mt-4 font-body text-sm text-[color:var(--color-ink-secondary)]">{helpText}</p>
        <div className="mt-6">
          <LeaderboardTable submissions={filtered} />
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Wire into App.tsx**

Modify `leaderboard/src/App.tsx` — add the import and the section below `TheSpire`:

```tsx
// Add to imports:
import { LeaderboardSection } from '@/components/leaderboard/LeaderboardSection'

// In JSX, below <TheSpire submissions={bundle.submissions} />:
<LeaderboardSection submissions={bundle.submissions} />
```

- [ ] **Step 5: Manual verify**

```bash
npm run dev
```

Verify:
- Scroll past hero + spire → see "Leaderboard" with Methods/Models/Characters tabs
- Characters tab is greyed-out with tooltip "Coming soon"
- Table shows all 6 submissions sorted by ceiling desc
- Each row has a run-strip of 10 pills
- Hover row → row highlights
- Ctrl+C

- [ ] **Step 6: Commit**

```bash
git add leaderboard/src/components/leaderboard leaderboard/src/App.tsx
git commit -m "feat(leaderboard): add sortable leaderboard table with tabs"
```

---

### Task 14: CeilingCostScatter

**Files:**
- Create: `leaderboard/src/components/scatter/CeilingCostScatter.tsx`
- Modify: `leaderboard/src/App.tsx`

- [ ] **Step 1: Implement scatter using Recharts**

Create `leaderboard/src/components/scatter/CeilingCostScatter.tsx`:

```tsx
import type { Submission } from '@/types/submission'
import {
  CartesianGrid, Legend, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'

const PROVIDER_COLOR: Record<Submission['model']['provider'], string> = {
  google: '#8ab4f8',
  openai: '#10a37f',
  anthropic: '#d97757',
  qwen: '#e91e63',
  other: '#9b8aa3',
}

interface Point {
  id: string
  name: string
  model: string
  x: number   // $/A
  y: number   // mean progress score
  z: number   // total runs
  provider: Submission['model']['provider']
}

function toPoints(subs: Submission[]): Point[] {
  return subs.map((s) => ({
    id: s.id,
    name: `${s.method.name} ${s.method.version}`,
    model: s.model.name,
    x: Math.max(s.cost.cost_per_ascension_unlocked_usd, 0.01),   // guard log(0)
    y: s.aggregate.progress_score_mean,
    z: s.aggregate.total_runs,
    provider: s.model.provider,
  }))
}

function groupByProvider(points: Point[]): Record<Point['provider'], Point[]> {
  const out: Record<Point['provider'], Point[]> = { google: [], openai: [], anthropic: [], qwen: [], other: [] }
  for (const p of points) out[p.provider].push(p)
  return out
}

export interface CeilingCostScatterProps {
  submissions: Submission[]
}

export function CeilingCostScatter({ submissions }: CeilingCostScatterProps) {
  const points = toPoints(submissions)
  const groups = groupByProvider(points)

  return (
    <section className="px-6 py-24">
      <h2 className="mb-4 text-center font-display text-4xl md:text-5xl">Score vs Cost</h2>
      <p className="mx-auto mb-10 max-w-2xl text-center font-body text-[color:var(--color-ink-secondary)]">
        Top-left quadrant = &ldquo;SOTA Zone.&rdquo; High climb, low cost per ascension unlocked.
      </p>

      <div className="mx-auto max-w-5xl">
        <ResponsiveContainer width="100%" height={420}>
          <ScatterChart margin={{ top: 20, right: 40, bottom: 60, left: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.15} />
            <XAxis
              dataKey="x"
              type="number"
              scale="log"
              domain={[0.1, 1000]}
              ticks={[0.1, 1, 10, 100, 1000]}
              name="$ / Ascension Unlocked"
              label={{ value: '$ / Ascension (log)', position: 'insideBottom', offset: -40 }}
              stroke="currentColor"
            />
            <YAxis
              dataKey="y"
              type="number"
              domain={[0, 600]}
              name="Progress Score (mean)"
              label={{ value: 'Progress Score (mean)', angle: -90, position: 'insideLeft', offset: -10 }}
              stroke="currentColor"
            />
            <ZAxis dataKey="z" range={[60, 180]} />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              content={({ active, payload }) => {
                if (!active || !payload?.[0]) return null
                const p = payload[0].payload as Point
                return (
                  <div className="rounded border border-[color:var(--color-ink-secondary)] bg-[color:var(--color-bg-raised)] p-3 font-mono text-xs shadow-xl">
                    <div className="font-display text-sm">{p.name}</div>
                    <div className="text-[color:var(--color-ink-secondary)]">{p.model}</div>
                    <div className="mt-1">Score: {p.y.toFixed(0)}</div>
                    <div>$/A: ${p.x.toFixed(2)}</div>
                  </div>
                )
              }}
            />
            <Legend />
            {(Object.keys(groups) as Point['provider'][]).map((prov) => (
              groups[prov].length > 0 && (
                <Scatter
                  key={prov}
                  name={prov}
                  data={groups[prov]}
                  fill={PROVIDER_COLOR[prov]}
                  fillOpacity={0.85}
                />
              )
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Wire into App.tsx**

Add import to `App.tsx`:

```tsx
import { CeilingCostScatter } from '@/components/scatter/CeilingCostScatter'
```

Add `<CeilingCostScatter submissions={bundle.submissions} />` between `<TheSpire>` and `<LeaderboardSection>`.

- [ ] **Step 3: Manual verify**

```bash
npm run dev
```

Verify:
- Section appears between Spire and Leaderboard
- 6 dots appear, colored by provider
- Log-scale X-axis with ticks at 0.1, 1, 10, 100, 1000
- Hover a dot → tooltip shows method, model, score, $/A
- Our HCM-Agent+Gemini dot should be upper-left (high score, low cost)
- Ctrl+C

- [ ] **Step 4: Commit**

```bash
git add leaderboard/src/components/scatter leaderboard/src/App.tsx
git commit -m "feat(leaderboard): add Progress Score vs Cost scatter with log X-axis"
```

---

### Task 15: Nav + Footer + final Home assembly

**Files:**
- Create: `leaderboard/src/components/shared/Nav.tsx`
- Create: `leaderboard/src/components/shared/Footer.tsx`
- Create: `leaderboard/src/routes/Home.tsx`
- Modify: `leaderboard/src/App.tsx`

- [ ] **Step 1: Implement Nav**

Create `leaderboard/src/components/shared/Nav.tsx`:

```tsx
import { ThemeToggle } from './ThemeToggle'

export function Nav() {
  return (
    <nav className="sticky top-0 z-50 border-b border-[color:var(--color-ink-secondary)]/20 bg-[color:var(--color-bg-base)]/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <a href="/" className="font-display text-xl">
          <span className="text-[color:var(--color-accent-gold)]">✦</span> STS2 Agent Leaderboard
        </a>
        <div className="flex items-center gap-6">
          <a href="#spire" className="font-body text-sm hover:text-[color:var(--color-accent-gold)]">The Spire</a>
          <a href="#leaderboard" className="font-body text-sm hover:text-[color:var(--color-accent-gold)]">Leaderboard</a>
          <a href="#about" className="font-body text-sm hover:text-[color:var(--color-accent-gold)]">About</a>
          <ThemeToggle />
        </div>
      </div>
    </nav>
  )
}
```

- [ ] **Step 2: Implement Footer**

Create `leaderboard/src/components/shared/Footer.tsx`:

```tsx
export function Footer() {
  return (
    <footer id="about" className="border-t border-[color:var(--color-ink-secondary)]/20 bg-[color:var(--color-bg-raised)] px-6 py-16">
      <div className="mx-auto max-w-5xl">
        <h3 className="font-display text-2xl">About This Benchmark</h3>
        <p className="mt-4 max-w-2xl font-body text-[color:var(--color-ink-secondary)]">
          Slay the Spire 2 is a roguelike deckbuilder. Each submission attempts to climb the
          Spire across 10 runs in <em>auto-ascension</em> mode — starting at Ascension 0,
          unlocking harder tiers only by beating the final boss. The highest tier an agent
          reliably clears is its <strong>ceiling</strong>.
        </p>

        <h3 className="mt-10 font-display text-2xl">Scoring</h3>
        <pre className="mt-3 inline-block rounded bg-[color:var(--color-bg-base)] px-4 py-3 font-mono text-sm">
{`per_run_score = ascension × 100 + (50 if victory else final_floor)`}
        </pre>
        <p className="mt-3 font-body text-sm text-[color:var(--color-ink-secondary)]">
          Aborts are excluded. Ties broken by mean score, then cost per ascension unlocked.
        </p>

        <div className="mt-12 flex flex-wrap justify-between gap-4 border-t border-[color:var(--color-ink-secondary)]/20 pt-8 font-body text-xs text-[color:var(--color-ink-secondary)]">
          <span>Built with 🔥 on React + Vite + Tailwind.</span>
          <span>Data updated via static bundle. See repo for submission protocol.</span>
        </div>
      </div>
    </footer>
  )
}
```

- [ ] **Step 3: Create Home route**

Create `leaderboard/src/routes/Home.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { HeroSection } from '@/components/hero/HeroSection'
import { TheSpire } from '@/components/spire/TheSpire'
import { CeilingCostScatter } from '@/components/scatter/CeilingCostScatter'
import { LeaderboardSection } from '@/components/leaderboard/LeaderboardSection'
import { loadSubmissions } from '@/data/loadSubmissions'
import type { SubmissionBundle } from '@/types/submission'

export function Home() {
  const [bundle, setBundle] = useState<SubmissionBundle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadSubmissions().then(setBundle).catch((e) => setError(String(e)))
  }, [])

  if (error) {
    return <p className="p-16 text-center text-[color:var(--color-danger)]">Error: {error}</p>
  }
  if (!bundle) {
    return <p className="p-16 text-center font-body">Loading the Spire…</p>
  }

  return (
    <>
      <HeroSection submissions={bundle.submissions} />
      <div id="spire"><TheSpire submissions={bundle.submissions} /></div>
      <CeilingCostScatter submissions={bundle.submissions} />
      <div id="leaderboard"><LeaderboardSection submissions={bundle.submissions} /></div>
    </>
  )
}
```

- [ ] **Step 4: Replace App.tsx with final layout**

Replace `leaderboard/src/App.tsx`:

```tsx
import { ThemeProvider } from '@/theme/ThemeProvider'
import { Nav } from '@/components/shared/Nav'
import { Footer } from '@/components/shared/Footer'
import { Home } from '@/routes/Home'

export default function App() {
  return (
    <ThemeProvider>
      <div className="min-h-screen bg-[color:var(--color-bg-base)] text-[color:var(--color-ink-primary)]">
        <Nav />
        <main>
          <Home />
        </main>
        <Footer />
      </div>
    </ThemeProvider>
  )
}
```

- [ ] **Step 5: Manual verify**

```bash
npm run dev
```

Walk through:
- Sticky nav stays at top while scrolling
- Nav link "The Spire" jumps to Spire section
- Nav link "Leaderboard" jumps to table
- Footer appears at bottom with scoring formula
- Theme toggle in nav works
- Stop with Ctrl+C

- [ ] **Step 6: Commit**

```bash
git add leaderboard/src
git commit -m "feat(leaderboard): add nav, footer, and route-based home assembly"
```

---

### Task 16: Responsive + reduced-motion polish

**Files:**
- Create: `leaderboard/src/hooks/useReducedMotion.ts`
- Modify: `leaderboard/src/components/hero/HeroHeadline.tsx`
- Modify: `leaderboard/src/components/hero/HeroSection.tsx`
- Modify: `leaderboard/src/components/spire/Flag.tsx`
- Modify: `leaderboard/src/components/hero/TradingCard.tsx`

- [ ] **Step 1: Implement useReducedMotion hook**

Create `leaderboard/src/hooks/useReducedMotion.ts`:

```ts
import { useEffect, useState } from 'react'

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  })

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return reduced
}
```

- [ ] **Step 2: Gate HeroHeadline typing animation**

Modify `leaderboard/src/components/hero/HeroHeadline.tsx` — replace the component:

```tsx
import { motion } from 'motion/react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

const HEADLINE = 'Can an LLM climb the Spire?'
const SUBLINE = 'One can.'

export function HeroHeadline() {
  const reduced = useReducedMotion()

  return (
    <div className="text-center">
      <h1 className="font-display text-5xl leading-tight md:text-7xl">
        {reduced ? (
          HEADLINE
        ) : (
          HEADLINE.split('').map((ch, i) => (
            <motion.span
              key={i}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.05, delay: 0.02 * i }}
              className="inline-block"
            >
              {ch === ' ' ? '\u00A0' : ch}
            </motion.span>
          ))
        )}
      </h1>
      <motion.p
        initial={reduced ? false : { opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduced ? 0 : 0.6, delay: reduced ? 0 : 0.8 }}
        className="font-body mt-4 text-xl text-[color:var(--color-accent-magenta)] md:text-2xl"
      >
        {SUBLINE}
      </motion.p>
    </div>
  )
}
```

- [ ] **Step 3: Gate TradingCard + Flag animations**

Modify `leaderboard/src/components/hero/TradingCard.tsx` — at the top add:

```tsx
import { useReducedMotion } from '@/hooks/useReducedMotion'
```

Replace the `<motion.div>` block in the component body with:

```tsx
export function TradingCard({ submission, medianCostUsd, delay = 0 }: TradingCardProps) {
  const { method, model, aggregate, cost } = submission
  const reduced = useReducedMotion()

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 40, rotateY: 30 }}
      animate={{ opacity: 1, y: 0, rotateY: 0 }}
      transition={{ duration: reduced ? 0 : 0.6, delay: reduced ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={reduced ? undefined : { y: -8, rotateY: 4, rotateX: -2 }}
      style={{ perspective: 1000 }}
      className="w-[280px] shrink-0"
    >
      {/* rest of card body unchanged */}
```

Similarly modify `leaderboard/src/components/spire/Flag.tsx`:

```tsx
import { useReducedMotion } from '@/hooks/useReducedMotion'

export function Flag({ submission, delay = 0 }: FlagProps) {
  const { method, model, aggregate } = submission
  const reduced = useReducedMotion()

  return (
    <motion.div
      initial={reduced ? false : { y: 120, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: reduced ? 0 : 0.9, delay: reduced ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={reduced ? undefined : { y: -6, scale: 1.05 }}
      className="group relative flex flex-col items-center"
    >
      {/* rest unchanged */}
```

- [ ] **Step 4: Responsive sanity check**

Open DevTools at mobile viewport (375×667). In the browser with `npm run dev`:

Verify:
- Trading cards stack vertically on <768px (they already use flex-wrap)
- Nav collapses cleanly (links should still fit; if not, acceptable for MVP to let them scroll horizontally)
- Spire tiers remain readable (labels shrink via `text-sm`)
- Table has `overflow-x-auto` so can scroll horizontally
- No text overlap, no cut-off cards

If any break, add explicit Tailwind `md:` and `sm:` prefixes to the affected component. Most of the existing code already uses responsive utilities.

- [ ] **Step 5: Test reduced motion**

In Chrome DevTools: Command Menu (Ctrl+Shift+P) → "Show Rendering" → "Emulate CSS media feature prefers-reduced-motion" → reduce.

Reload page. Verify: no typing animation, no card deal animation, no flag climb animation — everything appears instantly. Unset the emulation.

- [ ] **Step 6: Commit**

```bash
git add leaderboard/src
git commit -m "feat(leaderboard): respect prefers-reduced-motion + verify responsive layout"
```

---

### Task 17: Build & deploy configuration

**Files:**
- Create: `leaderboard/public/favicon.svg`
- Modify: `leaderboard/README.md`
- Create: `leaderboard/vercel.json` OR `leaderboard/.cloudflare-pages.toml` (pick one)

- [ ] **Step 1: Create favicon**

Create `leaderboard/public/favicon.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <defs>
    <linearGradient id="g" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#7c3aed"/>
      <stop offset="100%" stop-color="#f4c430"/>
    </linearGradient>
  </defs>
  <rect width="32" height="32" fill="#0d0818" rx="4"/>
  <path d="M 16 4 L 22 28 L 10 28 Z" fill="url(#g)"/>
  <circle cx="16" cy="10" r="2" fill="#f4c430"/>
</svg>
```

- [ ] **Step 2: Run production build**

```bash
cd AgenticSTS/leaderboard
npm run build
```

Expected: compiles with no TS errors, outputs `dist/`. Note the bundle sizes printed — main chunk should be under ~300KB gzipped.

- [ ] **Step 3: Test production build locally**

```bash
npm run preview
```

Open printed URL. Walk through the entire site. Verify same behavior as dev mode. Ctrl+C.

- [ ] **Step 4: Create Vercel config (if using Vercel)**

Create `leaderboard/vercel.json`:

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "installCommand": "npm install"
}
```

*Alternatively* for Cloudflare Pages, this file is unnecessary — configure via the Pages dashboard:
- Build command: `npm run build`
- Build output directory: `dist`
- Root directory: `leaderboard`

- [ ] **Step 5: Update README with deploy instructions**

Replace `leaderboard/README.md`:

```markdown
# STS2 Agent Leaderboard

Public-facing leaderboard for LLM agents playing Slay the Spire 2.
Companion site to the AgenticSTS project.

## Local development

```bash
npm install
npm run dev        # dev server on http://localhost:5173
npm run test       # run vitest
npm run typecheck  # type-only compile check
npm run build      # production build -> dist/
npm run preview    # preview production build locally
```

## Data

Submissions are loaded at runtime from `public/data/submissions.json`.
The fixture shipped with this repo is mock data — real pipeline from
`../data/runs/history.jsonl` is v0.2 work.

Schema is enforced by `src/data/schemas.ts` (Zod).

## Architecture

- React 19 + Vite + TypeScript + Tailwind v4
- Motion library for React animations
- Recharts for the cost/score scatter plot
- Zod for runtime JSON validation
- No backend; 100% static deploy

## Deploy

### Vercel
Configured via `vercel.json`. Push to main → auto-deploy.

### Cloudflare Pages
Configure in dashboard:
- Build command: `npm run build`
- Output directory: `dist`
- Root directory: `leaderboard`

See `../docs/2026-04-17-leaderboard-design.md` for the full design spec.
See `../docs/superpowers/plans/2026-04-17-leaderboard-mvp.md` for the
implementation plan.
```

- [ ] **Step 6: Ensure .gitignore covers dist/**

Already covered in `leaderboard/.gitignore` from Task 1.

- [ ] **Step 7: Final verification — whole site walkthrough**

```bash
npm run dev
```

Complete walkthrough (document in a brief mental or written note):
- ✅ Nav sticky, anchor links work
- ✅ Headline types out
- ✅ Top 3 cards deal with stagger; each has rarity border, stats, potion gauge, run strip, flavor text
- ✅ Hover a card → tilts
- ✅ Theme toggle → flips palette
- ✅ Spire: 6 tiers, A5 fog-covered, flags at correct tiers, animated climb
- ✅ Hover flag → tooltip appears
- ✅ Scatter: 6 dots, log X-axis, hover shows detail
- ✅ Leaderboard table: sorted by ceiling, tabs (Characters disabled with tooltip), run strips per row
- ✅ Footer: scoring formula readable
- ✅ Ctrl+C

Run `npm run typecheck` and `npm run test` — both must be clean before commit.

- [ ] **Step 8: Final commit**

```bash
cd AgenticSTS
git add leaderboard/
git commit -m "feat(leaderboard): add favicon, deploy config, final README — MVP complete"
```

- [ ] **Step 9: Push to remote**

```bash
git push origin HEAD
```

---

## Final Self-Review Checklist

Before declaring MVP done:

- [ ] `npm run typecheck` — clean
- [ ] `npm run test` — all tests pass
- [ ] `npm run build` — succeeds, bundle under 500KB gzipped excluding fonts
- [ ] Manual desktop walkthrough (all 17 tasks' manual verify steps) — passes
- [ ] Manual mobile walkthrough (Chrome DevTools iPhone viewport) — usable
- [ ] Lighthouse (desktop): Performance > 85, Accessibility > 90
- [ ] Theme persists across reload
- [ ] Reduced motion respected
- [ ] Content matches spec sections 1, 4, 6 (narrative, scoring, components)
- [ ] No `console.log` left in code (search: `grep -rn "console\.log" leaderboard/src`)
- [ ] `README.md` has clear local-dev and deploy instructions

## Out-of-Scope Reminder

These are **intentionally deferred** to later phases:

- Python `build_leaderboard.py` pipeline reading real `data/runs/history.jsonl` + `logs/run_*.jsonl` (v0.2)
- Submission detail pages `/submission/:id` (v0.3)
- STS Map View trajectory chart (v0.3)
- Ablation tab (v0.3+)
- Multi-character support (pending multi-character codebase)
- Real model portraits (AI-generate in v0.2)
- Real spire tier illustrations (AI-generate in v0.2)
- Real relic icons (design/AI-generate in v0.2)

If any work above bleeds into this MVP, stop and escalate.
