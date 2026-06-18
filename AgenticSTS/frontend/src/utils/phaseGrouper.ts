import type {
  MonitorEvent,
  PhaseEncounter,
  PhaseEncounterKind,
  StateData,
  TransitionData,
  DecisionData,
} from '../types/events'

// Sub-states that can appear inside a phase encounter without ending it.
// e.g. picking a card during a card_reward, or selecting a card to remove
// during a shop/event.
const SUB_STATES = new Set<string>(['card_select', 'hand_select'])

const PHASE_TO_KIND: Record<string, PhaseEncounterKind> = {
  event: 'event',
  shop: 'shop',
  card_reward: 'card_reward',
  rest_site: 'rest',
}

interface GroupConfig {
  primaryStates: Set<string>
}

const VIEW_CONFIGS: Record<string, GroupConfig> = {
  event: { primaryStates: new Set(['event']) },
  shop_reward: { primaryStates: new Set(['shop', 'card_reward']) },
  rest: { primaryStates: new Set(['rest_site']) },
}

export function getPhaseConfig(view: string): GroupConfig | null {
  return VIEW_CONFIGS[view] ?? null
}

/**
 * Groups events into phase encounters (event / shop / reward / rest).
 *
 * An encounter starts when state_type enters one of the primary states and
 * ends when it transitions to a state that is neither primary nor a sub-state.
 * Non-state events (LLM, action, decision) inside the window are attached to
 * the current encounter.
 */
export function groupPhaseEncounters(
  events: MonitorEvent[],
  primaryStates: Set<string>,
): PhaseEncounter[] {
  const encounters: PhaseEncounter[] = []
  let current: PhaseEncounter | null = null
  let lastFloor = 0

  const closeCurrent = () => {
    if (current) {
      encounters.push(current)
      current = null
    }
  }

  for (const event of events) {
    const stateData = event.type === 'state' ? (event.data as unknown as StateData) : null
    const transData = event.type === 'transition' ? (event.data as unknown as TransitionData) : null
    const stateType = stateData?.state_type ?? transData?.state_type
    if (stateData?.floor) lastFloor = stateData.floor
    else if (transData?.floor) lastFloor = transData.floor

    if (stateType && primaryStates.has(stateType)) {
      if (!current) {
        const kind = PHASE_TO_KIND[stateType] ?? 'event'
        current = {
          id: event.id,
          kind,
          floor: stateData?.floor ?? transData?.floor ?? lastFloor,
          events: [event],
          hpBefore: stateData?.player?.hp,
        }
      } else {
        current.events.push(event)
      }

      // Pick up the event title when present (for the event phase).
      // Backend ships this as state.data.event_details.event_name.
      if (current.kind === 'event' && stateData) {
        const details = (stateData as Record<string, unknown>).event_details as Record<string, unknown> | undefined
        const title = details && typeof details.event_name === 'string' ? details.event_name : undefined
        if (title && !current.title) current.title = title
      }
      continue
    }

    if (current) {
      // Sub-states keep the encounter alive (e.g. card_select inside a shop).
      if (stateType && SUB_STATES.has(stateType)) {
        current.events.push(event)
        continue
      }

      // A state transition to something else closes the encounter.
      // Capture exit HP if the new state has player data.
      if (stateType) {
        if (stateData?.player?.hp != null) current.hpAfter = stateData.player.hp
        closeCurrent()
        continue
      }

      // Attach decision text where useful (final answer for the phase).
      if (event.type === 'decision') {
        const dd = event.data as unknown as DecisionData
        if (!current.decision && typeof dd.reasoning === 'string' && dd.reasoning.length > 0) {
          current.decision = dd.reasoning.split('\n')[0].slice(0, 120)
        }
      }
      current.events.push(event)
    }
  }

  if (current) encounters.push(current)
  return encounters
}
