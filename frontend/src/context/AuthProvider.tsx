import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as api from '../lib/api'
import type { User } from '../types'
import { AuthContext, type AuthStatus, type AuthValue } from './auth-context'

/**
 * Holds the signed-in account for the whole app.
 *
 * The access token itself lives in `lib/api.ts`, in a module variable rather
 * than in React state — it changes on every refresh, and re-rendering the tree
 * each time a background renewal lands would be noise. What this owns is the
 * *answer* to "who is signed in".
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>('checking')

  // Boot: a page load starts with no access token in memory — by design. The
  // refresh cookie is the only thing that survived, so trading it in is both
  // how we get a token and how we find out whether anyone is signed in.
  useEffect(() => {
    void (async () => {
      try {
        const session = await api.refreshSession()
        setUser(session?.user ?? null)
        setStatus(session ? 'authenticated' : 'anonymous')
      } catch {
        // Backend unreachable — treat as signed out rather than hanging on a
        // spinner forever; the chat screen surfaces the connection error.
        setUser(null)
        setStatus('anonymous')
      }
    })()
  }, [])

  // A session can also end elsewhere — the refresh chain was revoked, or
  // another device hit "sign out everywhere". This fires only for a 401 that
  // a refresh could not rescue, so it means the session is genuinely over.
  useEffect(() => {
    api.setUnauthorizedHandler(() => {
      api.clearSession()
      setUser(null)
      setStatus('anonymous')
    })
    return () => api.setUnauthorizedHandler(null)
  }, [])

  const adopt = useCallback((account: User) => {
    setUser(account)
    setStatus('authenticated')
  }, [])

  const signIn = useCallback(
    async (email: string, password: string) => {
      const session = await api.login({ email, password })
      adopt(session.user)
    },
    [adopt],
  )

  const signUp = useCallback(
    async (name: string, email: string, password: string) => {
      const session = await api.signup({ name, email, password })
      adopt(session.user)
    },
    [adopt],
  )

  const forget = useCallback(() => {
    setUser(null)
    setStatus('anonymous')
  }, [])

  const signOut = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      // Clear locally even if the request failed: the user asked to leave, and
      // a stale cookie will be rejected on its next use anyway.
      forget()
    }
  }, [forget])

  const signOutEverywhere = useCallback(async () => {
    try {
      await api.logoutEverywhere()
    } finally {
      forget()
    }
  }, [forget])

  const value = useMemo<AuthValue>(
    () => ({ user, status, signIn, signUp, signOut, signOutEverywhere }),
    [user, status, signIn, signUp, signOut, signOutEverywhere],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
