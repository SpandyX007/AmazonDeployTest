import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useBilling, type PaywallReason } from '../context/billing-context'
import * as api from '../lib/api'
import type { Billing } from '../types'
import { CheckIcon, CloseIcon, CopyIcon, LockIcon, RetryIcon } from './Icons'

const formatNumber = new Intl.NumberFormat('en-IN')

const HEADLINES = {
  insufficient_credits: {
    eyebrow: 'Out of credits',
    title: 'Your free credits are used up.',
    lede: 'Top up once and keep the thread going — premium models come with it.',
  },
  model_locked: {
    eyebrow: 'Premium model',
    title: 'This one is behind the paywall.',
    lede: 'The larger models cost more to run. One top-up unlocks all of them.',
  },
  topup: {
    eyebrow: 'Top up',
    title: 'Add credits to your account.',
    lede: 'Pay by UPI, paste the transaction reference, and you are unlocked once it is verified.',
  },
} as const

/**
 * The manual UPI paywall.
 *
 * Three steps, no gateway: scan the owner's QR, pay, paste the transaction
 * id. The claim is then `pending` until the owner checks their statement and
 * approves it — so the modal has two faces, "pay" and "waiting", and switches
 * on whether a pending payment exists.
 */
export function Paywall() {
  const { billing, paywall } = useBilling()
  // Mounted only while open, so the form starts clean on every opening.
  if (paywall === null || !billing) return null
  return <PaywallDialog reason={paywall} billing={billing} />
}

function PaywallDialog({ reason, billing }: { reason: PaywallReason; billing: Billing }) {
  const { closePaywall, refresh } = useBilling()
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  // Escape closes.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closePaywall()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [closePaywall])

  const copy = HEADLINES[reason]
  const { pack, upi, pendingPayment, balance, isPremium } = billing

  async function claim(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await api.submitPayment({ reference, note })
      setReference('')
      setNote('')
      await refresh()
    } catch (failure) {
      setError((failure as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function check() {
    setBusy(true)
    try {
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  function copyUpi() {
    if (!upi) return
    void navigator.clipboard?.writeText(upi.id).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    })
  }

  return (
    <div className="paywall-scrim" onClick={closePaywall}>
      <section
        className="paywall"
        role="dialog"
        aria-modal="true"
        aria-labelledby="paywall-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="paywall-head">
          <div>
            <p className="label paywall-eyebrow">
              <LockIcon />
              <span>{copy.eyebrow}</span>
            </p>
            <h2 className="paywall-title" id="paywall-title">
              {copy.title}
            </h2>
            <p className="paywall-lede">{copy.lede}</p>
          </div>
          <button type="button" className="icon-btn" onClick={closePaywall} aria-label="Close">
            <CloseIcon />
          </button>
        </header>

        <div className="paywall-grid">
          {/* What you get */}
          <div className="paywall-offer">
            <div className="paywall-price">
              <span className="paywall-currency">₹</span>
              <span className="paywall-amount">{pack.priceInr}</span>
              <span className="label paywall-once">one time</span>
            </div>
            <ul className="paywall-perks">
              <li>
                <CheckIcon />
                <span>
                  <strong>{formatNumber.format(pack.credits)}</strong> credits added
                </span>
              </li>
              <li>
                <CheckIcon />
                <span>Every premium model unlocked</span>
              </li>
              <li>
                <CheckIcon />
                <span>Credits never expire</span>
              </li>
            </ul>
            <p className="label paywall-balance">
              balance now · {formatNumber.format(balance)} · {isPremium ? 'premium' : 'free tier'}
            </p>
          </div>

          {/* How to pay */}
          <div className="paywall-pay">
            {upi ? (
              <>
                <img
                  className="paywall-qr"
                  src={api.qrImageUrl(upi.qrUrl)}
                  alt={`UPI QR code for ${upi.id}`}
                  width={176}
                  height={176}
                />
                <div className="paywall-upi">
                  <span className="label">UPI ID</span>
                  <code>{upi.id}</code>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={copyUpi}
                    aria-label="Copy UPI id"
                    title="Copy"
                  >
                    {copied ? <CheckIcon /> : <CopyIcon />}
                  </button>
                </div>
                <a className="paywall-deeplink label" href={upi.uri}>
                  Open in a UPI app ↗
                </a>
              </>
            ) : (
              <p className="paywall-unavailable">
                Payments are not set up on this server yet. Ask the owner to configure UPI.
              </p>
            )}
          </div>
        </div>

        {pendingPayment ? (
          <div className="paywall-pending" role="status">
            <span className="pulse is-live" aria-hidden="true" />
            <div className="paywall-pending-text">
              <strong>Waiting for verification.</strong>
              <span>
                Payment #{pendingPayment.id} · ref {pendingPayment.reference} · credits land
                automatically once the owner confirms it.
              </span>
            </div>
            <button
              type="button"
              className={`paywall-check ${busy ? 'is-busy' : ''}`}
              onClick={() => void check()}
              disabled={busy}
            >
              <RetryIcon />
              <span>Check</span>
            </button>
          </div>
        ) : upi ? (
          <form className="paywall-claim" onSubmit={(event) => void claim(event)}>
            <p className="label paywall-step">After paying, paste the transaction id</p>
            <div className="paywall-fields">
              <input
                className="paywall-input"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                placeholder="UTR / transaction ID (12 digits)"
                autoComplete="off"
                spellCheck={false}
                inputMode="text"
                required
                minLength={6}
                maxLength={80}
              />
              <input
                className="paywall-input"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Payer name (optional)"
                maxLength={200}
              />
              <button type="submit" className="paywall-submit" disabled={busy || !reference.trim()}>
                {busy ? 'Sending…' : 'I have paid'}
              </button>
            </div>
            {error && (
              <p className="paywall-error" role="alert">
                {error}
              </p>
            )}
          </form>
        ) : null}

        <footer className="label paywall-foot">
          Verified by a person, not a script — usually within a few hours.
        </footer>
      </section>
    </div>
  )
}
