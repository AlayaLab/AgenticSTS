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
