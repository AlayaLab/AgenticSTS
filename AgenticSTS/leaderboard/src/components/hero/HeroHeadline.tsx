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
