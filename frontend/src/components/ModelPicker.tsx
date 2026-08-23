import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { ChevronIcon, LockIcon } from './Icons'
import type { Model, Provider } from '../types'

interface Props {
  provider: Provider | null
  selectedId: string | null
  onSelect: (id: string) => void
  /** A locked model was clicked — show the paywall rather than selecting it. */
  onLocked: (model: Model) => void
}

const PLACEHOLDER: Model = {
  id: '—',
  name: 'No model',
  tagline: '',
  context: '—',
  speed: 'Balanced',
  tier: 'free',
  inputRate: 1,
  outputRate: 1,
  locked: false,
}

export function ModelPicker({ provider, selectedId, onSelect, onLocked }: Props) {
  const [open, setOpen] = useState(false)
  const [lastProviderId, setLastProviderId] = useState(provider?.id)
  const rootRef = useRef<HTMLDivElement>(null)

  // Close when the provider changes out from under the menu.
  if (provider?.id !== lastProviderId) {
    setLastProviderId(provider?.id)
    setOpen(false)
  }

  const models = provider?.models ?? []
  const selected = models.find((m) => m.id === selectedId) ?? models[0] ?? PLACEHOLDER
  const hue = provider?.hue ?? 0
  const disabled = models.length === 0
  const unlockedCount = models.filter((m) => !m.locked).length

  useEffect(() => {
    if (!open) return

    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div className="model-picker" ref={rootRef}>
      <button
        type="button"
        className={`model-trigger ${open ? 'is-open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="model-badge" style={{ '--hue': hue } as CSSProperties}>
          {provider?.initials ?? '··'}
        </span>
        <span className="model-trigger-text">
          <span className="model-trigger-name">
            {selected.name}
            {selected.tier === 'premium' && <span className="tier-tag">Pro</span>}
          </span>
          <span className="label model-trigger-id">{selected.id}</span>
        </span>
        <ChevronIcon className={`chevron ${open ? 'is-open' : ''}`} />
      </button>

      {open && provider && (
        <div className="model-menu" role="listbox" aria-label="Select a model">
          <div className="model-menu-head">
            <span className="model-menu-title">{provider.label} models</span>
            <span className="label">
              {unlockedCount === models.length
                ? `${models.length} available`
                : `${unlockedCount} of ${models.length} unlocked`}
            </span>
          </div>

          <div className="model-menu-scroll">
            {models.map((model) => {
              const isSelected = model.id === selected.id
              const premium = model.tier === 'premium'
              return (
                <button
                  type="button"
                  key={model.id}
                  role="option"
                  aria-selected={isSelected}
                  className={`model-option ${isSelected ? 'is-selected' : ''} ${
                    model.locked ? 'is-locked' : ''
                  }`}
                  onClick={() => {
                    setOpen(false)
                    if (model.locked) onLocked(model)
                    else onSelect(model.id)
                  }}
                  style={{ '--hue': provider.hue } as CSSProperties}
                >
                  <span className="model-option-name">
                    {model.name}
                    {premium && (
                      <span className={`tier-tag ${model.locked ? 'is-locked' : ''}`}>
                        {model.locked && <LockIcon />}
                        Pro
                      </span>
                    )}
                  </span>
                  <span className="model-option-tagline">{model.tagline || model.id}</span>
                  <span className="label model-option-spec">
                    {model.context} · {model.speed}
                    <br />
                    {model.outputRate}× credits
                  </span>
                </button>
              )
            })}
          </div>

          <div className="model-menu-foot label">
            {unlockedCount < models.length
              ? 'Pro models unlock with a top-up · switching keeps the thread'
              : `Served over ${provider.label} · switching keeps the thread`}
          </div>
        </div>
      )}
    </div>
  )
}
