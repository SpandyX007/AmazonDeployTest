import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AuthShell, Field, PasswordField } from '../components/AuthShell'
import { ArrowIcon } from '../components/Icons'
import { useAuth } from '../context/auth-context'

export function Login() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  /** Where the guard bounced us from, so a deep link survives the detour. */
  const destination = (location.state as { from?: string } | null)?.from ?? '/chat'

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return

    setPending(true)
    setError(null)
    try {
      await signIn(email.trim(), password)
      navigate(destination, { replace: true })
    } catch (failure) {
      setError((failure as Error).message)
      setPending(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in"
      subtitle="Your threads are where you left them."
      footer={
        <>
          New here? <Link to="/signup">Create an account</Link>
        </>
      }
    >
      <form className="auth-form" onSubmit={submit} noValidate>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}

        <Field
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />

        <PasswordField
          label="Password"
          name="password"
          autoComplete="current-password"
          placeholder="••••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <button type="submit" className="btn btn-primary btn-block" disabled={pending}>
          <span>{pending ? 'Signing in…' : 'Sign in'}</span>
          {!pending && <ArrowIcon />}
        </button>
      </form>
    </AuthShell>
  )
}
