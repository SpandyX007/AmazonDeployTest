import type { CSSProperties } from 'react'
import type { Provider } from '../types'

interface Props {
  providers: Provider[]
  selectedId: string | null
  onSelect: (provider: Provider) => void
}

/**
 * A segmented rail rather than a dropdown: the provider is the coarser choice,
 * so it stays visible. Unconfigured providers stay listed but inert, with the
 * setup step as their tooltip.
 */
export function ProviderPicker({ providers, selectedId, onSelect }: Props) {
  if (providers.length === 0) return null

  return (
    <div className="provider-rail" role="radiogroup" aria-label="LLM provider">
      <span className="label provider-rail-label">Provider</span>

      {providers.map((provider) => {
        const isSelected = provider.id === selectedId

        return (
          <button
            type="button"
            key={provider.id}
            role="radio"
            aria-checked={isSelected}
            disabled={!provider.available}
            title={provider.available ? provider.label : `${provider.detail} — ${provider.setupHint}`}
            className={`provider-chip ${isSelected ? 'is-selected' : ''}`}
            style={{ '--hue': provider.hue } as CSSProperties}
            onClick={() => onSelect(provider)}
          >
            <span className="provider-chip-dot" />
            <span className="provider-chip-name">{provider.label}</span>
            {!provider.available && <span className="provider-chip-note">offline</span>}
          </button>
        )
      })}
    </div>
  )
}
