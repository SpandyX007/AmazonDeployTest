import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { MODELS, getModel } from '../data/models'
import { ChevronIcon } from './Icons'
import type { Model } from '../types'

interface Props {
  selectedId: string
  onSelect: (id: string) => void
}

/** Groups models under their provider, preserving catalog order. */
function groupByProvider(models: Model[]) {
  const groups: { provider: string; models: Model[] }[] = []
  for (const model of models) {
    const existing = groups.find((g) => g.provider === model.provider)
    if (existing) existing.models.push(model)
    else groups.push({ provider: model.provider, models: [model] })
  }
  return groups
}

export function ModelPicker({ selectedId, onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const selected = getModel(selectedId)

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
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className="model-badge"
          style={{ '--hue': selected.hue } as CSSProperties}
        >
          {selected.initials}
        </span>
        <span className="model-trigger-text">
          <span className="model-trigger-name">{selected.name}</span>
          <span className="label model-trigger-id">{selected.id}</span>
        </span>
        <ChevronIcon className={`chevron ${open ? 'is-open' : ''}`} />
      </button>

      {open && (
        <div className="model-menu" role="listbox" aria-label="Select a model">
          <div className="model-menu-head">
            <span className="model-menu-title">Model index</span>
            <span className="label">{MODELS.length} available</span>
          </div>

          <div className="model-menu-scroll">
            {groupByProvider(MODELS).map((group) => (
              <div className="model-group" key={group.provider}>
                <div className="model-group-label label">{group.provider}</div>

                {group.models.map((model) => {
                  const isSelected = model.id === selectedId
                  return (
                    <button
                      type="button"
                      key={model.id}
                      role="option"
                      aria-selected={isSelected}
                      className={`model-option ${isSelected ? 'is-selected' : ''}`}
                      onClick={() => {
                        onSelect(model.id)
                        setOpen(false)
                      }}
                      style={{ '--hue': model.hue } as CSSProperties}
                    >
                      <span className="model-option-name">{model.name}</span>
                      <span className="model-option-tagline">{model.tagline}</span>
                      <span className="label model-option-spec">
                        {model.context} · {model.speed}
                      </span>
                    </button>
                  )
                })}
              </div>
            ))}
          </div>

          <div className="model-menu-foot label">
            Served over Groq · switching keeps the thread
          </div>
        </div>
      )}
    </div>
  )
}
