import type { CSSProperties } from 'react'
import { SAMPLE_CONVERSATIONS, getModel } from '../data/models'
import { PlusIcon, SidebarIcon, TrashIcon } from './Icons'

interface Props {
  open: boolean
  activeId: string | null
  onSelect: (id: string) => void
  onNewChat: () => void
  onClose: () => void
}

const GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 days']

export function Sidebar({ open, activeId, onSelect, onNewChat, onClose }: Props) {
  return (
    <aside className={`sidebar ${open ? 'is-open' : ''}`}>
      <div className="sidebar-head">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Nexus</span>
        </div>
        <button
          type="button"
          className="icon-btn sidebar-close"
          onClick={onClose}
          aria-label="Collapse sidebar"
        >
          <SidebarIcon />
        </button>
      </div>

      <button type="button" className="new-chat" onClick={onNewChat}>
        <PlusIcon />
        New chat
      </button>

      <nav className="conv-list" aria-label="Chat history">
        {GROUP_ORDER.map((group) => {
          const items = SAMPLE_CONVERSATIONS.filter((c) => c.group === group)
          if (items.length === 0) return null

          return (
            <div className="conv-group" key={group}>
              <div className="conv-group-label">{group}</div>
              {items.map((conv) => {
                const model = getModel(conv.modelId)
                return (
                  <button
                    type="button"
                    key={conv.id}
                    className={`conv-item ${activeId === conv.id ? 'is-active' : ''}`}
                    onClick={() => onSelect(conv.id)}
                  >
                    <span
                      className="conv-dot"
                      style={{ '--hue': model.hue } as CSSProperties}
                      aria-hidden="true"
                    />
                    <span className="conv-title">{conv.title}</span>
                    <span className="conv-actions">
                      <TrashIcon className="conv-trash" />
                    </span>
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
            <span className="user-plan">Free plan</span>
          </span>
        </button>
      </div>
    </aside>
  )
}
