import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as api from '../lib/api'
import type { User } from '../types'
import { AuthContext, type AuthStatus, type AuthValue } from './auth-context'

/**
 * Holds the signed-in account for the whole app.
 *
 * There is no token here to look after — the browser replays the httpOnly
 * cookie on its own. What this owns is the *answer* to "who is signed in",
 * which is asked once at boot and then kept in sync with the server.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>('checking')

  // Boot check: turn the cookie we cannot read into an account, or nothing.
  useEffect(() => {
    const controller = new AbortController()

    void (async () => {
      try {
        const me = await api.fetchMe(controller.signal)
        setUser(me)
        setStatus(me ? 'authenticated' : 'anonymous')
      } catch (error) {
        if ((error as Error).name === 'AbortError') return
        // Backend unreachable — treat as signed out rather than hanging on a
        // spinner forever; the chat screen surfaces the connection error.
        setUser(null)
        setStatus('anonymous')
      }
    })()

    return () => controller.abort()
  }, [])

  // A session can also end elsewhere — it expired, or another device hit
  // "sign out everywhere". Any 401 from any call lands here.
  useEffect(() => {
    api.setUnauthorizedHandler(() => {
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
    async (email: string, password: string) => adopt(await api.login({ email, password })),
    [adopt],
  )

  const signUp = useCallback(
    async (name: string, email: string, password: string) =>
      adopt(await api.signup({ name, email, password })),
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
