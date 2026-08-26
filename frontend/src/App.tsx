import type { ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider } from './context/AuthProvider'
import { BillingProvider } from './context/BillingProvider'
import { useAuth } from './context/auth-context'
import { Chat } from './pages/Chat'
import { Landing } from './pages/Landing'
import { Login } from './pages/Login'
import { Signup } from './pages/Signup'
import './App.css'
import './pages.css'

/** Shown only while the boot check is in flight — see AuthProvider. */
function Booting() {
  return (
    <div className="booting">
      <span className="brand-mark" aria-hidden="true">
        N
      </span>
      <span className="label">Restoring your session…</span>
    </div>
  )
}

/**
 * Gate for the workspace. This is a *convenience*, not the security boundary —
 * every protected endpoint checks the session itself, so a user who edits their
 * way past this guard reaches a screen with nothing in it.
 */
function RequireAuth({ children }: { children: ReactElement }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'checking') return <Booting />
  if (status === 'anonymous') {
    // Remember where they were headed so the login can hand them back.
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  return children
}

/** Keeps a signed-in user off the login and signup screens. */
function GuestOnly({ children }: { children: ReactElement }) {
  const { status } = useAuth()

  if (status === 'checking') return <Booting />
  if (status === 'authenticated') return <Navigate to="/chat" replace />
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <BillingProvider>
          <Routes>
          <Route path="/" element={<Landing />} />
          <Route
            path="/login"
            element={
              <GuestOnly>
                <Login />
              </GuestOnly>
            }
          />
          <Route
            path="/signup"
            element={
              <GuestOnly>
                <Signup />
              </GuestOnly>
            }
          />
          <Route
            path="/chat"
            element={
              <RequireAuth>
                <Chat />
              </RequireAuth>
            }
          />
          <Route
            path="/chat/:conversationId"
            element={
              <RequireAuth>
                <Chat />
              </RequireAuth>
            }
          />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BillingProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
