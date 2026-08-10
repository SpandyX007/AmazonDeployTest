import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell, Field, PasswordField } from '../components/AuthShell'
import { ArrowIcon } from '../components/Icons'
import { useAuth } from '../context/auth-context'

const MIN_PASSWORD = 8

export function Signup() {
  const { signUp } = useAuth()
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return

    // Catch the two failures worth catching here rather than round-tripping;
    // everything else (duplicate email, malformed address) is the server's call.
    if (password.length < MIN_PASSWORD) {
      setError(`Password must be at least ${MIN_PASSWORD} characters`)
      return
    }
    if (password !== confirm) {
      setError('Those passwords do not match')
      return
    }

    setPending(true)
    setError(null)
    try {
      await signUp(name.trim(), email.trim(), password)
      navigate('/chat', { replace: true })
    } catch (failure) {
      setError((failure as Error).message)
      setPending(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Get started"
      title="Create an account"
      subtitle="Takes a moment. Your conversations start being remembered straight away."
      footer={
        <>
          Already have an account? <Link to="/login">Sign in</Link>
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
          label="Name"
          name="name"
          autoComplete="name"
          placeholder="Ada Lovelace"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
        />

        <Field
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />

        <PasswordField
          label="Password"
          name="password"
          autoComplete="new-password"
          placeholder="••••••••••"
          hint={`At least ${MIN_PASSWORD} characters. A phrase beats a puzzle.`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <PasswordField
          label="Confirm password"
          name="confirm-password"
          autoComplete="new-password"
          placeholder="••••••••••"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />

        <button type="submit" className="btn btn-primary btn-block" disabled={pending}>
          <span>{pending ? 'Creating…' : 'Create account'}</span>
          {!pending && <ArrowIcon />}
        </button>
      </form>
    </AuthShell>
  )
}
