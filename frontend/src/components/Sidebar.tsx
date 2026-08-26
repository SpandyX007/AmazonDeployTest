import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { CoinIcon, LogoutIcon, PlusIcon, SidebarIcon, TrashIcon } from './Icons'
import { useBilling } from '../context/billing-context'
import type { Conversation, User } from '../types'

const formatNumber = new Intl.NumberFormat('en-IN')

/**
 * Balance, as a bar against the free allowance (or the pack, once paid).
 * A negative balance — the last turn overdrew — reads as an empty bar.
 */
function CreditMeter() {
  const { billing, openPaywall } = useBilling()
  if (!billing) return null

  const { balance, isPremium, freeSignupCredits, pack, pendingPayment } = billing
  const scale = Math.max(isPremium ? pack.credits : freeSignupCredits, 1)
  const fraction = Math.max(0, Math.min(1, balance / scale))
  const empty = balance <= 0
  const low = !empty && fraction < 0.15

  return (
    <div className={`credit-meter ${empty ? 'is-empty' : low ? 'is-low' : ''}`}>
      <div className="credit-meter-row">
        <span className="label credit-meter-label">
          <CoinIcon />
          <span>{isPremium ? 'Premium' : 'Free tier'}</span>
        </span>
        <span className="credit-meter-value" title={`${balance} credits`}>
          {formatNumber.format(Math.max(balance, 0))}
          <em>credits</em>
        </span>
      </div>
      <div className="credit-meter-bar" aria-hidden="true">
        <span style={{ '--fill': fraction } as CSSProperties} />
      </div>
      <button
        type="button"
        className="credit-meter-cta"
        onClick={() => openPaywall(empty ? 'insufficient_credits' : 'topup')}
      >
        {pendingPayment
          ? 'Payment pending · check'
          : empty
            ? 'Out of credits · top up'
            : isPremium
              ? 'Add credits'
              : `Unlock premium · ₹${pack.priceInr}`}
      </button>
    </div>
  )
}

interface Props {
  open: boolean
  conversations: Conversation[]
  activeId: string | null
  loading: boolean
  user: User | null
  onSelect: (id: string) => void
  onNewChat: () => void
  onDelete: (conversation: Conversation) => void
  onClose: () => void
  onSignOut: () => void
  onSignOutEverywhere: () => void
}

const GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Older']

function startOfDay(date: Date) {
  const copy = new Date(date)
  copy.setHours(0, 0, 0, 0)
  return copy
}

/** Buckets a thread by *local* calendar day — the server sends UTC instants. */
function groupOf(isoTimestamp: string): string {
  const days = Math.round(
    (startOfDay(new Date()).getTime() - startOfDay(new Date(isoTimestamp)).getTime()) / 86_400_000,
  )
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days <= 7) return 'Previous 7 days'
  if (days <= 30) return 'Previous 30 days'
  return 'Older'
}

/** Stable per-thread hue, so the dot colour survives a reload. */
function hueOf(id: string): number {
  let hash = 0
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) % 360
  return hash
}

export function Sidebar({
  open,
  conversations,
  activeId,
  loading,
  user,
  onSelect,
  onNewChat,
  onDelete,
  onClose,
  onSignOut,
  onSignOutEverywhere,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const footRef = useRef<HTMLDivElement>(null)
  const { billing } = useBilling()
  // The billing context is fresher than the sign-in snapshot on the user.
  const isPremium = billing?.isPremium ?? user?.isPremium ?? false

  // Dismiss the account menu on any click outside it.
  useEffect(() => {
    if (!menuOpen) return
    const close = (event: MouseEvent) => {
      if (!footRef.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [menuOpen])

  const ordered = conversations.map((c) => c.id)

  return (
    <aside className={`sidebar ${open ? 'is-open' : ''}`}>
      <div className="sidebar-head">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            N
          </span>
          <span className="brand-text">
            <span className="brand-name">Nexus</span>
            <span className="label brand-sub">Multi-model</span>
          </span>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Collapse sidebar">
          <SidebarIcon />
        </button>
      </div>

      <button type="button" className="new-chat" onClick={onNewChat}>
        <span>New thread</span>
        <PlusIcon />
      </button>

      <nav className="conv-list" aria-label="Chat history">
        {conversations.length === 0 ? (
          <p className="conv-empty label">
            {loading ? 'Loading your threads…' : 'No threads yet — ask something.'}
          </p>
        ) : (
          GROUP_ORDER.map((group) => {
            const items = conversations.filter((c) => groupOf(c.updatedAt) === group)
            if (items.length === 0) return null

            return (
              <div className="conv-group" key={group}>
                <div className="conv-group-label label">
                  <span>{group}</span>
                  <span className="conv-group-count">{items.length}</span>
                </div>

                {items.map((conversation) => (
                  <div
                    className={`conv-item ${activeId === conversation.id ? 'is-active' : ''}`}
                    key={conversation.id}
                  >
                    <button
                      type="button"
                      className="conv-open"
                      onClick={() => onSelect(conversation.id)}
                    >
                      <span className="conv-index">
                        {String(ordered.indexOf(conversation.id) + 1).padStart(2, '0')}
                      </span>
                      <span className="conv-title">{conversation.title || 'New thread'}</span>
                    </button>

                    <button
                      type="button"
                      className="conv-delete"
                      onClick={() => onDelete(conversation)}
                      aria-label={`Delete ${conversation.title}`}
                      title="Delete thread"
                    >
                      <TrashIcon />
                    </button>

                    <span
                      className="conv-dot"
                      style={{ '--hue': hueOf(conversation.id) } as CSSProperties}
                    />
                  </div>
                ))}
              </div>
            )
          })
        )}
      </nav>

      <CreditMeter />

      <div className="sidebar-foot" ref={footRef}>
        {menuOpen && (
          <div className="user-menu" role="menu">
            <button type="button" className="user-menu-item" role="menuitem" onClick={onSignOut}>
              <LogoutIcon />
              <span>Sign out</span>
            </button>
            <button
              type="button"
              className="user-menu-item"
              role="menuitem"
              onClick={onSignOutEverywhere}
            >
              <LogoutIcon />
              <span>Sign out everywhere</span>
            </button>
            <p className="user-menu-note">
              Signing out everywhere revokes every browser signed in to this account.
            </p>
          </div>
        )}

        <button
          type="button"
          className="user-pill"
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
        >
          <span className="avatar avatar-user">{user?.initials ?? '··'}</span>
          <span className="user-meta">
            <span className="user-name">{user?.name ?? 'Signed out'}</span>
            <span className="label user-plan">{user?.email ?? ''}</span>
          </span>
          {isPremium && <span className="tier-tag">Pro</span>}
        </button>
      </div>
    </aside>
  )
}
