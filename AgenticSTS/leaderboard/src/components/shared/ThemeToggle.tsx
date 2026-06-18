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
