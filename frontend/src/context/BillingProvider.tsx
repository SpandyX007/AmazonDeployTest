import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as api from '../lib/api'
import type { Billing, TurnUsage, User } from '../types'
import { useAuth } from './auth-context'
import { BillingContext, type BillingValue, type PaywallReason } from './billing-context'

interface State {
  /** Whose numbers these are. A different signed-in user invalidates them. */
  userId: string | null
  billing: Billing | null
  paywall: PaywallReason | null
}

const EMPTY: State = { userId: null, billing: null, paywall: null }

/** Enough to draw the meter before /api/billing/me answers. */
function seed(user: User): Billing {
  return {
    balance: user.creditBalance,
    isPremium: user.isPremium,
    freeSignupCredits: 0,
    pack: { priceInr: 0, credits: 0 },
    upi: null,
    pendingPayment: null,
  }
}

/**
 * The live credit balance, and whether the paywall is up.
 *
 * Loads once per sign-in. Between loads the balance is kept current from the
 * stream's `done` event — the server tells us what each turn cost and what is
 * left, so the meter in the sidebar never has to poll.
 *
 * State is tagged with the user id it belongs to and read through that tag,
 * so signing out (or in as someone else) drops it without an effect having to
 * notice and clear it.
 */
export function BillingProvider({ children }: { children: ReactNode }) {
  const { status, user } = useAuth()
  const [state, setState] = useState<State>(EMPTY)

  const userId = status === 'authenticated' && user ? user.id : null
  const current = userId && state.userId === userId ? state : null

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!userId) return
      try {
        const billing = await api.fetchBilling(signal)
        setState((prev) => ({
          userId,
          billing,
          paywall: prev.userId === userId ? prev.paywall : null,
        }))
      } catch {
        // Leave whatever was on screen; the next turn's `done` will correct it.
      }
    },
    [userId],
  )

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      await refresh(controller.signal)
    })()
    return () => controller.abort()
  }, [refresh])

  const applyUsage = useCallback(
    (usage: TurnUsage) => {
      if (!userId) return
      setState((prev) => {
        const base = prev.userId === userId && prev.billing ? prev.billing : user && seed(user)
        if (!base) return prev
        return {
          userId,
          billing: { ...base, balance: usage.balance },
          paywall: prev.userId === userId ? prev.paywall : null,
        }
      })
    },
    [userId, user],
  )

  const setPaywall = useCallback(
    (paywall: PaywallReason | null) => {
      if (!userId) return
      setState((prev) => ({
        userId,
        billing: prev.userId === userId ? prev.billing : null,
        paywall,
      }))
    },
    [userId],
  )

  const openPaywall = useCallback((reason: PaywallReason) => setPaywall(reason), [setPaywall])
  const closePaywall = useCallback(() => setPaywall(null), [setPaywall])

  const value = useMemo<BillingValue>(
    () => ({
      billing: current?.billing ?? (user && userId ? seed(user) : null),
      refresh,
      applyUsage,
      paywall: current?.paywall ?? null,
      openPaywall,
      closePaywall,
    }),
    [current, user, userId, refresh, applyUsage, openPaywall, closePaywall],
  )

  return <BillingContext.Provider value={value}>{children}</BillingContext.Provider>
}
