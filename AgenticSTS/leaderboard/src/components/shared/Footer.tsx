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
