# STS2 Agent Leaderboard

Public-facing leaderboard for LLM agents playing Slay the Spire 2.
Companion site to the AgenticSTS project.

## Local development

```bash
npm install
npm run dev        # dev server on http://localhost:5273 (5173 is reserved for agent monitor)
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
