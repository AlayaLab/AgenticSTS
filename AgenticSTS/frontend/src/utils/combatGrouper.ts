import type {
  MonitorEvent, CombatEncounter, CombatType, CombatRound,
  StateData, CombatPlanData, GameActionData, CombatSummaryData, DecisionData,
} from '../types/events'

/**
 * Groups a flat event timeline into combat encounters with rounds.
 *
 * Encounter start: state event with combat data when not already in combat.
 * Encounter end: state without combat data, transition away, or run_end.
 * Round grouping: state.data.combat.round field changes.
 */
export function groupCombatEncounters(events: MonitorEvent[]): CombatEncounter[] {
  const encounters: CombatEncounter[] = []
  let current: CombatEncounter | null = null
  let currentRound: CombatRound | null = null
  let inCombat = false
  // After combat closes, watch for the picked card-reward decision and attach
  // to the just-closed encounter. Cleared when next combat starts.
  let pendingRewardEnc: CombatEncounter | null = null

  for (const event of events) {
    const stateData = event.type === 'state' ? (event.data as unknown as StateData) : null

    // combat_summary may arrive AFTER the post-combat state event has already
    // closed the encounter — handle it independently of inCombat by attaching
    // to the most recent encounter.
    if (event.type === 'combat_summary') {
      const summary = event.data as unknown as CombatSummaryData
      const target = current ?? encounters[encounters.length - 1]
      if (target) {
        target.outcome = summary.won ? 'victory' : 'defeat'
        target.combatSummary = summary
        if (!target.combatType) {
          const ct = summary.combat_type
          if (ct === 'monster' || ct === 'elite' || ct === 'boss') {
            target.combatType = ct
          }
        }
        if (currentRound) {
          currentRound.events.push(event)
          currentRound.hpAfter = summary.hp_after
        }
      }
      continue
    }

    // Detect combat start
    if (stateData?.combat && !inCombat) {
      inCombat = true
      pendingRewardEnc = null
      const enemies = stateData.combat.enemies?.map(e => e.name).join(', ') || 'Unknown'
      const ct = stateData.state_type
      const combatType: CombatType | undefined =
        ct === 'monster' || ct === 'elite' || ct === 'boss' ? ct : undefined
      current = {
        id: event.id,
        enemyNames: enemies,
        floor: stateData.floor ?? 0,
        rounds: [],
        combatType,
      }
      currentRound = {
        roundNumber: stateData.combat.round,
        events: [event],
        actions: [],
        hpBefore: stateData.combat.player.hp,
      }
      current.rounds.push(currentRound)
      continue
    }

    // Detect combat end + round transitions
    if (inCombat && current) {
      const midCombatStates = ['monster', 'elite', 'boss', 'hand_select', 'card_select']
      const stateType = stateData?.state_type ?? (event.data as Record<string, unknown>).state_type as string ?? ''

      const isCombatEnd =
        (stateData && !stateData.combat && !midCombatStates.includes(stateType)) ||
        event.type === 'run_end' ||
        (event.type === 'transition' && !midCombatStates.includes(stateType))

      if (isCombatEnd) {
        if (currentRound) {
          currentRound.hpAfter = currentRound.hpAfter ?? (stateData?.combat?.player.hp)
        }
        encounters.push(current)
        pendingRewardEnc = current
        current = null
        currentRound = null
        inCombat = false
        continue
      }

      // Within combat: detect round changes
      if (stateData?.combat && currentRound) {
        const newRound = stateData.combat.round
        if (newRound !== currentRound.roundNumber) {
          currentRound.hpAfter = stateData.combat.player.hp
          currentRound = {
            roundNumber: newRound,
            events: [event],
            actions: [],
            hpBefore: stateData.combat.player.hp,
          }
          current.rounds.push(currentRound)
          continue
        }
      }

      // Attach event to current round
      if (currentRound) {
        currentRound.events.push(event)

        if (event.type === 'combat_plan') {
          const plan = event.data as unknown as CombatPlanData
          currentRound.planSummary = plan.items?.map(i => i.card || i.type).join(' → ') || undefined
        }

        if (event.type === 'game_action') {
          const action = event.data as unknown as GameActionData
          currentRound.actions.push(formatActionLabel(action, currentRound.events))
        }
      }
      continue
    }

    // After combat: watch for the picked reward and attach.
    if (pendingRewardEnc) {
      const stateType = stateData?.state_type ?? ''
      // Closing window: next combat (handled at combat-start above), run_end,
      // or transition to a different scene that's not card_reward/card_select.
      if (event.type === 'run_end'
        || (stateType && stateType !== 'card_reward' && stateType !== 'card_select')) {
        pendingRewardEnc = null
      } else if (event.type === 'decision') {
        const dd = event.data as unknown as DecisionData
        if (dd.state_type === 'card_reward') {
          const action = (dd.action || {}) as Record<string, unknown>
          const name = (typeof action.action === 'string' ? action.action : '') || ''
          const cardName = pickFirstString(action, ['card', 'card_name', 'choice', 'name'])
          if (cardName) {
            pendingRewardEnc.cardReward = cardName
          } else if (name === 'skip_reward_cards' || name === 'skip') {
            pendingRewardEnc.cardReward = '(skipped)'
          }
        }
      }
    }
  }

  // Handle combat still in progress at end of events
  if (inCombat && current) {
    encounters.push(current)
  }

  return encounters
}

function pickFirstString(obj: Record<string, unknown>, keys: string[]): string | null {
  for (const k of keys) {
    const v = obj[k]
    if (typeof v === 'string' && v.length > 0) return v
  }
  return null
}

const ACTION_LABELS: Record<string, string> = {
  end_turn: 'end',
  use_potion: 'potion',
  discard_potion: 'discard-potion',
  select_deck_card: 'pick-deck',
  confirm_selection: 'confirm',
  cancel_selection: 'cancel',
  close_cards_view: 'close',
  skip_reward_cards: 'skip',
}

function formatActionLabel(action: GameActionData, recentEvents: MonitorEvent[]): string {
  if (action.action === 'play_card') {
    const idx = action.params?.card_index
    if (typeof idx === 'number') {
      const name = resolveHandCardName(idx, recentEvents)
      return name ? `play ${name}` : `play[${idx}]`
    }
    return 'play'
  }
  return ACTION_LABELS[action.action] ?? action.action
}

function resolveHandCardName(idx: number, recentEvents: MonitorEvent[]): string | null {
  for (let i = recentEvents.length - 1; i >= 0; i--) {
    const ev = recentEvents[i]
    if (ev.type !== 'state') continue
    const sd = ev.data as unknown as StateData
    const hand = sd.combat?.player?.hand
    if (hand && hand[idx]?.name) return hand[idx].name
  }
  return null
}
