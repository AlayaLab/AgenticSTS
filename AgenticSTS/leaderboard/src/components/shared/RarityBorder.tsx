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
