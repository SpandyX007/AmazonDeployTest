import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { MODELS, getModel } from '../data/models'
import { ChevronIcon, CheckIcon } from './Icons'
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
        className="model-trigger"
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
          <span className="model-trigger-provider">{selected.provider}</span>
        </span>
        <ChevronIcon className={`chevron ${open ? 'is-open' : ''}`} />
      </button>

      {open && (
        <div className="model-menu" role="listbox" aria-label="Select a model">
          <div className="model-menu-head">
            <span>Choose a model</span>
            <span className="model-menu-count">{MODELS.length} available</span>
          </div>

          <div className="model-menu-scroll">
            {groupByProvider(MODELS).map((group) => (
              <div className="model-group" key={group.provider}>
                <div className="model-group-label">{group.provider}</div>
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
                    >
                      <span
                        className="model-badge"
                        style={{ '--hue': model.hue } as CSSProperties}
                      >
                        {model.initials}
                      </span>
                      <span className="model-option-body">
                        <span className="model-option-title">
                          {model.name}
                          <span className={`speed-tag speed-${model.speed.toLowerCase()}`}>
                            {model.speed}
                          </span>
                        </span>
                        <span className="model-option-tagline">{model.tagline}</span>
                        <span className="model-option-meta">{model.context} context</span>
                      </span>
                      {isSelected && <CheckIcon className="model-option-check" />}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
