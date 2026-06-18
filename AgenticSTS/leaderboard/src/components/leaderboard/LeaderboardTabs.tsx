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
