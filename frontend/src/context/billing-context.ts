import { createContext, useContext } from 'react'
import type { Billing, TurnUsage } from '../types'

/** Why the paywall opened — it changes the headline, not the flow. */
export type PaywallReason = 'insufficient_credits' | 'model_locked' | 'topup'

export interface BillingValue {
  /** Null until the first fetch lands (or while signed out). */
  billing: Billing | null
  /** Re-read from the server — after a payment claim, or on "check status". */
  refresh: () => Promise<void>
  /** Fold a turn's `done` usage into the balance without a round-trip. */
  applyUsage: (usage: TurnUsage) => void
  paywall: PaywallReason | null
  openPaywall: (reason: PaywallReason) => void
  closePaywall: () => void
}

export const BillingContext = createContext<BillingValue | null>(null)

export function useBilling(): BillingValue {
  const value = useContext(BillingContext)
  if (!value) throw new Error('useBilling must be used inside <BillingProvider>')
  return value
}
