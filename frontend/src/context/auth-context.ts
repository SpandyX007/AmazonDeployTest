import { createContext, useContext } from 'react'
import type { User } from '../types'

/**
 * `checking` matters more than it looks: on a hard refresh the app cannot know
 * whether the (unreadable, httpOnly) cookie is still good until /api/auth/me
 * answers. Rendering the login screen during that gap would flash it in the
 * face of an already signed-in user.
 */
export type AuthStatus = 'checking' | 'authenticated' | 'anonymous'

export interface AuthValue {
  user: User | null
  status: AuthStatus
  signIn: (email: string, password: string) => Promise<void>
  signUp: (name: string, email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  signOutEverywhere: () => Promise<void>
}

export const AuthContext = createContext<AuthValue | null>(null)

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}
