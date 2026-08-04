import type { CSSProperties } from 'react'
import { SAMPLE_CONVERSATIONS, getModel } from '../data/models'
import { PlusIcon, SidebarIcon } from './Icons'

interface Props {
  open: boolean
  activeId: string | null
  onSelect: (id: string) => void
  onNewChat: () => void
  onClose: () => void
}

const GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 days']

/** Flat reading order, so the index numbers run 01..n across all groups. */
const ORDERED_IDS = GROUP_ORDER.flatMap((group) =>
  SAMPLE_CONVERSATIONS.filter((c) => c.group === group).map((c) => c.id),
)

export function Sidebar({ open, activeId, onSelect, onNewChat, onClose }: Props) {
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
        <button
          type="button"
          className="icon-btn"
          onClick={onClose}
          aria-label="Collapse sidebar"
        >
          <SidebarIcon />
        </button>
      </div>

      <button type="button" className="new-chat" onClick={onNewChat}>
        <span>New thread</span>
        <PlusIcon />
      </button>

      <nav className="conv-list" aria-label="Chat history">
        {GROUP_ORDER.map((group) => {
          const items = SAMPLE_CONVERSATIONS.filter((c) => c.group === group)
          if (items.length === 0) return null

          return (
            <div className="conv-group" key={group}>
              <div className="conv-group-label label">
                <span>{group}</span>
                <span className="conv-group-count">{items.length}</span>
              </div>

              {items.map((conv) => {
                const model = getModel(conv.modelId)
                const index = ORDERED_IDS.indexOf(conv.id) + 1

                return (
                  <button
                    type="button"
                    key={conv.id}
                    className={`conv-item ${activeId === conv.id ? 'is-active' : ''}`}
                    onClick={() => onSelect(conv.id)}
                  >
                    <span className="conv-index">{String(index).padStart(2, '0')}</span>
                    <span className="conv-title">{conv.title}</span>
                    <span
                      className="conv-dot"
                      style={{ '--hue': model.hue } as CSSProperties}
                      title={model.name}
                    />
                  </button>
                )
              })}
            </div>
          )
        })}
      </nav>

      <div className="sidebar-foot">
        <button type="button" className="user-pill">
          <span className="avatar avatar-user">S</span>
          <span className="user-meta">
            <span className="user-name">Spandan</span>
            <span className="label user-plan">Free plan</span>
          </span>
        </button>
      </div>
    </aside>
  )
}
