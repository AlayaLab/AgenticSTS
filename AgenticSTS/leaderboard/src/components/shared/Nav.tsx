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
