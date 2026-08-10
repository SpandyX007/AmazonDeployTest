import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { KineticHeadline } from '../components/KineticHeadline'
import { ArrowIcon, MoonIcon, SunIcon } from '../components/Icons'
import { useAuth } from '../context/auth-context'
import { fetchCatalog } from '../lib/api'
import { useTheme } from '../lib/theme'

/** Live counts from the public catalog — the only thing on this page that is
 *  not static copy, and the quickest way to see the backend is actually up. */
function useFleet() {
  const [fleet, setFleet] = useState<{ providers: number; models: number } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      try {
        const catalog = await fetchCatalog(controller.signal)
        const online = catalog.providers.filter((p) => p.available)
        setFleet({
          providers: online.length,
          models: online.reduce((total, p) => total + p.models.length, 0),
        })
      } catch {
        setFleet(null)
      }
    })()
    return () => controller.abort()
  }, [])

  return fleet
}

const FEATURES = [
  {
    title: 'Switch minds mid-thought',
    body: 'Groq, Gemini and a local Ollama sit behind one picker. Change model in the middle of a thread and the conversation carries over intact.',
  },
  {
    title: 'Memory that outlives the tab',
    body: 'Every turn is stored against your account, not your browser. Close the laptop, sign in on another one, and pick the thread up where you left it.',
  },
  {
    title: 'Your threads, only yours',
    body: 'Sessions ride in a cookie the page cannot read, and every query is scoped to the account that made it. Sign out from one device or from all of them.',
  },
]

const FLOW = [
  { step: 'Create an account', body: 'Email and a password. The password is hashed with bcrypt; it is never stored or logged in the clear.' },
  { step: 'Get a session', body: 'The server issues a random token, keeps only its hash, and hands your browser an httpOnly cookie.' },
  { step: 'Start a thread', body: 'Your first message creates a conversation, titled from what you asked, owned by your account.' },
  { step: 'Come back later', body: 'The cookie identifies you, the thread reloads from the database, and the model reads the same history you see.' },
]

export function Landing() {
  const { theme, toggle } = useTheme()
  const { status, user } = useAuth()
  const fleet = useFleet()

  const signedIn = status === 'authenticated'

  return (
    <div className="page lp">
      <div className="grain" aria-hidden="true" />

      <header className="lp-nav">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            N
          </span>
          <span className="brand-text">
            <span className="brand-name">Nexus</span>
            <span className="label brand-sub">Multi-model</span>
          </span>
        </Link>

        <nav className="lp-nav-actions">
          <button
            type="button"
            className="icon-btn"
            onClick={toggle}
            aria-label="Toggle colour theme"
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>

          {signedIn ? (
            <Link to="/chat" className="btn btn-primary">
              <span>Open workspace</span>
              <ArrowIcon />
            </Link>
          ) : (
            <>
              <Link to="/login" className="lp-link">
                Log in
              </Link>
              <Link to="/signup" className="btn btn-primary">
                <span>Get started</span>
                <ArrowIcon />
              </Link>
            </>
          )}
        </nav>
      </header>

      <main className="lp-main">
        <section className="lp-hero">
          <p className="label lp-eyebrow">
            <span>AI Workspace</span>
            <span className="tick" />
            <span>
              {fleet
                ? `${fleet.providers} providers · ${fleet.models} models online`
                : 'connecting to the service…'}
            </span>
          </p>

          <KineticHeadline text="Every model. One thread. Your memory." className="lp-title" />

          <p className="lp-sub">
            A chat workspace where the conversation belongs to you, not to the tab it started
            in. Sign in once — your threads, and the context behind them, follow you.
          </p>

          <div className="lp-actions">
            {signedIn ? (
              <Link to="/chat" className="btn btn-primary btn-lg">
                <span>Continue as {user?.name.split(' ')[0]}</span>
                <ArrowIcon />
              </Link>
            ) : (
              <>
                <Link to="/signup" className="btn btn-primary btn-lg">
                  <span>Create an account</span>
                  <ArrowIcon />
                </Link>
                <Link to="/login" className="btn btn-ghost btn-lg">
                  I already have one
                </Link>
              </>
            )}
          </div>

          <p className="label lp-note">Bring your own keys · nothing leaves your provider</p>
        </section>

        <section className="lp-specs" aria-label="Service status">
          <div className="lp-spec">
            <em className="label">providers</em>
            <b>{fleet ? String(fleet.providers).padStart(2, '0') : '—'}</b>
          </div>
          <div className="lp-spec">
            <em className="label">models</em>
            <b>{fleet ? String(fleet.models).padStart(2, '0') : '—'}</b>
          </div>
          <div className="lp-spec">
            <em className="label">history</em>
            <b>kept</b>
          </div>
          <div className="lp-spec">
            <em className="label">session</em>
            <b>revocable</b>
          </div>
        </section>

        <section className="lp-features">
          {FEATURES.map((feature, i) => (
            <article className="lp-card" key={feature.title}>
              <span className="label lp-card-index">{String(i + 1).padStart(2, '0')}</span>
              <h2 className="lp-card-title">{feature.title}</h2>
              <p className="lp-card-body">{feature.body}</p>
            </article>
          ))}
        </section>

        <section className="lp-flow">
          <div className="lp-flow-head">
            <p className="label">How a session works</p>
            <h2 className="lp-flow-title">Four steps, then it stays out of your way.</h2>
          </div>

          <ol className="lp-steps">
            {FLOW.map((item, i) => (
              <li className="lp-step" key={item.step}>
                <span className="lp-step-index">{String(i + 1).padStart(2, '0')}</span>
                <div>
                  <h3 className="lp-step-title">{item.step}</h3>
                  <p className="lp-step-body">{item.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {!signedIn && (
          <section className="lp-closer">
            <h2 className="lp-closer-title">Ready when you are.</h2>
            <Link to="/signup" className="btn btn-primary btn-lg">
              <span>Create an account</span>
              <ArrowIcon />
            </Link>
          </section>
        )}
      </main>

      <footer className="lp-foot">
        <span className="label">Nexus · multi-provider chat</span>
        <span className="label">FastAPI · React · SQLAlchemy</span>
      </footer>
    </div>
  )
}
