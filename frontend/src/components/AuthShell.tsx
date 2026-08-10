import { useId, useState } from 'react'
import type { InputHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { EyeIcon, EyeOffIcon, MoonIcon, SunIcon } from './Icons'
import { useTheme } from '../lib/theme'

const ASSURANCES = [
  'Passwords are hashed with bcrypt — never stored in the clear.',
  'Your session lives in a cookie this page cannot read.',
  'Threads are scoped to your account and follow you between devices.',
]

/** The split screen both auth pages sit in: editorial panel left, form right. */
export function AuthShell({
  eyebrow,
  title,
  subtitle,
  children,
  footer,
}: {
  eyebrow: string
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  const { theme, toggle } = useTheme()

  return (
    <div className="page auth">
      <div className="grain" aria-hidden="true" />

      <aside className="auth-aside">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            N
          </span>
          <span className="brand-text">
            <span className="brand-name">Nexus</span>
            <span className="label brand-sub">Multi-model</span>
          </span>
        </Link>

        <div className="auth-aside-body">
          <p className="auth-quote">
            One thread, every provider. Pick the mind that fits the question — the
            conversation carries over.
          </p>
          <ul className="auth-points">
            {ASSURANCES.map((point) => (
              <li key={point}>
                <span className="auth-point-tick" aria-hidden="true" />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>

        <span className="label auth-aside-foot">FastAPI · React · SQLAlchemy</span>
      </aside>

      <main className="auth-main">
        <div className="auth-topbar">
          <Link to="/" className="lp-link auth-back">
            ← Back
          </Link>
          <button
            type="button"
            className="icon-btn"
            onClick={toggle}
            aria-label="Toggle colour theme"
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>

        <div className="auth-card">
          <p className="label auth-eyebrow">{eyebrow}</p>
          <h1 className="auth-title">{title}</h1>
          <p className="auth-sub">{subtitle}</p>

          {children}

          <p className="auth-footer">{footer}</p>
        </div>
      </main>
    </div>
  )
}

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
}

export function Field({ label, hint, ...input }: FieldProps) {
  const id = useId()
  return (
    <div className="field">
      <label className="label field-label" htmlFor={id}>
        {label}
      </label>
      <input id={id} className="field-input" {...input} />
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  )
}

/** Password field with a reveal toggle — typo-proofing beats forced retyping. */
export function PasswordField({ label, hint, ...input }: FieldProps) {
  const id = useId()
  const [shown, setShown] = useState(false)

  return (
    <div className="field">
      <label className="label field-label" htmlFor={id}>
        {label}
      </label>
      <div className="field-wrap">
        <input id={id} className="field-input" type={shown ? 'text' : 'password'} {...input} />
        <button
          type="button"
          className="field-reveal"
          onClick={() => setShown((v) => !v)}
          aria-label={shown ? 'Hide password' : 'Show password'}
          tabIndex={-1}
        >
          {shown ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  )
}
